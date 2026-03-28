"""Gyro service translating sensor gestures into player actions."""

import asyncio
import logging

from core.hardware.gyro import Gesture, GestureDetector, GyroSensor
from core.services.event_bus import EventBus

logger = logging.getLogger(__name__)

# Map gestures to event bus actions
GESTURE_ACTIONS = {
    Gesture.TILT_LEFT: "previous_track",
    Gesture.TILT_RIGHT: "next_track",
    Gesture.TILT_FORWARD: "volume_up",
    Gesture.TILT_BACK: "volume_down",
    Gesture.SHAKE: "shuffle",
}


class GyroService:
    """Reads gyro sensor data, detects gestures, publishes events."""

    def __init__(
        self,
        sensor: GyroSensor,
        event_bus: EventBus,
        sensitivity: str = "normal",
        enabled: bool = True,
    ) -> None:
        self._sensor = sensor
        self._event_bus = event_bus
        self._detector = GestureDetector(sensitivity=sensitivity)
        self._enabled = enabled
        self._poll_task: asyncio.Task | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    async def start(self) -> None:
        """Initialize sensor and start gesture detection loop."""
        if not self._enabled:
            logger.info("Gyro service disabled")
            return
        await self._sensor.start()
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Gyro service started")

    async def stop(self) -> None:
        """Stop gesture detection and release sensor."""
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await self._sensor.stop()

    async def _poll_loop(self) -> None:
        """Poll sensor at ~50 Hz and detect gestures."""
        while True:
            try:
                if not self._enabled:
                    await asyncio.sleep(0.5)
                    continue

                accel = await self._sensor.read_accel()
                gesture = self._detector.detect(accel)

                if gesture is not None:
                    action = GESTURE_ACTIONS[gesture]
                    logger.info("Gesture detected: %s → %s", gesture, action)
                    await self._event_bus.publish(
                        "gesture_detected",
                        gesture=gesture.value,
                        action=action,
                    )

                await asyncio.sleep(0.05)  # 20 Hz — sufficient for gesture detection
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Gyro poll error: %s", e)
                await asyncio.sleep(1)
