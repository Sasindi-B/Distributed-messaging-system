import logging
logger = logging.getLogger(__name__)
from aiohttp import web
import time
import uuid
from .replication import replicate_to_peers, replicate_with_quorum  # relative import

# ---------------------------
# /send : Producers publish
# ---------------------------
async def send_handler(request):
    node = request.app['node']
    payload = await request.json()
    msg_id = payload.get("msg_id") or str(uuid.uuid4())
    msg = {
        "msg_id": msg_id,
        "sender": payload.get("sender", "unknown"),
        "recipient": payload.get("recipient", "all"),
        "payload": payload.get("payload", ""),
        "ts": payload.get("ts", time.time())
    }

    seq = await node.store_message(msg)
    logger.info(f"Message stored: {msg_id}, seq: {seq}, replicating to {len(node.peers)} peers")

    if node.peers:
        if node.replication_mode == 'async':
            # fire and forget
            request.app.loop.create_task(replicate_to_peers(node, msg))
            await node.commit_message(seq)
        elif node.replication_mode == 'sync_quorum':
            ok = await replicate_with_quorum(node, msg)
            if ok:
                await node.commit_message(seq)
            else:
                return web.json_response(
                    {"status": "error", "reason": "replication quorum not achieved"},
                    status=503
                )

    return web.json_response({"status": "ok", "seq": seq, "msg_id": msg_id})


# ---------------------------
# /replicate : Follower nodes accept replication
# ---------------------------
async def replicate_handler(request):
    node = request.app['node']
    payload = await request.json()
    msg = payload.get("msg")
    if not msg:
        return web.json_response({"status": "bad_request"}, status=400)

    seq = await node.store_message(msg)
    await node.commit_message(seq)  # followers commit immediately
    return web.json_response({"status": "ok", "seq": seq})


# ---------------------------
# /heartbeat : Fault tolerance
# ---------------------------
async def heartbeat_handler(request):
    node = request.app['node']
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
    msgs = await node.get_committed_messages()
    return web.json_response({"messages": msgs})


# ---------------------------
# /status : Node status/debug
# ---------------------------
async def status_handler(request):
    node = request.app['node']
    status = {
        "node_id": node.node_id,
        "port": node.port,
        "peers": node.peers,
        "peer_status": node.failure_detector.peer_status,
        "replication_mode": node.replication_mode,
        "quorum": node.replication_quorum
    }
    return web.json_response(status)
