import time
import logging
from typing import Dict, Optional, Tuple, List
from enum import Enum

logger = logging.getLogger(__name__)


class TimestampCorrectionMethod(Enum):
    """Different methods for timestamp correction"""
    SIMPLE_OFFSET = "simple_offset"
    LINEAR_DRIFT = "linear_drift"
    NETWORK_DELAY_COMPENSATION = "network_delay_compensation"
    HYBRID = "hybrid"


class TimestampCorrector:
    """
    Provides various techniques for correcting message timestamps based on 
    clock synchronization data and network delay analysis.
    """
    
    def __init__(self, method: TimestampCorrectionMethod = TimestampCorrectionMethod.HYBRID):
        self.method = method
        
        # Synchronization state
        self.clock_offset = 0.0
        self.drift_rate = 0.0
        self.network_delay = 0.0
        self.last_sync_time = 0.0
        
        # Correction statistics
        self.corrections_applied = 0
        self.total_correction_magnitude = 0.0
        self.max_correction = 0.0
        
        # Per-peer correction data
        self.peer_offsets: Dict[str, float] = {}
        self.peer_delays: Dict[str, float] = {}
        self.peer_drift_rates: Dict[str, float] = {}
        
    def update_sync_data(self, clock_offset: float, drift_rate: float, 
                        network_delay: float, sync_timestamp: Optional[float] = None):
        """Update synchronization data used for corrections"""
        self.clock_offset = clock_offset
        self.drift_rate = drift_rate
        self.network_delay = network_delay
        self.last_sync_time = sync_timestamp or time.time()
        
        logger.debug(f"Timestamp corrector updated: offset={clock_offset:.6f}s, "
                    f"drift={drift_rate:.9f}s/s, delay={network_delay:.6f}s")
    
    def update_peer_data(self, peer: str, offset: float, delay: float, drift_rate: float = 0.0):
        """Update peer-specific correction data"""
        self.peer_offsets[peer] = offset
        self.peer_delays[peer] = delay
        self.peer_drift_rates[peer] = drift_rate
    
    def correct_timestamp(self, original_timestamp: float, 
                         sender: Optional[str] = None,
                         receive_time: Optional[float] = None) -> Tuple[float, Dict]:
        """
        Correct a message timestamp using the configured correction method.
        
        Returns:
            Tuple of (corrected_timestamp, correction_info)
        """
        if receive_time is None:
            receive_time = time.time()
        
        correction_info = {
            "method": self.method.value,
            "original_timestamp": original_timestamp,
            "receive_time": receive_time,
            "corrections_applied": {}
        }
        
        corrected_timestamp = original_timestamp
        
        if self.method == TimestampCorrectionMethod.SIMPLE_OFFSET:
            corrected_timestamp, offset_info = self._apply_simple_offset(original_timestamp)
            correction_info["corrections_applied"]["offset"] = offset_info
            
        elif self.method == TimestampCorrectionMethod.LINEAR_DRIFT:
            corrected_timestamp, drift_info = self._apply_drift_correction(
                original_timestamp, receive_time
            )
            correction_info["corrections_applied"]["drift"] = drift_info
            
        elif self.method == TimestampCorrectionMethod.NETWORK_DELAY_COMPENSATION:
            corrected_timestamp, delay_info = self._apply_network_delay_compensation(
                original_timestamp, sender, receive_time
            )
            correction_info["corrections_applied"]["network_delay"] = delay_info
            
        elif self.method == TimestampCorrectionMethod.HYBRID:
            corrected_timestamp, hybrid_info = self._apply_hybrid_correction(
                original_timestamp, sender, receive_time
            )
            correction_info["corrections_applied"] = hybrid_info
        
        # Update statistics
        correction_magnitude = abs(corrected_timestamp - original_timestamp)
        self.corrections_applied += 1
        self.total_correction_magnitude += correction_magnitude
        self.max_correction = max(self.max_correction, correction_magnitude)
        
        correction_info["correction_magnitude"] = correction_magnitude
        correction_info["corrected_timestamp"] = corrected_timestamp
        
        if correction_magnitude > 0.1:  # Log significant corrections
            logger.info(f"Large timestamp correction applied: {correction_magnitude:.6f}s "
                       f"(method: {self.method.value})")
        
        return corrected_timestamp, correction_info
    
    def _apply_simple_offset(self, timestamp: float) -> Tuple[float, Dict]:
        """Apply simple clock offset correction"""
        corrected = timestamp + self.clock_offset
        
        info = {
            "offset_applied": self.clock_offset,
            "correction": self.clock_offset
        }
        
        return corrected, info
    
    def _apply_drift_correction(self, timestamp: float, receive_time: float) -> Tuple[float, Dict]:
        """Apply clock drift correction based on time elapsed"""
        # Calculate time elapsed since last synchronization
        time_since_sync = receive_time - self.last_sync_time
        
        # Apply base offset and drift correction
        drift_correction = self.drift_rate * time_since_sync
        total_correction = self.clock_offset + drift_correction
        
        corrected = timestamp + total_correction
        
        info = {
            "base_offset": self.clock_offset,
            "drift_rate": self.drift_rate,
            "time_since_sync": time_since_sync,
            "drift_correction": drift_correction,
            "total_correction": total_correction
        }
        
        return corrected, info
    
    def _apply_network_delay_compensation(self, timestamp: float, 
                                        sender: Optional[str], 
                                        receive_time: float) -> Tuple[float, Dict]:
        """Apply network delay compensation to timestamp"""
        # Use peer-specific delay if available, otherwise use average
        if sender and sender in self.peer_delays:
            delay = self.peer_delays[sender]
            offset = self.peer_offsets.get(sender, self.clock_offset)
        else:
            delay = self.network_delay
            offset = self.clock_offset
        
        # Estimate when message was actually sent accounting for network delay
        estimated_send_time = receive_time - delay
        
        # Calculate correction based on the difference between claimed and estimated send time
        time_diff = estimated_send_time - timestamp
        
        # Apply correction (conservative approach - use partial correction)
        delay_correction = time_diff * 0.5  # Use 50% of calculated difference
        total_correction = offset + delay_correction
        
        corrected = timestamp + total_correction
        
        info = {
            "sender": sender,
            "network_delay": delay,
            "base_offset": offset,
            "estimated_send_time": estimated_send_time,
            "time_difference": time_diff,
            "delay_correction": delay_correction,
            "total_correction": total_correction
        }
        
        return corrected, info
    
    def _apply_hybrid_correction(self, timestamp: float, 
                               sender: Optional[str], 
                               receive_time: float) -> Tuple[float, Dict]:
        """Apply hybrid correction combining multiple techniques"""
        corrections_info = {}
        
        # 1. Apply base offset correction
        offset_corrected, offset_info = self._apply_simple_offset(timestamp)
        corrections_info["offset"] = offset_info
        
        # 2. Apply drift correction
        drift_corrected, drift_info = self._apply_drift_correction(offset_corrected, receive_time)
        corrections_info["drift"] = drift_info
        
        # 3. Apply network delay compensation (lighter weight in hybrid mode)
        if sender and sender in self.peer_delays:
            delay = self.peer_delays[sender]
            estimated_send_time = receive_time - delay
            time_diff = estimated_send_time - timestamp
            
            # Apply smaller network delay correction in hybrid mode
            network_correction = time_diff * 0.2  # Use only 20% of calculated difference
            final_corrected = drift_corrected + network_correction
            
            corrections_info["network_delay"] = {
                "sender": sender,
                "network_delay": delay,
                "estimated_send_time": estimated_send_time,
                "time_difference": time_diff,
                "network_correction": network_correction
            }
        else:
            final_corrected = drift_corrected
            corrections_info["network_delay"] = {"applied": False, "reason": "No peer data available"}
        
        # Calculate total correction applied
        total_correction = final_corrected - timestamp
        corrections_info["total_correction"] = total_correction
        
        return final_corrected, corrections_info
    
    def validate_timestamp(self, timestamp: float, 
                          receive_time: Optional[float] = None) -> Tuple[bool, str]:
        """
        Validate if a timestamp is reasonable.
        
        Returns:
            Tuple of (is_valid, reason)
        """
        if receive_time is None:
            receive_time = time.time()
        
        # Check if timestamp is not too far in the future
        if timestamp > receive_time + 300:  # 5 minutes in future
            return False, f"Timestamp too far in future: {timestamp - receive_time:.2f}s ahead"
        
        # Check if timestamp is not too far in the past
        if timestamp < receive_time - 3600:  # 1 hour in past
            return False, f"Timestamp too far in past: {receive_time - timestamp:.2f}s ago"
        
        # Check for obviously invalid timestamps (e.g., before epoch)
        if timestamp < 0:
            return False, "Timestamp is negative"
        
        # Check for timestamps that are too old (before year 2000)
        if timestamp < 946684800:  # January 1, 2000
            return False, "Timestamp predates year 2000"
        
        return True, "Valid timestamp"
    
    def estimate_accuracy(self, corrected_timestamp: float, 
                         original_timestamp: float,
                         sender: Optional[str] = None) -> float:
        """
        Estimate the accuracy of the timestamp correction.
        
        Returns estimated accuracy in seconds (lower is better).
        """
        base_accuracy = 0.1  # Base uncertainty
        
        # Factor in synchronization accuracy
        sync_accuracy = abs(self.clock_offset) * 0.1
        
        # Factor in drift uncertainty
        time_since_sync = time.time() - self.last_sync_time
        drift_uncertainty = abs(self.drift_rate) * time_since_sync
        
        # Factor in network delay uncertainty
        if sender and sender in self.peer_delays:
            delay_uncertainty = self.peer_delays[sender] * 0.2
        else:
            delay_uncertainty = self.network_delay * 0.3
        
        # Magnitude of correction affects confidence
        correction_magnitude = abs(corrected_timestamp - original_timestamp)
        correction_uncertainty = correction_magnitude * 0.1
        
        total_uncertainty = (base_accuracy + sync_accuracy + 
                           drift_uncertainty + delay_uncertainty + 
                           correction_uncertainty)
        
        return total_uncertainty
    
    def get_correction_statistics(self) -> Dict:
        """Get statistics about timestamp corrections"""
        avg_correction = (self.total_correction_magnitude / max(1, self.corrections_applied))
        
        return {
            "corrections_applied": self.corrections_applied,
            "average_correction_magnitude": avg_correction,
            "max_correction_magnitude": self.max_correction,
            "total_correction_magnitude": self.total_correction_magnitude,
            "current_method": self.method.value,
            "current_clock_offset": self.clock_offset,
            "current_drift_rate": self.drift_rate,
            "current_network_delay": self.network_delay,
            "peers_tracked": len(self.peer_offsets),
            "last_sync_time": self.last_sync_time
        }
    
    def reset_statistics(self):
        """Reset correction statistics"""
        self.corrections_applied = 0
        self.total_correction_magnitude = 0.0
        self.max_correction = 0.0