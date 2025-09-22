import aiosqlite
import time
from src.ds_messaging.failure.detector import FailureDetector  # Add this import
from typing import Optional

DB_FILE = "messages.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id TEXT UNIQUE,
    sender TEXT,
    recipient TEXT,
    payload TEXT,
    ts REAL
);
"""

CREATE_RAFT_SQL = """
CREATE TABLE IF NOT EXISTS raft_state (
    id INTEGER PRIMARY KEY CHECK (id=1),
    current_term INTEGER NOT NULL,
    voted_for TEXT
);
"""

UPSERT_RAFT_SQL = """
INSERT INTO raft_state (id, current_term, voted_for)
VALUES (1, ?, ?)
ON CONFLICT(id) DO UPDATE SET current_term=excluded.current_term, voted_for=excluded.voted_for;
"""

SELECT_RAFT_SQL = "SELECT current_term, voted_for FROM raft_state WHERE id=1;"

SELECT_SINCE = "SELECT seq, msg_id, sender, recipient, payload, ts FROM messages WHERE seq > ? ORDER BY seq ASC;"
SELECT_MAX_SEQ = "SELECT IFNULL(MAX(seq), 0) FROM messages;"
INSERT_MSG = "INSERT OR IGNORE INTO messages (msg_id, sender, recipient, payload, ts) VALUES (?, ?, ?, ?, ?);"


class Node:
    def __init__(self, host, port, node_id, peers, replication_quorum=1, replication_mode='async'):
        self.host = host
        self.port = port
        self.node_id = node_id
        self.base_url = f"http://{host}:{port}"
        self.peers = peers[:]  # list of peer base URLs

        # Add FailureDetector
        self.failure_detector = FailureDetector(peers)

        self.replication_mode = replication_mode  # 'async' or 'sync_quorum'
        self.replication_quorum = replication_quorum
        self.db_file = f"{DB_FILE}.{port}"

        # Consensus state (Raft)
        self.role: str = "Follower"
        self.current_term: int = 0
        self.voted_for: Optional[str] = None
        self.leader_id: Optional[str] = None
        self.leader_url: Optional[str] = None
        self.votes_received: int = 0
        self.consensus = None  # set by server on startup

    async def init_db(self):
        self.db = await aiosqlite.connect(self.db_file)
        await self.db.execute(CREATE_SQL)
        await self.db.execute(CREATE_RAFT_SQL)
        await self.db.commit()
        await self._load_raft_state()

    async def _load_raft_state(self):
        cur = await self.db.execute(SELECT_RAFT_SQL)
        row = await cur.fetchone()
        if row is None:
            # Initialize default state
            self.current_term = 0
            self.voted_for = None
            await self.db.execute(UPSERT_RAFT_SQL, (self.current_term, self.voted_for))
            await self.db.commit()
        else:
            self.current_term = int(row[0] or 0)
            self.voted_for = row[1]

    async def persist_term_state(self):
        await self.db.execute(UPSERT_RAFT_SQL, (self.current_term, self.voted_for))
        await self.db.commit()

    async def store_message(self, msg):
        await self.db.execute(INSERT_MSG, (msg['msg_id'], msg['sender'], msg['recipient'], msg['payload'], msg['ts']))
        await self.db.commit()
        cur = await self.db.execute(SELECT_MAX_SEQ)
        row = await cur.fetchone()
        return row[0]

    async def get_messages_since(self, seq):
        cur = await self.db.execute(SELECT_SINCE, (seq,))
        rows = await cur.fetchall()
        return [{"seq": r[0], "msg_id": r[1], "sender": r[2],
                 "recipient": r[3], "payload": r[4], "ts": r[5]} for r in rows]

    async def get_max_seq(self):
        cur = await self.db.execute(SELECT_MAX_SEQ)
        row = await cur.fetchone()
        return row[0]

    def majority_count(self) -> int:
        # number of nodes in cluster / 2 (floor) for majority comparison, return threshold (N//2)
        # When comparing votes > threshold, it implies (> N/2)
        n = 1 + len(self.peers)
        return n // 2
