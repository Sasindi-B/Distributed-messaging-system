import aiohttp
import asyncio
import time

HEARTBEAT_INTERVAL = 2.0
HEARTBEAT_TIMEOUT = 6.0

async def heartbeat_task(app):
    node = app['node']
    async with aiohttp.ClientSession() as sess:
        while True:
            now = time.time()
            for p in node.peers:
                try:
                    async with sess.get(f"{p}/heartbeat", timeout=HEARTBEAT_INTERVAL) as resp:
                        if resp.status == 200:
                            node.peer_status[p]['last_ok'] = now
                            node.peer_status[p]['alive'] = True
                except Exception:
                    if now - node.peer_status[p]['last_ok'] > HEARTBEAT_TIMEOUT:
                        node.peer_status[p]['alive'] = False

async def rejoin_sync(node):
    max_seq = await node.get_max_seq()
    async with aiohttp.ClientSession() as sess:
        for p in node.peers:
            try:
                async with sess.post(f"{p}/sync", json={"since": max_seq}, timeout=5.0) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for m in data.get("messages", []):
                            await node.store_message(m)
                        return
            except Exception:
                continue
