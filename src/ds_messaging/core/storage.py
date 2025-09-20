import aiosqlite
import time
from src.ds_messaging.failure.detector import FailureDetector  # Add this import

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

    async def init_db(self):
        self.db = await aiosqlite.connect(self.db_file)
        await self.db.execute(CREATE_SQL)
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