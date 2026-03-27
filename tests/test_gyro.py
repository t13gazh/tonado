"""Tests for gyro gesture detection."""

import pytest

from core.hardware.gyro import AccelData, Gesture, GestureDetector


def _detect_until_gesture(detector: GestureDetector, accel: AccelData, max_readings: int = 20) -> Gesture | None:
    """Feed readings until a gesture is detected or max_readings is reached."""
    for _ in range(max_readings):
        result = detector.detect(accel)
        if result is not None:
            return result
    return None


def test_no_gesture_when_flat() -> None:
    detector = GestureDetector(sensitivity="normal")
    result = _detect_until_gesture(detector, AccelData(x=0.0, y=0.0, z=1.0))
    assert result is None


def test_tilt_left_detected() -> None:
    detector = GestureDetector(sensitivity="normal")
    result = _detect_until_gesture(detector, AccelData(x=-0.7, y=0.0, z=0.7))
    assert result == Gesture.TILT_LEFT


def test_tilt_right_detected() -> None:
    detector = GestureDetector(sensitivity="normal")
    result = _detect_until_gesture(detector, AccelData(x=0.7, y=0.0, z=0.7))
    assert result == Gesture.TILT_RIGHT


def test_tilt_forward_detected() -> None:
    detector = GestureDetector(sensitivity="normal")
    result = _detect_until_gesture(detector, AccelData(x=0.0, y=0.7, z=0.7))
    assert result == Gesture.TILT_FORWARD


def test_tilt_back_detected() -> None:
    detector = GestureDetector(sensitivity="normal")
    result = _detect_until_gesture(detector, AccelData(x=0.0, y=-0.7, z=0.7))
    assert result == Gesture.TILT_BACK


def test_shake_detected() -> None:
    detector = GestureDetector(sensitivity="normal")
    result = _detect_until_gesture(detector, AccelData(x=2.0, y=2.0, z=2.0))
    assert result == Gesture.SHAKE


def test_cooldown_after_gesture() -> None:
    detector = GestureDetector(sensitivity="normal")
    # Trigger a gesture
    _detect_until_gesture(detector, AccelData(x=-0.7, y=0.0, z=0.7))

    # Immediately after, same input should be in cooldown
    result = detector.detect(AccelData(x=-0.7, y=0.0, z=0.7))
    assert result is None


def test_gentle_sensitivity_needs_more_tilt() -> None:
    detector = GestureDetector(sensitivity="gentle")
    # Moderate tilt that would trigger "normal" but not "gentle"
    result = _detect_until_gesture(detector, AccelData(x=-0.55, y=0.0, z=0.85))
    assert result is None


def test_wild_sensitivity_triggers_easily() -> None:
    detector = GestureDetector(sensitivity="wild")
    # Small tilt that triggers "wild" but not "normal"
    result = _detect_until_gesture(detector, AccelData(x=-0.4, y=0.0, z=0.9))
    assert result == Gesture.TILT_LEFT
