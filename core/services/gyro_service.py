"""Gyro service translating sensor gestures into player actions."""

import asyncio
import logging

from core.hardware.gyro import (
    AccelBias,
    AccelData,
    AxisMapping,
    Gesture,
    GestureDetector,
    GyroSensor,
    calibrate_from_readings,
)
from core.services.base import BaseService
from core.services.config_service import ConfigService
from core.services.event_bus import EventBus

logger = logging.getLogger(__name__)

# Gesture → action mapping when removing the figure pauses playback
# (card.remove_pauses=True). The figure falls off during a tilt anyway,
# so tilts front/back double as discrete playback toggles.
GESTURE_ACTIONS = {
    Gesture.TILT_LEFT: "previous_track",
    Gesture.TILT_RIGHT: "next_track",
    Gesture.TILT_FORWARD: "play_pause",
    Gesture.TILT_BACK: "stop",
    Gesture.SHAKE: "shuffle",
}

# When playback continues after the figure is removed (typical for
# magnet-backed figures or a card holder) tilts are usable as a
# continuous volume dial.
GESTURE_ACTIONS_KEEP_PLAYING = {
    Gesture.TILT_LEFT: "previous_track",
    Gesture.TILT_RIGHT: "next_track",
    Gesture.TILT_FORWARD: "volume_up",
    Gesture.TILT_BACK: "volume_down",
    Gesture.SHAKE: "shuffle",
}

# Number of samples to average during calibration
CALIBRATION_SAMPLES = 50


class GyroService(BaseService):
    """Reads gyro sensor data, detects gestures, publishes events."""

    def __init__(
        self,
        sensor: GyroSensor,
        event_bus: EventBus,
        config: ConfigService | None = None,
        sensitivity: str = "normal",
        enabled: bool = True,
    ) -> None:
        super().__init__()
        self._sensor = sensor
        self._event_bus = event_bus
        self._config = config
        self._detector = GestureDetector(sensitivity=sensitivity)
        self._enabled = enabled
        self._hw_failed = False
        self._poll_task: asyncio.Task | None = None

        # Keep-playing mode (card.remove_pauses=False) repurposes tilt-
        # front/back as volume control. See K8 product decision.
        self._keep_playing_mode = False
        # Track whether we attached the config listener so stop() can
        # detach it cleanly — avoids a stale closure firing on a dead
        # service after restart.
        self._config_subscribed = False

        # Last detected gesture (for test UI)
        self._last_gesture: str | None = None
        self._last_gesture_age = 0  # readings since last gesture

        # Calibration state
        self._axis_map = AxisMapping()
        self._bias = AccelBias()
        self._calibrated = False
        self._calibrating = asyncio.Event()
        self._calibrating.set()  # Not calibrating → gesture detection active

        # Calibration session (collecting samples)
        self._rest_samples: list[AccelData] = []
        self._tilt_samples: list[AccelData] = []
        self._collecting: str | None = None  # "rest" or "tilt" or None
        self._collect_done: asyncio.Event = asyncio.Event()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def calibrated(self) -> bool:
        return self._calibrated

    @property
    def last_gesture(self) -> str | None:
        """Last detected gesture (clears after 1s / 20 readings)."""
        if self._last_gesture_age > 20:
            return None
        return self._last_gesture

    @property
    def axis_map(self) -> AxisMapping:
        return self._axis_map

    async def start(self) -> None:
        """Initialize sensor and start gesture detection loop."""
        if not self._enabled:
            logger.info("Gyro service disabled")
            return
        try:
            await self._sensor.start()
        except Exception as e:
            logger.warning("Gyro sensor init failed, gyro service disabled: %s", e)
            self._enabled = False
            self._hw_failed = True
            return

        # Load calibration from config
        await self._load_calibration()

        # Hydrate keep-playing mode from config and follow live changes
        if self._config is not None:
            stored = await self._config.get("card.remove_pauses")
            # Default: remove_pauses=False (box keeps playing → volume mode)
            self._keep_playing_mode = (stored is False) or (stored is None)
            self._event_bus.subscribe("config_changed", self._on_config_changed)
            self._config_subscribed = True

        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(
            "Gyro service started (calibrated=%s, keep_playing=%s)",
            self._calibrated, self._keep_playing_mode,
        )

    async def _on_config_changed(self, key: str = "", value=None, **_) -> None:
        """Pick up card.remove_pauses changes so the gesture map stays in sync."""
        if key == "card.remove_pauses":
            self._keep_playing_mode = value is False
            logger.info(
                "Gyro gesture mode updated: %s",
                "volume (keep-playing)" if self._keep_playing_mode else "playback toggles",
            )

    async def stop(self) -> None:
        """Stop gesture detection and release sensor."""
        if self._config_subscribed:
            self._event_bus.unsubscribe("config_changed", self._on_config_changed)
            self._config_subscribed = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await self._sensor.stop()

    def health(self) -> dict:
        """Return gyro sensor health status."""
        from core.hardware.gyro import MockGyroSensor
        if isinstance(self._sensor, MockGyroSensor):
            return {"status": "not_configured", "detail": "Mock-Sensor"}
        if self._hw_failed:
            return {"status": "error", "detail": "Sensor-Initialisierung fehlgeschlagen"}
        if not self._enabled:
            return {"status": "disconnected", "detail": "Deaktiviert"}
        detail = "MPU6050"
        if not self._calibrated:
            detail += " (nicht kalibriert)"
        return {"status": "connected", "detail": detail}

    async def read_raw(self) -> AccelData:
        """Read current accelerometer values (bias-corrected)."""
        raw = await self._sensor.read_accel()
        return self._bias.apply(raw)

    async def read_mapped(self) -> AccelData:
        """Read accelerometer values after bias + axis mapping."""
        corrected = await self.read_raw()
        return self._axis_map.remap(corrected)

    # --- Calibration API ---

    async def calibrate_start(self) -> None:
        """Begin calibration — pause gesture detection."""
        self._calibrating.clear()  # Pause gesture detection
        self._rest_samples.clear()
        self._tilt_samples.clear()
        self._collecting = None
        logger.info("Calibration started — gesture detection paused")

    async def calibrate_collect_rest(self) -> dict:
        """Collect rest samples (box flat on table)."""
        self._rest_samples.clear()
        self._collecting = "rest"
        self._collect_done.clear()

        try:
            await asyncio.wait_for(self._collect_done.wait(), timeout=10.0)
        finally:
            self._collecting = None

        # Validate
        n = len(self._rest_samples)
        if n < 10:
            raise RuntimeError(f"Too few rest samples: {n}")

        avg = AccelData(
            x=sum(s.x for s in self._rest_samples) / n,
            y=sum(s.y for s in self._rest_samples) / n,
            z=sum(s.z for s in self._rest_samples) / n,
        )
        return {"samples": n, "avg": {"x": round(avg.x, 3), "y": round(avg.y, 3), "z": round(avg.z, 3)}}

    async def calibrate_collect_tilt(self) -> dict:
        """Collect tilt-right samples (box tilted to the right)."""
        self._tilt_samples.clear()
        self._collecting = "tilt"
        self._collect_done.clear()

        try:
            await asyncio.wait_for(self._collect_done.wait(), timeout=10.0)
        finally:
            self._collecting = None

        n = len(self._tilt_samples)
        if n < 10:
            raise RuntimeError(f"Too few tilt samples: {n}")

        avg = AccelData(
            x=sum(s.x for s in self._tilt_samples) / n,
            y=sum(s.y for s in self._tilt_samples) / n,
            z=sum(s.z for s in self._tilt_samples) / n,
        )
        return {"samples": n, "avg": {"x": round(avg.x, 3), "y": round(avg.y, 3), "z": round(avg.z, 3)}}

    async def calibrate_save(self) -> dict:
        """Calculate and save calibration from collected samples."""
        if not self._rest_samples or not self._tilt_samples:
            raise RuntimeError("Missing samples — collect rest and tilt first")

        mapping, bias = calibrate_from_readings(self._rest_samples, self._tilt_samples)

        self._axis_map = mapping
        self._bias = bias
        self._calibrated = True

        # Persist to config
        if self._config:
            await self._config.set("gyro.axis_map", mapping.to_dict())
            await self._config.set("gyro.bias", bias.to_dict())
            await self._config.set("gyro.calibrated", True)

        # Reset detector base gravity and resume gesture detection
        self._detector.reset_base()
        self._calibrating.set()

        await self._event_bus.publish("gyro.calibrated", mapping=mapping.to_dict())
        logger.info("Calibration saved and gesture detection resumed")

        return {
            "axis_map": mapping.to_dict(),
            "bias": bias.to_dict(),
        }

    async def flip_forward(self) -> dict:
        """Invert the forward axis sign (fixes swapped forward/back)."""
        self._axis_map.fwd_sign *= -1.0
        if self._config:
            await self._config.set("gyro.axis_map", self._axis_map.to_dict())
        logger.info("Forward axis flipped: fwd_sign=%.0f", self._axis_map.fwd_sign)
        return self._axis_map.to_dict()

    async def calibrate_cancel(self) -> None:
        """Cancel calibration and resume gesture detection."""
        self._collecting = None
        self._rest_samples.clear()
        self._tilt_samples.clear()
        self._calibrating.set()
        logger.info("Calibration cancelled")

    # --- Internal ---

    async def _load_calibration(self) -> None:
        """Load axis mapping and bias from config."""
        if not self._config:
            return
        try:
            self._calibrated = await self._config.get("gyro.calibrated")
            if self._calibrated:
                axis_data = await self._config.get("gyro.axis_map")
                self._axis_map = AxisMapping.from_dict(axis_data)
                bias_data = await self._config.get("gyro.bias")
                self._bias = AccelBias.from_dict(bias_data)
                logger.info("Loaded calibration: %s", self._axis_map.to_dict())
        except Exception as e:
            logger.warning("Failed to load calibration, using defaults: %s", e)
            self._axis_map = AxisMapping()
            self._bias = AccelBias()
            self._calibrated = False

    async def _poll_loop(self) -> None:
        """Poll sensor at ~10 Hz and detect gestures."""
        while True:
            try:
                if not self._enabled:
                    await asyncio.sleep(0.5)
                    continue

                raw = await self._sensor.read_accel()

                # Collect samples during calibration
                if self._collecting == "rest":
                    self._rest_samples.append(raw)
                    if len(self._rest_samples) >= CALIBRATION_SAMPLES:
                        self._collect_done.set()
                elif self._collecting == "tilt":
                    self._tilt_samples.append(raw)
                    if len(self._tilt_samples) >= CALIBRATION_SAMPLES:
                        self._collect_done.set()

                # Track gesture age for test UI
                self._last_gesture_age += 1

                # Only detect gestures when not calibrating
                if self._calibrating.is_set():
                    corrected = self._bias.apply(raw)
                    mapped = self._axis_map.remap(corrected)
                    gesture = self._detector.detect(mapped)

                    if gesture is not None:
                        actions = (
                            GESTURE_ACTIONS_KEEP_PLAYING
                            if self._keep_playing_mode
                            else GESTURE_ACTIONS
                        )
                        action = actions[gesture]
                        self._last_gesture = gesture.value
                        self._last_gesture_age = 0
                        logger.info("Gesture detected: %s → %s", gesture, action)
                        await self._event_bus.publish(
                            "gesture_detected",
                            gesture=gesture.value,
                            action=action,
                        )

                await asyncio.sleep(0.1)  # 10 Hz — sufficient for gesture detection
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Gyro poll error: %s", e)
                await asyncio.sleep(1)
