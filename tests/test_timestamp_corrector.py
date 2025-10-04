import time

import pytest  # type: ignore

from ds_messaging.time.clock_skew import ClockSkewAnalyzer
from ds_messaging.time.timestamp_correction import TimestampCorrectionMethod, TimestampCorrector


class _FakeTimeSync:
    def __init__(self, offset: float, predicted: float, accuracy: float = 0.01):
        self.clock_offset = offset
        self._predicted = predicted
        self.sync_accuracy = accuracy
        self.peer_offsets = {}
        self.peer_last_sync = {}

    def get_predicted_offset(self, _timestamp: float) -> float:
        return self._predicted


@pytest.mark.parametrize(
    "offset,predicted",
    [
        (0.05, 0.08),
        (-0.12, -0.10),
    ],
)
def test_correct_timestamp_hybrid(offset: float, predicted: float) -> None:
    time_sync = _FakeTimeSync(offset, predicted)
    analyzer = ClockSkewAnalyzer()
    analyzer.drift_rate = 0.001
    corrector = TimestampCorrector(time_sync, analyzer, method=TimestampCorrectionMethod.HYBRID)

    original = time.time()
    corrected, metadata = corrector.correct_timestamp(original)

    expected_offset = metadata["applied_offset"]
    assert abs((corrected - original) - expected_offset) < 1e-6
    assert metadata["method"] == TimestampCorrectionMethod.HYBRID.value
    assert metadata["magnitude"] >= 0.0

    accuracy = corrector.estimate_accuracy(corrected, original)
    assert accuracy["upper_bound"] >= corrected
    assert accuracy["lower_bound"] <= corrected


def test_validate_timestamp_rejects_future() -> None:
    time_sync = _FakeTimeSync(0.0, 0.0)
    analyzer = ClockSkewAnalyzer()
    corrector = TimestampCorrector(time_sync, analyzer)

    far_future = time.time() + corrector.max_future_skew + 10
    ok, reason = corrector.validate_timestamp(far_future)
    assert not ok
    assert "ahead" in reason