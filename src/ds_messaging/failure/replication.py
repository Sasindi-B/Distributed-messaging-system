import aiohttp
import asyncio
import logging

REPL_TIMEOUT = 3.0
logger = logging.getLogger(__name__)


async def _post_json(sess, url, data, timeout=REPL_TIMEOUT):
    """
    Helper: POST JSON data to a peer with timeout.
    Returns JSON response or an Exception.
    """
    try:
        async with sess.post(url, json=data, timeout=timeout) as resp:
            return await resp.json()
    except Exception as e:
        logger.error(f"Replication POST to {url} failed: {e}")
        return e


async def replicate_to_peers(node, msg):
    """
    Fire-and-forget replication.
    Leader sends to all alive peers but does not wait for ACKs.
    """
    async with aiohttp.ClientSession() as sess:
        alive_peers = node.failure_detector.get_alive_peers()
        tasks = [_post_json(sess, f"{p}/replicate", {"msg": msg}) for p in alive_peers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for p, r in zip(alive_peers, results):
            if isinstance(r, Exception):
                # Mark peer as failed if replication fails
                node.failure_detector.peer_status[p]['alive'] = False
                logger.warning(f"Replication to {p} failed, marking as down")


async def replicate_with_quorum(node, msg):
    """
    Quorum-based replication.
    Leader sends to all alive peers and waits for enough ACKs.
    """
    needed = node.replication_quorum
    acks = 1  # local write counts

    async with aiohttp.ClientSession() as sess:
        alive_peers = node.failure_detector.get_alive_peers()
        tasks = [_post_json(sess, f"{p}/replicate", {"msg": msg}) for p in alive_peers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, dict) and r.get("status") == "ok":
                acks += 1
                if acks >= needed:
                    logger.info(f"Replication quorum achieved: {acks}/{needed}")
                    return True

    logger.warning(f"Replication quorum NOT achieved: {acks}/{needed}")
    return False
