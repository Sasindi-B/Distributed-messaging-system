import asyncio
import random
import time
from collections import deque
from typing import Optional, List, Dict

import aiohttp


# Timers (seconds)
HEARTBEAT_INTERVAL = 0.2  # 200ms
ELECTION_TIMEOUT_MIN = 0.3  # 300ms
ELECTION_TIMEOUT_MAX = 0.6  # 600ms


def randomized_election_timeout() -> float:
    return random.uniform(ELECTION_TIMEOUT_MIN, ELECTION_TIMEOUT_MAX)


async def _post_json(
    session: aiohttp.ClientSession, url: str, data: dict
):
    try:
        async with session.post(url, json=data) as resp:
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
        self._pending_entries = deque()
        self._max_batch_size = 32

    # --- Task lifecycle ---
    def start(self):
        if self._election_task is None or self._election_task.done():
            self._election_task = asyncio.create_task(self._election_timer_loop())

    async def stop(self):
        tasks = []
        if self._election_task:
            self._election_task.cancel()
            tasks.append(self._election_task)
            self._election_task = None
        if self._leader_hb_task:
            self._leader_hb_task.cancel()
            tasks.append(self._leader_hb_task)
            self._leader_hb_task = None
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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

    def _collect_pending_entries(self) -> List[Dict[str, object]]:
        pending = [entry for entry in self._pending_entries if not entry.get("delivered")]
        payload = []
        for entry in pending[: self._max_batch_size]:
            payload.append(
                {
                    "seq": entry["seq"],
                    "term": entry["term"],
                    "message": entry["message"],
                }
            )
        return payload

    def _handle_append_entries_responses(
        self,
        entries_payload: List[Dict[str, object]],
        responses: List[dict],
    ) -> None:
        if not entries_payload:
            return

        success_responses = sum(
            1 for r in responses if isinstance(r, dict) and r.get("success")
        )
        has_majority = success_responses + 1 > self.node.majority_count()

        if has_majority:
            self._mark_entries_delivered(entries_payload)
        else:
            self._reset_delivery_flags()

    def _mark_entries_delivered(self, entries_payload: List[Dict[str, object]]) -> None:
        delivered_ids = {entry["seq"] for entry in entries_payload}
        for entry in self._pending_entries:
            if entry["seq"] in delivered_ids:
                entry["delivered"] = True
        while self._pending_entries and self._pending_entries[0].get("delivered"):
            self._pending_entries.popleft()

    def _reset_delivery_flags(self) -> None:
        for entry in self._pending_entries:
            if entry.get("delivered"):
                entry["delivered"] = False

    async def _leader_heartbeat_loop(self):
        async with aiohttp.ClientSession() as session:
            while self.node.role == RaftRole.LEADER:
                entries_payload = self._collect_pending_entries()

                payload = {
                    "term": self.node.current_term,
                    "leaderId": self.node.node_id,
                    "leaderUrl": self.node.base_url,
                    "lastLogIndex": await self.node.get_max_seq(),
                    "lastLogTerm": 0,
                    "prevLogIndex": entries_payload[0]["seq"] - 1 if entries_payload else self.node.commit_index,
                    "entries": entries_payload,
                    "leaderCommit": self.node.commit_index,
                }
                tasks = []
                for p in self.node.peers:
                    tasks.append(
                        self._post_with_timeout(
                            session, f"{p}/append_entries", payload, HEARTBEAT_INTERVAL
                        )
                    )
                if tasks:
                    responses = await asyncio.gather(*tasks, return_exceptions=True)
                    filtered = [r for r in responses if isinstance(r, dict)]
                    self._handle_append_entries_responses(entries_payload, filtered)
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

        replies = await self._broadcast_request_vote(req)
        await self._process_vote_replies(replies)

        # If no majority, keep waiting; timer will trigger new term

    async def _broadcast_request_vote(self, req: dict) -> List[dict]:
        if not self.node.peers:
            return []
        async with aiohttp.ClientSession() as session:
            tasks = [
                self._post_with_timeout(
                    session, f"{p}/request_vote", req, ELECTION_TIMEOUT_MAX
                )
                for p in self.node.peers
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in responses if isinstance(r, dict)]

    async def _process_vote_replies(self, replies: List[dict]) -> None:
        for reply in replies:
            higher_term = reply.get("term", 0) > self.node.current_term
            if higher_term:
                await self.become_follower(reply.get("term", self.node.current_term))
                return
            vote_granted = (
                self.node.role == RaftRole.CANDIDATE
                and reply.get("term") == self.node.current_term
                and reply.get("voteGranted")
            )
            if vote_granted:
                self.node.votes_received += 1
                if self.node.votes_received > self.node.majority_count():
                    await self.become_leader()
                    return

    async def _post_with_timeout(
        self,
        session: aiohttp.ClientSession,
        url: str,
        data: dict,
        timeout_seconds: float,
    ) -> dict:
        try:
            async with asyncio.timeout(timeout_seconds):
                return await _post_json(session, url, data)
        except asyncio.TimeoutError:
            return {"error": "timeout"}

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
            for entry in self._pending_entries:
                entry["delivered"] = False
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

        entries = hb.get("entries", []) or []
        last_applied = self.node.committed_seq
        if entries:
            for entry in entries:
                message = entry.get("message")
                if not isinstance(message, dict):
                    continue
                seq, _, inserted = await self.node.store_message(message)
                if inserted:
                    last_applied = max(last_applied, seq)

        leader_commit = int(hb.get("leaderCommit", self.node.commit_index))
        if leader_commit > self.node.committed_seq:
            self.node.commit_message(leader_commit)

        return {"term": self.node.current_term, "success": True, "matchIndex": last_applied}

    def register_log_entry(self, seq: int, stored_msg: dict) -> None:
        if self.node.role != RaftRole.LEADER:
            return
        msg_id = stored_msg.get("msg_id")
        if any(entry.get("message", {}).get("msg_id") == msg_id for entry in self._pending_entries):
            return
        message = dict(stored_msg)
        self._pending_entries.append(
            {
                "seq": seq,
                "term": self.node.current_term,
                "message": message,
                "delivered": False,
            }
        )
        while len(self._pending_entries) > 256:
            self._pending_entries.popleft()

