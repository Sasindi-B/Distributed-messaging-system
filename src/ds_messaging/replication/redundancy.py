import aiohttp
import logging

logger = logging.getLogger(__name__)

class RedundancyHandler:
    def __init__(self, node):
        self.node = node  # instance of Node

    async def sync_with_peer(self, peer):
        try:
            my_seq = await self.node.get_max_seq()
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{peer}/sync", json={"since": my_seq}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for msg in data.get("messages", []):
                            await self.node.store_message(msg)
                            await self.node.commit_message(msg["seq"])
                        logger.info(f"Synced {len(data.get('messages', []))} messages from {peer}")
        except Exception as e:
            logger.error(f"Sync with {peer} failed: {e}")

    async def catch_up(self):
        """
        Try syncing with all peers periodically (every 5s).
        """
        import asyncio
        while True:
            for peer in self.node.peers:
                await self.sync_with_peer(peer)
            await asyncio.sleep(5)
