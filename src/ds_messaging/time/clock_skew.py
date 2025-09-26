import time
import logging
from typing import Dict, List, Tuple, Optional
from collections import deque
import statistics

logger = logging.getLogger(__name__)


class ClockSkewAnalyzer:
    """
    Analyzes clock skew and drift patterns in distributed messaging system.
    Tracks clock behavior over time and provides correction mechanisms.
    """
    
    def __init__(self, window_size: int = 100, max_skew: float = 0.1):
        self.window_size = window_size
        self.max_skew = max_skew  # Maximum acceptable skew in seconds
        
        # Historical data for drift analysis
        self.offset_history: deque = deque(maxlen=window_size)
        self.timestamp_history: deque = deque(maxlen=window_size)
        
        # Skew analysis results
        self.current_skew = 0.0
        self.drift_rate = 0.0  # Clock drift in seconds per second
        self.last_analysis_time = 0.0
        
        # Peer-specific skew tracking
        self.peer_skews: Dict[str, deque] = {}
        self.peer_drift_rates: Dict[str, float] = {}
        
    def record_offset(self, offset: float, timestamp: Optional[float] = None):
        """Record a clock offset measurement for analysis"""
        if timestamp is None:
            timestamp = time.time()
            
        self.offset_history.append(offset)
        self.timestamp_history.append(timestamp)
        
        # Update current skew
        self.current_skew = offset
        
        # Trigger analysis if we have enough data
        if len(self.offset_history) >= 3:
            self._analyze_drift()
    
    def record_peer_offset(self, peer: str, offset: float, timestamp: Optional[float] = None):
        """Record clock offset for a specific peer"""
        if timestamp is None:
            timestamp = time.time()
            
        if peer not in self.peer_skews:
            self.peer_skews[peer] = deque(maxlen=self.window_size)
            
        self.peer_skews[peer].append((offset, timestamp))
        
        # Calculate drift rate for this peer
        if len(self.peer_skews[peer]) >= 3:
            self.peer_drift_rates[peer] = self._calculate_drift_rate(
                list(self.peer_skews[peer])
            )
    
    def _analyze_drift(self):
        """Analyze clock drift based on historical offset data"""
        if len(self.offset_history) < 3:
            return
            
        # Calculate drift rate using linear regression
        self.drift_rate = self._calculate_drift_rate(
            list(zip(self.offset_history, self.timestamp_history))
        )
        
        self.last_analysis_time = time.time()
        
        if abs(self.drift_rate) > 1e-6:  # Significant drift detected
            logger.warning(f"Clock drift detected: {self.drift_rate:.9f} s/s")
    
    def _calculate_drift_rate(self, data_points: List[Tuple[float, float]]) -> float:
        """Calculate drift rate using simple linear regression"""
        if len(data_points) < 2:
            return 0.0
            
        # Extract x (time) and y (offset) values
        x_values = [point[1] for point in data_points]  # timestamps
        y_values = [point[0] for point in data_points]  # offsets
        
        n = len(data_points)
        
        # Calculate means
        x_mean = sum(x_values) / n
        y_mean = sum(y_values) / n
        
        # Calculate slope (drift rate)
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
        denominator = sum((x - x_mean) ** 2 for x in x_values)
        
        if denominator == 0:
            return 0.0
            
        return numerator / denominator
    
    def predict_future_offset(self, future_time: float) -> float:
        """Predict clock offset at a future time based on drift analysis"""
        if not self.offset_history:
            return 0.0
            
        time_diff = future_time - self.timestamp_history[-1]
        predicted_offset = self.current_skew + (self.drift_rate * time_diff)
        
        return predicted_offset
    
    def is_skew_acceptable(self, skew: Optional[float] = None) -> bool:
        """Check if current or given skew is within acceptable bounds"""
        if skew is None:
            skew = self.current_skew
        return abs(skew) <= self.max_skew
    
    def get_correction_factor(self, timestamp: float) -> float:
        """Get correction factor for a given timestamp based on drift analysis"""
        if not self.offset_history:
            return 0.0
            
        # Calculate time elapsed since last measurement
        time_elapsed = timestamp - self.timestamp_history[-1]
        
        # Apply drift correction
        correction = self.current_skew + (self.drift_rate * time_elapsed)
        
        return correction
    
    def detect_clock_jumps(self, threshold: float = 0.5) -> List[Tuple[float, float]]:
        """Detect significant clock jumps in the offset history"""
        if len(self.offset_history) < 2:
            return []
            
        jumps = []
        offsets = list(self.offset_history)
        timestamps = list(self.timestamp_history)
        
        for i in range(1, len(offsets)):
            offset_diff = abs(offsets[i] - offsets[i-1])
            if offset_diff > threshold:
                jumps.append((timestamps[i], offset_diff))
                logger.warning(f"Clock jump detected at {timestamps[i]}: {offset_diff:.6f}s")
        
        return jumps
    
    def get_skew_statistics(self) -> Dict:
        """Get comprehensive statistics about clock skew"""
        if not self.offset_history:
            return {"error": "No data available"}
            
        offsets = list(self.offset_history)
        
        stats = {
            "current_skew": self.current_skew,
            "drift_rate": self.drift_rate,
            "measurements": len(offsets),
            "mean_offset": statistics.mean(offsets),
            "median_offset": statistics.median(offsets),
            "std_deviation": statistics.stdev(offsets) if len(offsets) > 1 else 0.0,
            "min_offset": min(offsets),
            "max_offset": max(offsets),
            "range": max(offsets) - min(offsets),
            "acceptable": self.is_skew_acceptable(),
            "last_analysis": self.last_analysis_time
        }
        
        # Add peer-specific statistics
        peer_stats = {}
        for peer, skews in self.peer_skews.items():
            if skews:
                peer_offsets = [s[0] for s in skews]
                peer_stats[peer] = {
                    "current_offset": peer_offsets[-1],
                    "drift_rate": self.peer_drift_rates.get(peer, 0.0),
                    "measurements": len(peer_offsets),
                    "mean_offset": statistics.mean(peer_offsets),
                    "std_deviation": statistics.stdev(peer_offsets) if len(peer_offsets) > 1 else 0.0
                }
        
        stats["peer_statistics"] = peer_stats
        
        return stats
    
    def recommend_sync_interval(self) -> float:
        """Recommend synchronization interval based on drift analysis"""
        if abs(self.drift_rate) < 1e-9:  # Very stable clock
            return 300.0  # 5 minutes
        elif abs(self.drift_rate) < 1e-7:  # Reasonably stable
            return 120.0  # 2 minutes
        elif abs(self.drift_rate) < 1e-6:  # Moderate drift
            return 60.0   # 1 minute
        else:  # High drift
            return 30.0   # 30 seconds
    
    def reset_analysis(self):
        """Reset all analysis data"""
        self.offset_history.clear()
        self.timestamp_history.clear()
        self.peer_skews.clear()
        self.peer_drift_rates.clear()
        self.current_skew = 0.0
        self.drift_rate = 0.0
        self.last_analysis_time = 0.0