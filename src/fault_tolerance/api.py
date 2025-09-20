from aiohttp import web
import time
import uuid
from replication import replicate_to_peers, replicate_with_quorum

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
    if node.peers:
        if node.replication_mode == 'async':
            request.app.loop.create_task(replicate_to_peers(node, msg))
        elif node.replication_mode == 'sync_quorum':
            ok = await replicate_with_quorum(node, msg)
            if not ok:
                return web.json_response({"status": "error", "reason": "replication quorum not achieved"}, status=503)
    return web.json_response({"status": "ok", "seq": seq, "msg_id": msg_id})

async def replicate_handler(request):
    node = request.app['node']
    payload = await request.json()
    msg = payload.get("msg")
    if not msg:
        return web.json_response({"status": "bad_request"}, status=400)
    seq = await node.store_message(msg)
    return web.json_response({"status": "ok", "seq": seq})

async def heartbeat_handler(request):
    node = request.app['node']
    return web.json_response({"status": "ok", "node_id": node.node_id, "time": time.time()})

async def sync_handler(request):
    node = request.app['node']
    payload = await request.json()
    since = int(payload.get("since", 0))
    msgs = await node.get_messages_since(since)
    return web.json_response({"messages": msgs})

async def messages_handler(request):
    node = request.app['node']
    rows = await node.db.execute("SELECT seq, msg_id, sender, recipient, payload, ts FROM messages ORDER BY seq ASC;")
    rows = await rows.fetchall()
    return web.json_response({"messages": [
        {"seq": r[0], "msg_id": r[1], "sender": r[2], "recipient": r[3], "payload": r[4], "ts": r[5]} for r in rows
    ]})
