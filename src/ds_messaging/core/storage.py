import json
import time
from collections import deque

import aiosqlite
from typing import Optional, Dict, Any, List

from src.ds_messaging.failure.detector import FailureDetector
from src.ds_messaging.time import (
    TimeSync,
    ClockSkewAnalyzer,
    TimestampCorrector,
    MessageOrderingBuffer,
    TimedMessage,
)

DB_FILE = "messages.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id TEXT UNIQUE,
    sender TEXT,
    recipient TEXT,
    payload TEXT,
    ts REAL,
    original_ts REAL,
    corrected_ts REAL,
    receive_ts REAL,
    correction_metadata TEXT
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

SELECT_SINCE = """
SELECT seq, msg_id, sender, recipient, payload, ts, original_ts, corrected_ts, receive_ts, correction_metadata
FROM messages WHERE seq > ? ORDER BY seq ASC;
"""

SELECT_MAX_SEQ = "SELECT IFNULL(MAX(seq), 0) FROM messages;"

INSERT_MSG = """
INSERT OR IGNORE INTO messages (msg_id, sender, recipient, payload, ts, original_ts, corrected_ts, receive_ts, correction_metadata)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

CREATE_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient, corrected_ts)",
    "CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender, corrected_ts)",
]


class Node:
    def __init__(self, host, port, node_id, peers,
                 replication_quorum=1, replication_mode='async'):
        self.host = host
        self.port = port
        self.node_id = node_id
        self.base_url = f"http://{host}:{port}"
        self.peers = peers[:]  # list of peer base URLs

        # failure detector for heartbeats
        self.failure_detector = FailureDetector(peers)

        # time synchronization / ordering components
        self.time_sync = TimeSync(peers)
        self.clock_analyzer = ClockSkewAnalyzer()
        self.timestamp_corrector = TimestampCorrector(self.time_sync, self.clock_analyzer)
        self.message_buffer = MessageOrderingBuffer()
        self.delivered_messages = deque(maxlen=256)
        self.delivery_metrics: Dict[str, Any] = {
            "correction_magnitudes": [],
            "store_latencies": [],
            "last_recovery_time": None,
        }

        # replication settings
        self.replication_mode = replication_mode
        self.replication_quorum = replication_quorum

        # separate DB file per node (so multiple nodes can run on one machine)
        self.db_file = f"{DB_FILE}.{port}"

        # Consensus state (Raft)
        self.role: str = "Follower"
        self.current_term: int = 0
        self.voted_for: Optional[str] = None
        self.leader_id: Optional[str] = None
        self.leader_url: Optional[str] = None
        self.votes_received: int = 0
        self.consensus = None  # set by server on startup
        self.commit_index: int = 0

        # replication consistency tracking
        self.committed_seq = 0

    async def init_db(self):
        self.db = await aiosqlite.connect(self.db_file)
        await self.db.execute(CREATE_SQL)
        await self.db.execute(CREATE_RAFT_SQL)
        await self._ensure_extended_schema()
        for stmt in CREATE_INDEX_SQL:
            await self.db.execute(stmt)
        await self.db.commit()
        await self._load_raft_state()
        # initialize committed sequence to what's already stored
        self.committed_seq = await self.get_max_seq()

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

    async def _ensure_extended_schema(self) -> None:
        required_columns = [
            ("original_ts", "REAL", "0"),
            ("corrected_ts", "REAL", "0"),
            ("receive_ts", "REAL", "0"),
            ("correction_metadata", "TEXT", "'{}'"),
        ]
        cur = await self.db.execute("PRAGMA table_info(messages);")
        rows = await cur.fetchall()
        existing = {row[1] for row in rows}
        for name, col_type, default in required_columns:
            if name not in existing:
                await self.db.execute(
                    f"ALTER TABLE messages ADD COLUMN {name} {col_type} DEFAULT {default};"
                )

    async def persist_term_state(self):
        await self.db.execute(UPSERT_RAFT_SQL, (self.current_term, self.voted_for))
        await self.db.commit()

    async def store_message(self, msg: Dict[str, Any]):
        """Store a message locally after applying time correction metadata.

        Returns a tuple ``(seq, stored_msg, inserted)`` where ``inserted`` is a
        boolean indicating whether a new row was persisted (``False`` implies
        the message was already present, typically through replication).
        """
        start = time.time()
        prepared = self.prepare_message(msg)

        cursor = await self.db.execute(
            INSERT_MSG,
            (
                prepared['msg_id'],
                prepared['sender'],
                prepared['recipient'],
                prepared['payload'],
                prepared['ts'],
                prepared['original_ts'],
                prepared['corrected_ts'],
                prepared['receive_ts'],
                json.dumps(prepared.get('correction_info', {})),
            )
        )
        inserted = cursor.rowcount > 0
        await self.db.commit()

        cur = await self.db.execute(
            "SELECT seq, msg_id, sender, recipient, payload, ts, original_ts, corrected_ts, receive_ts, correction_metadata "
            "FROM messages WHERE msg_id = ?;",
            (prepared['msg_id'],),
        )
        row = await cur.fetchone()
        stored_msg = self._row_to_message(row)
        seq = stored_msg['seq']
        if 'correction_metadata' in stored_msg:
            stored_msg.setdefault('correction_info', stored_msg['correction_metadata'])

        if inserted:
            self._register_for_ordering(stored_msg)
            self.delivery_metrics['store_latencies'].append(time.time() - start)
            if len(self.delivery_metrics['store_latencies']) > 512:
                self.delivery_metrics['store_latencies'].pop(0)

        return seq, stored_msg, inserted

    def prepare_message(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        prepared = dict(msg)
        now = time.time()

        prepared.setdefault('sender', 'unknown')
        prepared.setdefault('recipient', 'all')
        prepared.setdefault('payload', '')

        original_ts = prepared.get('original_ts')
        if original_ts is None:
            original_ts = float(prepared.get('ts', now))

        corrected_ts = prepared.get('corrected_ts')
        correction_info = prepared.get('correction_info') or {}

        if corrected_ts is None:
            corrected_ts = original_ts
            if self.timestamp_corrector:
                corrected_ts, info = self.timestamp_corrector.correct_timestamp(
                    original_ts, prepared.get('sender')
                )
                correction_info.update(info)
                accuracy = self.timestamp_corrector.estimate_accuracy(
                    corrected_ts, original_ts, prepared.get('sender')
                )
                correction_info['accuracy'] = accuracy
        else:
            if self.timestamp_corrector and 'accuracy' not in correction_info:
                accuracy = self.timestamp_corrector.estimate_accuracy(
                    corrected_ts, original_ts, prepared.get('sender')
                )
                correction_info['accuracy'] = accuracy

        prepared['original_ts'] = original_ts
        prepared['corrected_ts'] = corrected_ts
        prepared['ts'] = corrected_ts
        prepared['receive_ts'] = prepared.get('receive_ts', now)
        if correction_info:
            prepared['correction_info'] = correction_info
            magnitude = correction_info.get('magnitude')
            if magnitude is not None:
                self.delivery_metrics['correction_magnitudes'].append(magnitude)
                if len(self.delivery_metrics['correction_magnitudes']) > 512:
                    self.delivery_metrics['correction_magnitudes'].pop(0)

        return prepared

    def _register_for_ordering(self, message: Dict[str, Any]) -> None:
        timed_message = TimedMessage(
            msg_id=message['msg_id'],
            sender=message.get('sender', 'unknown'),
            recipient=message.get('recipient', 'all'),
            payload=message.get('payload', ''),
            original_timestamp=message['original_ts'],
            corrected_timestamp=message['corrected_ts'],
            receive_timestamp=message['receive_ts'],
            sequence_number=message.get('seq'),
            vector_clock=message.get('vector_clock'),
        )

        added = self.message_buffer.add_message(timed_message)
        if added:
            deliverable = self.message_buffer.get_deliverable_messages()
            if deliverable:
                self.delivered_messages.extend(deliverable)
                self.delivery_metrics['last_delivery_time'] = time.time()

    async def get_messages_since(self, seq):
        """
        Fetch all messages with sequence number greater than `seq`.
        Used for redundancy catch-up.
        """
        cur = await self.db.execute(SELECT_SINCE, (seq,))
        rows = await cur.fetchall()
        return [self._row_to_message(r) for r in rows]

    async def get_max_seq(self):
        cur = await self.db.execute(SELECT_MAX_SEQ)
        row = await cur.fetchone()
        return row[0]

    def majority_count(self) -> int:
        # number of nodes in cluster / 2 (floor) for majority comparison, return threshold (N//2)
        # When comparing votes > threshold, it implies (> N/2)
        n = 1 + len(self.peers)
        return n // 2

    def commit_message(self, seq: int) -> None:
        """Mark messages up to `seq` as committed."""
        if seq > self.committed_seq:
            self.committed_seq = seq
            self.commit_index = seq

    async def get_committed_messages(
        self,
        *,
        limit: Optional[int] = None,
        after_seq: Optional[int] = None,
        sender: Optional[str] = None,
        recipient: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch committed messages with optional pagination and filtering."""

        clauses = ["seq <= ?"]
        params: List[Any] = [self.committed_seq]

        if after_seq is not None:
            clauses.append("seq > ?")
            params.append(after_seq)
        if sender:
            clauses.append("sender = ?")
            params.append(sender)
        if recipient:
            clauses.append("recipient = ?")
            params.append(recipient)

        where_clause = " AND ".join(clauses)
        query = (
            "SELECT seq, msg_id, sender, recipient, payload, ts, original_ts, corrected_ts, receive_ts, correction_metadata "
            f"FROM messages WHERE {where_clause} ORDER BY seq ASC"
        )
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        cur = await self.db.execute(query, params)
        rows = await cur.fetchall()
        return [self._row_to_message(r) for r in rows]

    async def get_log_entries_since(self, seq: int, limit: int = 32) -> List[Dict[str, Any]]:
        """Return committed log entries with seq greater than ``seq``."""

        cur = await self.db.execute(
            "SELECT seq, msg_id, sender, recipient, payload, ts, original_ts, corrected_ts, receive_ts, correction_metadata "
            "FROM messages WHERE seq > ? AND seq <= ? ORDER BY seq ASC LIMIT ?;",
            (seq, self.committed_seq, limit),
        )
        rows = await cur.fetchall()
        return [self._row_to_message(r) for r in rows]

    @staticmethod
    def _row_to_message(row: List[Any]) -> Dict[str, Any]:
        metadata = row[9] if len(row) > 9 else None
        return {
            "seq": row[0],
            "msg_id": row[1],
            "sender": row[2],
            "recipient": row[3],
            "payload": row[4],
            "ts": row[5],
            "original_ts": row[6],
            "corrected_ts": row[7],
            "receive_ts": row[8],
            "correction_metadata": json.loads(metadata) if metadata else {},
        }
