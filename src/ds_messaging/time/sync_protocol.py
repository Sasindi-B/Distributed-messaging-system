import time
import asyncio
import aiohttp
import logging
from typing import Dict, List, Optional, Tuple
from statistics import median

logger = logging.getLogger(__name__)


class TimeSync:
    """
    Implements NTP-style time synchronization for distributed messaging system.
    Handles clock offset calculation, network delay compensation, and synchronization accuracy.
    """
    
    def __init__(self, peers: List[str], sync_interval: float = 30.0, max_offset: float = 1.0):
        self.peers = peers
        self.sync_interval = sync_interval
        self.max_offset = max_offset  # Maximum acceptable clock offset in seconds
        
        # Synchronization state
        self.clock_offset = 0.0  # Offset to add to local time to get synchronized time
        self.network_delay = 0.0  # Estimated network delay
        self.last_sync_time = 0.0
        self.sync_accuracy = 0.0  # Estimated synchronization accuracy
        
        # Drift rate computation
        self.drift_rate = 0.0  # Clock drift in seconds per second
        self.offset_history: List[Tuple[float, float]] = []  # (timestamp, offset) pairs
        self.max_history_size = 20  # Keep last 20 measurements for drift calculation
        
        # Peer time data
        self.peer_offsets: Dict[str, float] = {}
        self.peer_delays: Dict[str, float] = {}
        self.peer_last_sync: Dict[str, float] = {}
        
        # Statistics
        self.sync_attempts = 0
        self.successful_syncs = 0
        
    def get_synchronized_time(self) -> float:
        """Get current synchronized time accounting for calculated offset"""
        return time.time() + self.clock_offset
    
    def is_synchronized(self) -> bool:
        """Check if the clock is currently synchronized within acceptable bounds"""
        time_since_sync = time.time() - self.last_sync_time
        return time_since_sync < self.sync_interval * 2 and abs(self.clock_offset) < self.max_offset
    
    async def sync_with_peer(self, peer: str, session: aiohttp.ClientSession) -> Optional[Tuple[float, float]]:
        """
        Perform NTP-style time synchronization with a single peer.
        Returns (offset, delay) tuple or None if synchronization fails.
        """
        try:
            # Record timestamps for NTP-style calculation
            t1 = time.time()  # Client send time
            
            async with session.get(f"{peer}/time", timeout=5.0) as resp:
                if resp.status != 200:
                    return None
                    
                t4 = time.time()  # Client receive time
                data = await resp.json()
                
                t2 = data.get('server_receive_time', t1)  # Server receive time
                t3 = data.get('server_send_time', t4)     # Server send time
                
                # NTP offset and delay calculation
                # offset = ((t2 - t1) + (t3 - t4)) / 2
                # delay = (t4 - t1) - (t3 - t2)
                offset = ((t2 - t1) + (t3 - t4)) / 2
                delay = (t4 - t1) - (t3 - t2)
                
                # Validate measurements
                if delay < 0 or delay > 1.0:  # Reject unrealistic delays
                    logger.warning(f"Rejected time sync with {peer}: invalid delay {delay}")
                    return None
                
                logger.debug(f"Time sync with {peer}: offset={offset:.6f}s, delay={delay:.6f}s")
                return (offset, delay)
                
        except Exception as e:
            logger.warning(f"Time sync with {peer} failed: {e}")
            return None
    
    async def synchronize_with_peers(self, node=None) -> bool:
        """
        Synchronize time with all available peers using NTP-style algorithm.
        Returns True if synchronization was successful.
        """
        if not self.peers:
            return False
        
        # Filter peers using failure detector if available (like replication module)
        target_peers = self.peers
        if node and hasattr(node, 'failure_detector'):
            alive_peers = node.failure_detector.get_alive_peers()
            target_peers = [peer for peer in self.peers if peer in alive_peers]
            if not target_peers:
                logger.warning("No alive peers available for time synchronization")
                return False
            logger.debug(f"Time sync targeting {len(target_peers)} alive peers out of {len(self.peers)} total")
        
        self.sync_attempts += 1
        valid_measurements = []
        
        async with aiohttp.ClientSession() as session:
            # Collect time measurements from alive peers only
            tasks = [self.sync_with_peer(peer, session) for peer in target_peers]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for peer, result in zip(target_peers, results):
                if isinstance(result, tuple) and result is not None:
                    offset, delay = result
                    valid_measurements.append((offset, delay))
                    self.peer_offsets[peer] = offset
                    self.peer_delays[peer] = delay
                    self.peer_last_sync[peer] = time.time()
                elif node and hasattr(node, 'failure_detector'):
                    # Mark peer as failed if sync fails (like replication module)
                    if peer in node.failure_detector.peer_status:
                        node.failure_detector.peer_status[peer]['alive'] = False
                        logger.debug(f"Marked peer {peer} as failed due to sync failure")
        
        if not valid_measurements:
            logger.warning("No valid time measurements obtained from peers")
            return False
        
        # Calculate consensus offset using median (more robust than mean)
        offsets = [m[0] for m in valid_measurements]
        delays = [m[1] for m in valid_measurements]
        
        # Use median for both offset and delay for robustness against outliers
        consensus_offset = median(offsets)
        median_delay = median(delays)
        
        # Update synchronization state
        current_sync_time = time.time()
        self.clock_offset = consensus_offset
        self.network_delay = median_delay
        
        # Update drift rate computation
        self._update_drift_rate(consensus_offset, current_sync_time)
        
        self.last_sync_time = current_sync_time
        self.successful_syncs += 1
        
        # Calculate synchronization accuracy (standard deviation of offsets)
        if len(offsets) > 1:
            mean_offset = sum(offsets) / len(offsets)
            variance = sum((o - mean_offset) ** 2 for o in offsets) / len(offsets)
            self.sync_accuracy = variance ** 0.5
        else:
            self.sync_accuracy = 0.0
        
        logger.info(f"Time synchronized: offset={consensus_offset:.6f}s, "
                   f"accuracy={self.sync_accuracy:.6f}s, drift={self.drift_rate:.9f}s/s, "
                   f"peers={len(valid_measurements)}")
        
        return True
    
    def _update_drift_rate(self, offset: float, timestamp: float):
        """
        Update drift rate calculation based on offset history using linear regression.
        This helps predict future clock behavior and improve synchronization accuracy.
        """
        # Add current measurement to history
        self.offset_history.append((timestamp, offset))
        
        # Keep only recent measurements
        if len(self.offset_history) > self.max_history_size:
            self.offset_history.pop(0)
        
        # Need at least 3 points for meaningful drift calculation
        if len(self.offset_history) < 3:
            self.drift_rate = 0.0
            return
        
        # Calculate drift rate using linear regression (similar to ClockSkewAnalyzer)
        timestamps = [point[0] for point in self.offset_history]
        offsets = [point[1] for point in self.offset_history]
        
        n = len(self.offset_history)
        
        # Calculate means
        t_mean = sum(timestamps) / n
        o_mean = sum(offsets) / n
        
        # Calculate slope (drift rate) using least squares
        numerator = sum((t - t_mean) * (o - o_mean) for t, o in zip(timestamps, offsets))
        denominator = sum((t - t_mean) ** 2 for t in timestamps)
        
        if denominator > 0:
            self.drift_rate = numerator / denominator
            
            # Log significant drift changes
            if abs(self.drift_rate) > 1e-6:
                logger.warning(f"Significant clock drift detected: {self.drift_rate:.9f} s/s")
        else:
            self.drift_rate = 0.0
    
    def get_predicted_offset(self, future_time: Optional[float] = None) -> float:
        """
        Predict clock offset at a future time based on computed drift rate.
        Useful for timestamp correction and proactive synchronization.
        """
        if future_time is None:
            future_time = time.time()
        
        if not self.offset_history:
            return self.clock_offset
        
        # Calculate time elapsed since last synchronization
        time_diff = future_time - self.last_sync_time
        
        # Predict offset accounting for drift
        predicted_offset = self.clock_offset + (self.drift_rate * time_diff)
        
        return predicted_offset
    
    async def sync_task(self, app):
        """Background task for periodic time synchronization"""
        node = app.get('node')
        while True:
            try:
                await self.synchronize_with_peers(node)
            except Exception as e:
                logger.error(f"Time sync task error: {e}")
            
            await asyncio.sleep(self.sync_interval)
    
    def get_sync_status(self) -> Dict:
        """Get current synchronization status for monitoring"""
        return {
            "synchronized": self.is_synchronized(),
            "clock_offset": self.clock_offset,
            "network_delay": self.network_delay,
            "sync_accuracy": self.sync_accuracy,
            "drift_rate": self.drift_rate,
            "predicted_offset": self.get_predicted_offset(),
            "offset_history_size": len(self.offset_history),
            "last_sync_time": self.last_sync_time,
            "sync_attempts": self.sync_attempts,
            "successful_syncs": self.successful_syncs,
            "success_rate": self.successful_syncs / max(1, self.sync_attempts),
            "peer_offsets": self.peer_offsets.copy(),
            "peer_delays": self.peer_delays.copy()
        }
    
    def estimate_peer_time(self, peer: str, local_time: Optional[float] = None) -> Optional[float]:
        """
        Estimate the current time at a specific peer based on last synchronization.
        """
        if peer not in self.peer_offsets:
            return None
            
        if local_time is None:
            local_time = time.time()
            
        # Account for time elapsed since last sync with this peer
        time_since_sync = local_time - self.peer_last_sync.get(peer, 0)
        if time_since_sync > self.sync_interval * 3:  # Too old
            return None
            
        # Estimate peer time: local_time + peer_offset
        peer_offset = self.peer_offsets[peer]
        return local_time + peer_offset