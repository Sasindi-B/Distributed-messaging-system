import asyncio
import time

from ds_messaging.core.storage import Node
from ds_messaging.failure.consensus import Consensus


def test_append_entries_persists_and_commits_message():
    asyncio.run(_run_append_entries_check())


async def _run_append_entries_check() -> None:
    node = Node("127.0.0.1", 9100, "n1", [])
    node.db_file = ":memory:"
    await node.init_db()

    consensus = Consensus(node)
    node.consensus = consensus

    message = {
        "msg_id": "test-1",
        "sender": "client",
        "recipient": "group",
        "payload": "hello",
        "ts": time.time(),
    }

    payload = {
        "term": 1,
        "leaderId": "n2",
        "leaderUrl": "http://127.0.0.1:9200",
        "leaderCommit": 1,
        "entries": [
            {
                "seq": 1,
                "term": 1,
                "message": message,
            }
        ],
    }

    response = await consensus.handle_append_entries(payload)

    assert response["success"]
    assert node.leader_url == "http://127.0.0.1:9200"
    assert node.committed_seq == 1

    committed = await node.get_committed_messages()
    assert len(committed) == 1
    assert committed[0]["msg_id"] == "test-1"

    await node.db.close()
