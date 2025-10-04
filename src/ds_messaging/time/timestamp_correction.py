import math
import time
import statistics
from enum import Enum
from typing import Dict, Optional, Tuple, List


class TimestampCorrectionMethod(str, Enum):
    """Enumeration of supported timestamp correction strategies."""

    OFFSET = "offset"
    DRIFT_COMPENSATED = "drift_compensated"
    HYBRID = "hybrid"


class TimestampCorrector:
    """Apply clock-offset and drift-aware corrections to timestamps.

    The corrector relies on the active ``TimeSync`` instance to obtain the
    current clock-offset, while the ``ClockSkewAnalyzer`` provides drift
    insights for longer running trends.  The class tracks statistics so the
    REST API can expose accuracy information and operators can reset metrics
    during experiments.
    """

    def __init__(
        self,
        time_sync,
        clock_analyzer,
        method: TimestampCorrectionMethod = TimestampCorrectionMethod.HYBRID,
        max_future_skew: float = 5.0,
        max_past_skew: float = 60.0,
    ) -> None:
        self.time_sync = time_sync
        self.clock_analyzer = clock_analyzer
        self.method = method
        self.max_future_skew = max_future_skew
        self.max_past_skew = max_past_skew

        # Statistics
        self.corrections_applied = 0
        self.total_correction_magnitude = 0.0
        self.max_correction_magnitude = 0.0
        self.correction_history: List[Tuple[float, float]]
        self.correction_history = []  # (original, corrected)

    # ------------------------------------------------------------------
    # Validation & correction helpers
    # ------------------------------------------------------------------
    def validate_timestamp(self, timestamp: Optional[float]) -> Tuple[bool, str]:
        """Validate an incoming timestamp prior to correction."""

        if timestamp is None:
            return False, "timestamp missing"

        try:
            timestamp = float(timestamp)
        except (TypeError, ValueError):
            return False, "timestamp must be numeric"

        now = time.time()
        # Reject timestamps that are too far in the future.
        if timestamp - now > self.max_future_skew:
            return False, "timestamp is implausibly ahead of local clock"

        # Reject very old timestamps (suggests stale client or clock jump).
        if now - timestamp > self.max_past_skew:
            return False, "timestamp is excessively old"

        return True, "ok"

    def _compute_offset(self, original_timestamp: float) -> float:
        """Derive an offset using the configured method."""
        offset = self.time_sync.clock_offset if self.time_sync else 0.0

        if self.method == TimestampCorrectionMethod.OFFSET:
            return offset

        drift = 0.0
        if self.clock_analyzer:
            drift = self.clock_analyzer.drift_rate
            # Record latest offset in analyzer for trend tracking.
            self.clock_analyzer.record_offset(offset)

        if self.method == TimestampCorrectionMethod.DRIFT_COMPENSATED:
            return offset + drift * 0.5  # speculative half-interval drift

        # Hybrid – mix current offset with drift prediction at timestamp horizon.
        if self.time_sync:
            predicted_offset = self.time_sync.get_predicted_offset(original_timestamp)
        else:
            predicted_offset = offset

        # Weight current measurement heavier (2/3 offset, 1/3 prediction)
        return (2 * offset + predicted_offset) / 3.0 + drift * 0.25

    def correct_timestamp(
        self,
        original_timestamp: float,
        sender: Optional[str] = None,
    ) -> Tuple[float, Dict[str, float]]:
        """Return a drift-aware corrected timestamp and metadata."""

        offset = self._compute_offset(original_timestamp)
        corrected_timestamp = original_timestamp + offset

        # Update statistics
        self.corrections_applied += 1
        magnitude = abs(corrected_timestamp - original_timestamp)
        self.total_correction_magnitude += magnitude
        self.max_correction_magnitude = max(self.max_correction_magnitude, magnitude)
        self.correction_history.append((original_timestamp, corrected_timestamp))

        # Feed analyzer with peer-specific data if available.
        if sender and self.clock_analyzer:
            self.clock_analyzer.record_peer_offset(sender, offset)

        return corrected_timestamp, {
            "applied_offset": offset,
            "method": self.method.value,
            "magnitude": magnitude,
        }

    def estimate_accuracy(
        self,
        corrected_timestamp: float,
        original_timestamp: float,
        sender: Optional[str] = None,
    ) -> Dict[str, float]:
        """Estimate accuracy bounds for a corrected timestamp."""

        if not self.time_sync:
            return {
                "confidence_interval": 0.5,
                "lower_bound": corrected_timestamp - 0.25,
                "upper_bound": corrected_timestamp + 0.25,
            }

        accuracy = max(self.time_sync.sync_accuracy, 1e-6)
        variance = accuracy**2
        drift = self.clock_analyzer.drift_rate if self.clock_analyzer else 0.0
        age = abs(corrected_timestamp - original_timestamp)

        peer_offset = 0.0
        if sender and getattr(self.time_sync, "peer_offsets", None):
            peer_offset = abs(self.time_sync.peer_offsets.get(sender, 0.0))

        # Confidence grows when more corrections exist.
        sample_count = max(1, self.corrections_applied)
        confidence_interval = (
            math.sqrt(variance / sample_count)
            + abs(drift) * 0.5
            + peer_offset * 0.1
            + age * 0.01
        )

        return {
            "confidence_interval": confidence_interval,
            "lower_bound": corrected_timestamp - confidence_interval,
            "upper_bound": corrected_timestamp + confidence_interval,
        }

    # ------------------------------------------------------------------
    # Statistics and maintenance
    # ------------------------------------------------------------------
    def reset_statistics(self) -> None:
        self.corrections_applied = 0
        self.total_correction_magnitude = 0.0
        self.max_correction_magnitude = 0.0
        self.correction_history.clear()

    def get_correction_statistics(self) -> Dict[str, float]:
        if not self.correction_history:
            return {
                "corrections_applied": 0,
                "average_correction_magnitude": 0.0,
                "max_correction_magnitude": 0.0,
                "current_method": self.method.value,
            }

        magnitudes = [abs(corrected - original) for original, corrected in self.correction_history]
        average = statistics.fmean(magnitudes)

        return {
            "corrections_applied": self.corrections_applied,
            "average_correction_magnitude": average,
            "max_correction_magnitude": self.max_correction_magnitude,
            "current_method": self.method.value,
        }

