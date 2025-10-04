import logging

logger = logging.getLogger(__name__)
import aiohttp
import asyncio
import time

HEARTBEAT_INTERVAL = 2.0
HEARTBEAT_TIMEOUT = 6.0  # Add this constant


async def heartbeat_task(app):
    node = app['node']
    async with aiohttp.ClientSession() as sess:
        while True:
            now = time.time()
            for p in node.peers:
                try:
                    async with sess.get(f"{p}/heartbeat", timeout=HEARTBEAT_INTERVAL) as resp:
                        if resp.status == 200:
                            node.failure_detector.mark_alive(p, now)  # Use failure_detector
                except Exception:
                    # Let the failure detector handle timeouts automatically
                    pass

            # Check for failures periodically
            failed_peers = node.failure_detector.check_failures(now)
            for peer in failed_peers:
                logger.warning(f"Node {peer} marked as failed - timeout exceeded")

            await asyncio.sleep(HEARTBEAT_INTERVAL)


async def rejoin_sync(node):
    max_seq = await node.get_max_seq()
    async with aiohttp.ClientSession() as sess:
        alive_peers = node.failure_detector.get_alive_peers()
        targets = alive_peers if alive_peers else node.peers
        for p in targets:
            try:
                async with sess.post(f"{p}/sync", json={"since": max_seq}, timeout=5.0) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for m in data.get("messages", []):
                            seq, _, inserted = await node.store_message(m)
                            if inserted:
                                node.commit_message(seq)
                        node.delivery_metrics['last_recovery_time'] = time.time()
                        return
            except Exception:
                continue