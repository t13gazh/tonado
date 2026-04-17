"""Tests for gyro gesture detection.

The detector uses wall-clock timing (warmup, dwell, debounce). Tests
drive a fake clock so readings cross these thresholds deterministically.
"""

from unittest.mock import patch

import pytest

from core.hardware.gyro import AccelData, Gesture, GestureDetector


class _Clock:
    """Monotonic clock driven manually by tests (in seconds, matching time.monotonic)."""

    def __init__(self) -> None:
        self.t = 0.0  # seconds

    def __call__(self) -> float:
        return self.t

    def advance(self, ms: float) -> None:
        self.t += ms / 1000.0


_FLAT = AccelData(x=0.0, y=0.0, z=1.0)


def _warm_up(detector: GestureDetector, clock: _Clock, step_ms: float = 100.0) -> None:
    """Feed flat readings for 3s so the warmup + base-gravity lock completes."""
    for _ in range(30):
        detector.detect(_FLAT)
        clock.advance(step_ms)


def _drive(
    detector: GestureDetector,
    clock: _Clock,
    accel: AccelData,
    *,
    readings: int = 30,
    step_ms: float = 100.0,
    warm: bool = True,
) -> Gesture | None:
    """Feed the detector with one accel value, advancing the clock between calls.

    Returns the first gesture the detector emits, or None. When ``warm``
    is set the detector first sees 3s of flat readings so it locks onto
    (0, 0, 1) as its neutral gravity.
    """
    if warm:
        _warm_up(detector, clock, step_ms)
    for _ in range(readings):
        result = detector.detect(accel)
        if result is not None:
            return result
        clock.advance(step_ms)
    return None


@pytest.fixture
def clock():
    c = _Clock()
    with patch("core.hardware.gyro.time.monotonic", side_effect=c):
        yield c


def test_no_gesture_when_flat(clock: _Clock) -> None:
    detector = GestureDetector(sensitivity="normal")
    result = _drive(detector, clock, AccelData(x=0.0, y=0.0, z=1.0))
    assert result is None


def test_tilt_left_detected(clock: _Clock) -> None:
    detector = GestureDetector(sensitivity="normal")
    # Roll negative (x = -sin θ) → TILT_LEFT. 50° roll is well past normal trigger.
    result = _drive(detector, clock, AccelData(x=-0.77, y=0.0, z=0.64))
    assert result == Gesture.TILT_LEFT


def test_tilt_right_detected(clock: _Clock) -> None:
    detector = GestureDetector(sensitivity="normal")
    result = _drive(detector, clock, AccelData(x=0.77, y=0.0, z=0.64))
    assert result == Gesture.TILT_RIGHT


def test_tilt_forward_detected(clock: _Clock) -> None:
    detector = GestureDetector(sensitivity="normal")
    # Pitch negative (y = -sin θ) → TILT_FORWARD (head of box down)
    result = _drive(detector, clock, AccelData(x=0.0, y=-0.77, z=0.64))
    assert result == Gesture.TILT_FORWARD


def test_tilt_back_detected(clock: _Clock) -> None:
    detector = GestureDetector(sensitivity="normal")
    # Pitch positive (y = +sin θ) → TILT_BACK
    result = _drive(detector, clock, AccelData(x=0.0, y=0.77, z=0.64))
    assert result == Gesture.TILT_BACK


def test_shake_detected(clock: _Clock) -> None:
    detector = GestureDetector(sensitivity="normal")
    # Magnitude ~3.46g — far above G_MAX. Shake uses raw magnitude so no warmup.
    result = _drive(detector, clock, AccelData(x=2.0, y=2.0, z=2.0))
    assert result == Gesture.SHAKE


def test_cooldown_after_gesture(clock: _Clock) -> None:
    detector = GestureDetector(sensitivity="normal")
    first = _drive(detector, clock, AccelData(x=-0.77, y=0.0, z=0.64))
    assert first == Gesture.TILT_LEFT
    # Same tilt immediately after — detector is in the un-armed state until
    # the box returns to neutral, so no second gesture.
    result = detector.detect(AccelData(x=-0.77, y=0.0, z=0.64))
    assert result is None


def test_gentle_sensitivity_needs_more_tilt(clock: _Clock) -> None:
    detector = GestureDetector(sensitivity="gentle")
    # ~17° tilt — trips "normal" (trigger 14°) but not "gentle" (trigger 18°)
    result = _drive(detector, clock, AccelData(x=-0.3, y=0.0, z=0.954))
    assert result is None


def test_wild_sensitivity_triggers_easily(clock: _Clock) -> None:
    detector = GestureDetector(sensitivity="wild")
    # ~24° tilt — ignored by "normal", but "wild" has a lower trigger.
    result = _drive(detector, clock, AccelData(x=-0.4, y=0.0, z=0.9))
    assert result == Gesture.TILT_LEFT
