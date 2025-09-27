from src.ds_messaging.replication import Replicator

class ReplicationManager:
    """
    Orchestrates replication according to mode (async or quorum).
    """

    def __init__(self, peers, quorum=2, mode="async"):
        self.peers = peers
        self.quorum = quorum
        self.mode = mode
        self.replicator = Replicator(peers, quorum, mode)

    async def replicate_message(self, message: dict) -> bool:
        """
        Replicate a message and return True if commit condition is satisfied.
        """
        return await self.replicator.replicate_to_followers(message)
