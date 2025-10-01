import asyncio
import random
import time
from typing import Optional

import aiohttp


# Timers (seconds)
HEARTBEAT_INTERVAL = 0.2  # 200ms
ELECTION_TIMEOUT_MIN = 0.3  # 300ms
ELECTION_TIMEOUT_MAX = 0.6  # 600ms


def randomized_election_timeout() -> float:
    return random.uniform(ELECTION_TIMEOUT_MIN, ELECTION_TIMEOUT_MAX)


async def _post_json(
    session: aiohttp.ClientSession, url: str, data: dict, timeout: float = 1.0
):
    try:
        async with session.post(url, json=data, timeout=timeout) as resp:
            if resp.content_type == "application/json":
                return await resp.json()
            return {"status": resp.status}
    except Exception as e:
        return {"error": str(e)}


class RaftRole:
    FOLLOWER = "Follower"
    CANDIDATE = "Candidate"
    LEADER = "Leader"


class Consensus:
    """Lightweight Raft-style consensus for leader election and heartbeats.

    This augments the existing failure detector. It does not replace it.
    """

    def __init__(self, node):
        self.node = node
        # Volatile timers/tasks
        self._election_task: Optional[asyncio.Task] = None
        self._leader_hb_task: Optional[asyncio.Task] = None
        self._election_deadline: float = time.time() + randomized_election_timeout()
        self._lock = asyncio.Lock()

    # --- Task lifecycle ---
    def start(self):
        if self._election_task is None or self._election_task.done():
            self._election_task = asyncio.create_task(self._election_timer_loop())

    async def stop(self):
        if self._election_task:
            self._election_task.cancel()
        if self._leader_hb_task:
            self._leader_hb_task.cancel()

    # --- Timers ---
    async def _election_timer_loop(self):
        while True:
            await asyncio.sleep(0.05)
            now = time.time()
            # Leaders do not trigger elections
            if self.node.role == RaftRole.LEADER:
                continue
            if now >= self._election_deadline:
                await self.start_election()

    def reset_election_timer(self):
        self._election_deadline = time.time() + randomized_election_timeout()

    def _start_leader_heartbeats(self):
        if self._leader_hb_task is None or self._leader_hb_task.done():
            self._leader_hb_task = asyncio.create_task(self._leader_heartbeat_loop())

    async def _leader_heartbeat_loop(self):
        async with aiohttp.ClientSession() as session:
            while self.node.role == RaftRole.LEADER:
                payload = {
                    "term": self.node.current_term,
                    "leaderId": self.node.node_id,
                    "leaderUrl": self.node.base_url,
                    "lastLogIndex": await self.node.get_max_seq(),
                    "lastLogTerm": 0,
                    "entries": [],
                }
                tasks = []
                for p in self.node.peers:
                    tasks.append(
                        _post_json(
                            session,
                            f"{p}/append_entries",
                            payload,
                            timeout=HEARTBEAT_INTERVAL,
                        )
                    )
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.sleep(HEARTBEAT_INTERVAL)

    # --- Elections ---
    async def start_election(self):
        async with self._lock:
            # Step up to candidate
            if self.node.role == RaftRole.LEADER:
                return
            self.node.current_term += 1
            self.node.voted_for = self.node.node_id
            await self.node.persist_term_state()
            self.node.role = RaftRole.CANDIDATE
            self.node.votes_received = 1  # vote for self
            self.reset_election_timer()

            # If majority already satisfied (e.g., single node), become leader immediately
            if self.node.votes_received > self.node.majority_count():
                await self.become_leader()
                return

            # Broadcast RequestVote
            last_index = await self.node.get_max_seq()
            req = {
                "term": self.node.current_term,
                "candidateId": self.node.node_id,
                "candidateUrl": self.node.base_url,
                "lastLogIndex": last_index,
                "lastLogTerm": 0,
            }

        async with aiohttp.ClientSession() as session:
            tasks = [
                _post_json(
                    session, f"{p}/request_vote", req, timeout=ELECTION_TIMEOUT_MAX
                )
                for p in self.node.peers
            ]
            if tasks:
                replies = await asyncio.gather(*tasks, return_exceptions=True)
            else:
                replies = []

        for r in replies:
            if isinstance(r, dict):
                # Step down on higher term
                if r.get("term", 0) > self.node.current_term:
                    await self.become_follower(r["term"])
                    return
                if (
                    self.node.role == RaftRole.CANDIDATE
                    and r.get("term") == self.node.current_term
                    and r.get("voteGranted")
                ):
                    self.node.votes_received += 1
                    if self.node.votes_received > self.node.majority_count():
                        await self.become_leader()
                        return

        # If no majority, keep waiting; timer will trigger new term

    async def become_follower(
        self,
        new_term: int,
        leader_url: Optional[str] = None,
        leader_id: Optional[str] = None,
    ):
        async with self._lock:
            if new_term > self.node.current_term:
                self.node.current_term = new_term
                self.node.voted_for = None
                await self.node.persist_term_state()
            self.node.role = RaftRole.FOLLOWER
            self.node.leader_id = leader_id
            self.node.leader_url = leader_url
            self.reset_election_timer()

    async def become_leader(self):
        async with self._lock:
            self.node.role = RaftRole.LEADER
            self.node.leader_id = self.node.node_id
            self.node.leader_url = self.node.base_url
            self._start_leader_heartbeats()

    # --- RPC Handlers ---
    async def handle_request_vote(self, req: dict) -> dict:
        term = int(req.get("term", 0))
        cand_id = req.get("candidateId")
        cand_url = req.get("candidateUrl")
        last_idx = int(req.get("lastLogIndex", 0))
        # lastLogTerm ignored (no term tracking in log)

        # If term is older, reject
        if term < self.node.current_term:
            return {"term": self.node.current_term, "voteGranted": False}

        # If term is newer, step down
        if term > self.node.current_term:
            await self.become_follower(term)

        # Voting rules
        up_to_date = last_idx >= (await self.node.get_max_seq())
        can_vote = self.node.voted_for is None or self.node.voted_for == cand_id
        if can_vote and up_to_date:
            self.node.voted_for = cand_id
            await self.node.persist_term_state()
            self.reset_election_timer()
            # Track possible leader URL for debugging
            self.node.candidate_url = cand_url
            return {"term": self.node.current_term, "voteGranted": True}
        else:
            return {"term": self.node.current_term, "voteGranted": False}

    async def handle_append_entries(self, hb: dict) -> dict:
        term = int(hb.get("term", 0))
        leader_id = hb.get("leaderId")
        leader_url = hb.get("leaderUrl")

        if term < self.node.current_term:
            return {"term": self.node.current_term, "success": False}

        # If newer or equal term, accept and become follower
        await self.become_follower(term, leader_url=leader_url, leader_id=leader_id)
        return {"term": self.node.current_term, "success": True}
