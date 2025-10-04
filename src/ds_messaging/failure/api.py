import logging
logger = logging.getLogger(__name__)
from aiohttp import web
import time
import uuid
import asyncio
import statistics
from src.ds_messaging.failure.replication import replicate_to_peers, replicate_with_quorum

# ---------------------------
# /send : Producers publish
# ---------------------------
async def send_handler(request):
    node = request.app['node']
    payload = await request.json()
    msg_id = payload.get("msg_id") or str(uuid.uuid4())

    if node.role != "Leader" and node.leader_url and node.leader_url != node.base_url:
        return web.json_response(
            {
                "status": "redirect",
                "leader_url": node.leader_url,
                "reason": "node_is_not_leader",
            },
            status=307,
        )

    msg = {
        "msg_id": msg_id,
        "sender": payload.get("sender", "unknown"),
        "recipient": payload.get("recipient", "all"),
        "payload": payload.get("payload", ""),
        "ts": payload.get("ts", time.time())
    }

    seq, stored_msg, inserted = await node.store_message(msg)
    logger.info(f"Message stored: {msg_id}, seq: {seq}, replicating to {len(node.peers)} peers")

    if inserted and node.consensus:
        node.consensus.register_log_entry(seq, stored_msg)

    if node.peers:
        if node.replication_mode == 'async':
            # fire and forget
            request.app.loop.create_task(replicate_to_peers(node, stored_msg))
            node.commit_message(seq)
        elif node.replication_mode == 'sync_quorum':
            ok = await replicate_with_quorum(node, stored_msg)
            if ok:
                node.commit_message(seq)
            else:
                return web.json_response(
                    {"status": "error", "reason": "replication quorum not achieved"},
                    status=503
                )

    return web.json_response({
        "status": "ok",
        "seq": seq,
        "msg_id": msg_id,
        "corrected_ts": stored_msg.get('corrected_ts'),
        "original_ts": stored_msg.get('original_ts'),
        "correction": stored_msg.get('correction_info', {}),
    })


# ---------------------------
# /replicate : Follower nodes accept replication
# ---------------------------
async def replicate_handler(request):
    node = request.app['node']
    payload = await request.json()
    msg = payload.get("msg")
    if not msg:
        return web.json_response({"status": "bad_request"}, status=400)

    seq, stored_msg, inserted = await node.store_message(msg)
    if inserted:
        node.commit_message(seq)  # followers commit immediately
    return web.json_response({"status": "ok", "seq": seq, "msg_id": stored_msg.get('msg_id')})


# ---------------------------
# /heartbeat : Fault tolerance
# ---------------------------
async def heartbeat_handler(request):
    node = request.app['node']
    await asyncio.sleep(0)
    return web.json_response({"status": "ok", "node_id": node.node_id, "time": time.time()})


# ---------------------------
# /sync : Used by redundancy catch-up
# ---------------------------
async def sync_handler(request):
    node = request.app['node']
    payload = await request.json()
    since = int(payload.get("since", 0))
    msgs = await node.get_messages_since(since)
    return web.json_response({"messages": msgs})


# ---------------------------
# /messages : Consumers fetch committed messages
# ---------------------------
async def messages_handler(request):
    node = request.app['node']
    try:
        limit = int(request.query.get("limit", "50"))
        if limit <= 0:
            raise ValueError
    except ValueError:
        return web.json_response({"status": "bad_request", "reason": "limit must be positive integer"}, status=400)

    after_seq = request.query.get("after")
    sender = request.query.get("sender")
    recipient = request.query.get("recipient")
    try:
        after_val = int(after_seq) if after_seq is not None else None
    except ValueError:
        return web.json_response({"status": "bad_request", "reason": "after must be integer"}, status=400)

    msgs = await node.get_committed_messages(
        limit=limit,
        after_seq=after_val,
        sender=sender,
        recipient=recipient,
    )
    return web.json_response({"messages": msgs, "next_after": msgs[-1]['seq'] if msgs else after_val})


# ---------------------------
# /status : Node status/debug
# ---------------------------
async def status_handler(request):
    node = request.app['node']
    await asyncio.sleep(0)
    latencies = node.delivery_metrics.get('store_latencies', [])
    avg_latency = statistics.mean(latencies) if latencies else 0.0
    correction_magnitudes = node.delivery_metrics.get('correction_magnitudes', [])
    avg_correction = statistics.mean(correction_magnitudes) if correction_magnitudes else 0.0
    status = {
        "node_id": node.node_id,
        "port": node.port,
        "peers": node.peers,
        "peer_status": node.failure_detector.peer_status,
        "replication_mode": node.replication_mode,
        "quorum": node.replication_quorum,
        "committed_seq": node.committed_seq,
        "commit_index": node.commit_index,
        "metrics": {
            "average_store_latency": avg_latency,
            "average_correction_magnitude": avg_correction,
            "last_recovery_time": node.delivery_metrics.get('last_recovery_time'),
        },
        "recent_deliveries": [
            {
                "msg_id": msg.msg_id,
                "corrected_timestamp": msg.corrected_timestamp,
                "sender": msg.sender,
            }
            for msg in list(node.delivered_messages)[-5:]
        ],
        "consensus": {
            "role": node.role,
            "current_term": node.current_term,
            "voted_for": node.voted_for,
            "leader_id": node.leader_id,
            "leader_url": node.leader_url,
        },
        "time_sync": node.time_sync.get_sync_status() if node.time_sync else {},
    }
    return web.json_response(status)


# --- Consensus RPC handlers ---
async def request_vote_handler(request):
    node = request.app['node']
    payload = await request.json()
    resp = await node.consensus.handle_request_vote(payload)
    return web.json_response(resp)


async def append_entries_handler(request):
    node = request.app['node']
    payload = await request.json()
    resp = await node.consensus.handle_append_entries(payload)
    return web.json_response(resp)
