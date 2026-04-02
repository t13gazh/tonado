"""Central hardware detection service with cached results.

Single source of truth for hardware state. Replaces scattered detect_all() calls
across setup_wizard, system router, and card_service health checks.
"""

import logging
import time

from core.hardware.detect import HardwareProfile, detect_all
from core.services.base import BaseService

logger = logging.getLogger(__name__)


class HardwareDetector(BaseService):
    """Detect and cache the hardware profile at startup.

    Other services query this instead of running their own detection.
    Full re-detection only happens on explicit redetect() call.
    """

    def __init__(self) -> None:
        super().__init__()
        self._profile: HardwareProfile | None = None
        self._detected_at: float | None = None

    async def start(self) -> None:
        """Run initial hardware detection."""
        self._profile = detect_all()
        self._detected_at = time.monotonic()
        logger.info(
            "Hardware detected: RFID=%s, Gyro=%s, Mock=%s",
            self._profile.rfid_reader,
            self._profile.gyro_detected,
            self._profile.is_mock,
        )

    @property
    def profile(self) -> HardwareProfile:
        """Return the cached hardware profile.

        Falls back to a mock profile if detection hasn't run yet.
        """
        if self._profile is None:
            return HardwareProfile(is_mock=True)
        return self._profile

    @property
    def detected_at(self) -> float | None:
        """Monotonic timestamp of last detection."""
        return self._detected_at

    def health(self) -> dict:
        """Derive health from cached profile."""
        if self._profile is None:
            return {"status": "not_detected", "detail": "Detection not run"}
        if self._profile.is_mock:
            return {"status": "mock", "detail": "Not running on Raspberry Pi"}
        return {
            "status": "ok",
            "detail": self._profile.pi.model,
            "rfid": self._profile.rfid_reader,
            "gyro": self._profile.gyro_detected,
        }

    async def redetect(self, component: str | None = None, skip_rfid: bool = False) -> HardwareProfile:
        """Re-run hardware detection.

        Args:
            component: Optional — currently unused, reserved for future
                       partial re-detection (e.g. "rfid" only).
            skip_rfid: If True, skip RFID SPI probe to avoid disrupting
                       a running card scan loop. Uses cached RFID result.
        """
        logger.info("Re-detecting hardware (component=%s, skip_rfid=%s)...", component or "all", skip_rfid)
        old_rfid = self._profile.rfid_reader if self._profile else None
        old_rfid_dev = self._profile.rfid_device if self._profile else None
        self._profile = detect_all(skip_rfid=skip_rfid)
        # Preserve cached RFID result when skipping probe
        if skip_rfid and old_rfid:
            self._profile.rfid_reader = old_rfid
            self._profile.rfid_device = old_rfid_dev
        self._detected_at = time.monotonic()
        logger.info(
            "Re-detection complete: RFID=%s, Gyro=%s",
            self._profile.rfid_reader,
            self._profile.gyro_detected,
        )
        return self._profile

    async def stop(self) -> None:
        """Nothing to clean up."""
        pass
