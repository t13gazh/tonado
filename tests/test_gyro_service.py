"""Tests for the GyroService service layer (H6).

The gesture algorithm itself is covered by test_gyro.py. This file
exercises the service wrapper: enable/disable, calibration flow,
health reporting, and event publishing.
"""

import asyncio

import pytest
import pytest_asyncio

from core.hardware.gyro import AccelData, AxisMapping, MockGyroSensor
from core.services.config_service import ConfigService
from core.services.event_bus import EventBus
from core.services.gyro_service import GyroService


class ScriptedSensor(MockGyroSensor):
    """Sensor that returns pre-scripted readings in order."""

    def __init__(self, readings: list[AccelData]) -> None:
        super().__init__()
        self._readings = list(readings)
        self._idx = 0

    async def read_accel(self) -> AccelData:
        if not self._readings:
            return AccelData(x=0, y=0, z=1)
        reading = self._readings[self._idx % len(self._readings)]
        self._idx += 1
        return reading


@pytest.fixture
def sensor() -> ScriptedSensor:
    return ScriptedSensor([AccelData(x=0, y=0, z=1)])


@pytest.mark.asyncio
async def test_start_disabled_does_nothing(
    sensor: ScriptedSensor, event_bus: EventBus
) -> None:
    svc = GyroService(sensor, event_bus, enabled=False)
    await svc.start()
    assert svc._poll_task is None
    await svc.stop()


@pytest.mark.asyncio
async def test_health_reports_mock_sensor(
    sensor: ScriptedSensor, event_bus: EventBus
) -> None:
    svc = GyroService(sensor, event_bus, enabled=True)
    health = svc.health()
    assert health["status"] == "not_configured"
    assert "Mock" in health["detail"]


@pytest.mark.asyncio
async def test_enabled_setter(
    sensor: ScriptedSensor, event_bus: EventBus
) -> None:
    svc = GyroService(sensor, event_bus, enabled=True)
    assert svc.enabled is True
    svc.enabled = False
    assert svc.enabled is False


@pytest.mark.asyncio
async def test_calibration_requires_samples(
    sensor: ScriptedSensor, event_bus: EventBus
) -> None:
    """calibrate_save with no collected samples raises RuntimeError."""
    svc = GyroService(sensor, event_bus, enabled=False)
    with pytest.raises(RuntimeError, match="Missing samples"):
        await svc.calibrate_save()


@pytest.mark.asyncio
async def test_calibrate_collect_rest_needs_enough_samples(
    sensor: ScriptedSensor, event_bus: EventBus
) -> None:
    """A collect with < 10 samples must raise."""
    svc = GyroService(sensor, event_bus, enabled=False)
    await svc.calibrate_start()
    # Fire collect and finish immediately — no readings came in
    async def _finish():
        await asyncio.sleep(0.05)
        svc._collect_done.set()

    asyncio.create_task(_finish())
    with pytest.raises(RuntimeError, match="Too few rest"):
        await svc.calibrate_collect_rest()


@pytest.mark.asyncio
async def test_flip_forward_toggles_sign(
    sensor: ScriptedSensor,
    event_bus: EventBus,
    config_service: ConfigService,
) -> None:
    svc = GyroService(sensor, event_bus, config=config_service, enabled=False)
    initial = svc.axis_map.fwd_sign
    mapping = await svc.flip_forward()
    assert svc.axis_map.fwd_sign == -initial
    # Second flip restores
    await svc.flip_forward()
    assert svc.axis_map.fwd_sign == initial


@pytest.mark.asyncio
async def test_load_calibration_from_config(
    sensor: ScriptedSensor,
    event_bus: EventBus,
    config_service: ConfigService,
) -> None:
    """Stored calibration is rehydrated on start()."""
    custom = AxisMapping(fwd_sign=-1.0).to_dict()
    await config_service.set("gyro.axis_map", custom)
    await config_service.set("gyro.bias", {"x": 0.01, "y": 0.02, "z": 0.03})
    await config_service.set("gyro.calibrated", True)

    svc = GyroService(
        sensor, event_bus, config=config_service, enabled=True
    )
    await svc.start()
    try:
        # Give the poll loop a tick to run at least once
        await asyncio.sleep(0.05)
        assert svc.calibrated is True
        assert svc.axis_map.fwd_sign == -1.0
    finally:
        await svc.stop()


@pytest.mark.asyncio
async def test_stop_when_not_started_is_safe(
    sensor: ScriptedSensor, event_bus: EventBus
) -> None:
    """Stop must tolerate being called without a prior successful start()."""
    svc = GyroService(sensor, event_bus, enabled=False)
    await svc.stop()  # should not raise


# --- K8: gesture mapping follows card.remove_pauses ---

@pytest_asyncio.fixture
async def wired_config(tmp_db, event_bus: EventBus):
    """ConfigService with an EventBus wired in so config_changed fires."""
    svc = ConfigService(tmp_db, event_bus)
    await svc.start()
    yield svc


@pytest.mark.asyncio
async def test_gyro_starts_in_volume_mode_by_default(
    sensor: ScriptedSensor, event_bus: EventBus, wired_config: ConfigService
) -> None:
    """Default card.remove_pauses=False → tilts route to volume control."""
    # ConfigService seeds the default (False) at start()
    assert await wired_config.get("card.remove_pauses") is False
    svc = GyroService(sensor, event_bus, config=wired_config, enabled=True)
    try:
        await svc.start()
        assert svc._keep_playing_mode is True
    finally:
        await svc.stop()


@pytest.mark.asyncio
async def test_config_change_flips_gesture_mode(
    sensor: ScriptedSensor, event_bus: EventBus, wired_config: ConfigService
) -> None:
    """Toggling card.remove_pauses at runtime must re-route tilt gestures."""
    await wired_config.set("card.remove_pauses", True)
    svc = GyroService(sensor, event_bus, config=wired_config, enabled=True)
    try:
        await svc.start()
        assert svc._keep_playing_mode is False  # pause-mode → playback toggles

        # User toggles the setting to "keep playing"
        await wired_config.set("card.remove_pauses", False)
        assert svc._keep_playing_mode is True  # tilts now control volume
    finally:
        await svc.stop()


def test_gesture_maps_cover_all_gestures() -> None:
    """Both maps must agree on LEFT/RIGHT/SHAKE and diverge only on FORWARD/BACK."""
    from core.hardware.gyro import Gesture
    from core.services.gyro_service import GESTURE_ACTIONS, GESTURE_ACTIONS_KEEP_PLAYING

    assert set(GESTURE_ACTIONS) == set(GESTURE_ACTIONS_KEEP_PLAYING)
    for g in (Gesture.TILT_LEFT, Gesture.TILT_RIGHT, Gesture.SHAKE):
        assert GESTURE_ACTIONS[g] == GESTURE_ACTIONS_KEEP_PLAYING[g]
    # These are the K8-divergent ones
    assert GESTURE_ACTIONS[Gesture.TILT_FORWARD] == "play_pause"
    assert GESTURE_ACTIONS_KEEP_PLAYING[Gesture.TILT_FORWARD] == "volume_up"
    assert GESTURE_ACTIONS[Gesture.TILT_BACK] == "stop"
    assert GESTURE_ACTIONS_KEEP_PLAYING[Gesture.TILT_BACK] == "volume_down"
