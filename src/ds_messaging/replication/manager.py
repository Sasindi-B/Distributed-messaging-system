import logging
from src.ds_messaging.failure.replication import replicate_to_peers, replicate_with_quorum

logger = logging.getLogger(__name__)

class ReplicationManager:
    """
    Orchestrates replication according to the node's mode (async or quorum).
    """

    def __init__(self, node):
        """
        :param node: Node object with peers, replication_mode, replication_quorum
        """
        self.node = node

    async def replicate_message(self, msg, loop=None):
        """
        Replicate a message to peers depending on replication mode.

        :param msg: message dict to replicate
        :param loop: optional asyncio loop (for async fire-and-forget)
        :return: True if committed (quorum) or always True (async)
        """
        if not self.node.peers:
            logger.info("No peers configured, skipping replication.")
            return True

        if self.node.replication_mode == 'async':
            # Fire-and-forget replication
            if loop:
                loop.create_task(replicate_to_peers(self.node, msg))
            else:
                import asyncio
                asyncio.create_task(replicate_to_peers(self.node, msg))
            return True

        elif self.node.replication_mode == 'sync_quorum':
            # Wait for quorum acknowledgments
            ok = await replicate_with_quorum(self.node, msg)
            if ok:
                logger.info("Quorum replication successful.")
            else:
                logger.warning("Quorum replication failed.")
            return ok

        else:
            logger.error(f"Unknown replication mode: {self.node.replication_mode}")
            return False
