import aiohttp
import asyncio

REPL_TIMEOUT = 3.0


async def _post_json(sess, url, data, timeout=REPL_TIMEOUT):
    try:
        async with sess.post(url, json=data, timeout=timeout) as resp:
            return await resp.json()
    except Exception as e:
        return e


async def replicate_to_peers(node, msg):
    async with aiohttp.ClientSession() as sess:
        # Use failure_detector to get alive peers
        alive_peers = node.failure_detector.get_alive_peers()
        tasks = [_post_json(sess, f"{p}/replicate", {"msg": msg}) for p in alive_peers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for p, r in zip(alive_peers, results):
            if isinstance(r, Exception):
                # Mark as failed if replication fails
                node.failure_detector.peer_status[p]['alive'] = False


async def replicate_with_quorum(node, msg):
    needed = node.replication_quorum
    acks = 1  # local write counts

    async with aiohttp.ClientSession() as sess:
        # Use failure_detector to get alive peers
        alive_peers = node.failure_detector.get_alive_peers()
        tasks = [_post_json(sess, f"{p}/replicate", {"msg": msg}) for p in alive_peers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, dict) and r.get("status") == "ok":
                acks += 1
            if acks >= needed:
                return True
    return False