"""Tests for hardware detection module."""

import pytest

from core.hardware.detect import HardwareProfile, detect_all


def test_detect_all_returns_mock_on_non_pi() -> None:
    """On Windows/non-Pi, detection should return a mock profile."""
    profile = detect_all()
    assert isinstance(profile, HardwareProfile)
    assert profile.is_mock is True


def test_hardware_profile_to_dict() -> None:
    profile = HardwareProfile(is_mock=True)
    d = profile.to_dict()
    assert d["is_mock"] is True
    assert d["rfid"]["reader"] == "none"
    assert d["gyro_detected"] is False
    assert isinstance(d["audio"], list)
