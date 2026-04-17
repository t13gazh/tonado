"""Tests for hardware detection module."""

import pytest

from core.hardware.detect import (
    HardwareProfile,
    _HID_NON_RFID_HINTS,
    _RC522_VERSION_IDS,
    _hid_looks_like_rfid,
    detect_all,
)


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


# --- H9 hardening ---

def test_rc522_version_ids_include_clones() -> None:
    """H9: FM17522 clones (0x88, 0xB2) must be accepted alongside the NXP originals."""
    assert 0x91 in _RC522_VERSION_IDS
    assert 0x92 in _RC522_VERSION_IDS
    assert 0x88 in _RC522_VERSION_IDS
    assert 0xB2 in _RC522_VERSION_IDS


@pytest.mark.parametrize("name", [
    "Logitech USB Keyboard",
    "Dell Keypad",
    "Razer Gaming Mouse",
    "Apple Touchpad",
    "Xbox Controller",
    "Sony Gamepad",
])
def test_hid_filter_rejects_input_devices(name: str) -> None:
    """H9: keyboards/mice/gamepads must not be picked up as RFID readers."""
    assert _hid_looks_like_rfid(name) is False


@pytest.mark.parametrize("name", [
    "Sycreader USB Reader",
    "HXGCoLtd Human Interface",
    "RFIDeas pcProx",
    "",  # no sysfs info — default to accepting so legitimate readers still work
])
def test_hid_filter_accepts_rfid_names(name: str) -> None:
    """H9: actual RFID readers (and unknown devices) must pass the filter."""
    assert _hid_looks_like_rfid(name) is True


def test_hid_non_rfid_hints_are_lowercase() -> None:
    """Filter matches lowercase — hint list must also be lowercase or the check misses."""
    for hint in _HID_NON_RFID_HINTS:
        assert hint == hint.lower()
