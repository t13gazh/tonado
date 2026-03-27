"""Setup wizard service for first-boot experience.

Guides the user through:
1. Hardware detection
2. WiFi configuration
3. Audio output selection
4. First card assignment (scan card → pick content)

Tracks setup state so the wizard can resume if interrupted.
"""

import logging
from enum import StrEnum
from typing import Any

from core.hardware.detect import HardwareProfile, detect_all
from core.services.config_service import ConfigService
from core.services.wifi_service import WifiService

logger = logging.getLogger(__name__)


class SetupStep(StrEnum):
    NOT_STARTED = "not_started"
    HARDWARE_DETECTION = "hardware_detection"
    WIFI_SETUP = "wifi_setup"
    AUDIO_SETUP = "audio_setup"
    FIRST_CARD = "first_card"
    COMPLETED = "completed"


# Ordered list of steps
_STEPS = list(SetupStep)


class SetupWizard:
    """Manages the first-boot setup flow."""

    def __init__(
        self,
        config_service: ConfigService,
        wifi_service: WifiService,
    ) -> None:
        self._config = config_service
        self._wifi = wifi_service
        self._hardware: HardwareProfile | None = None
        self._current_step = SetupStep.NOT_STARTED

    async def start(self) -> None:
        """Load saved setup state."""
        saved = await self._config.get("setup.step")
        if saved and saved in SetupStep.__members__.values():
            self._current_step = SetupStep(saved)
        else:
            self._current_step = SetupStep.NOT_STARTED
        logger.info("Setup wizard state: %s", self._current_step)

    @property
    def is_complete(self) -> bool:
        return self._current_step == SetupStep.COMPLETED

    @property
    def current_step(self) -> SetupStep:
        return self._current_step

    def status(self) -> dict[str, Any]:
        step_index = _STEPS.index(self._current_step)
        total = len(_STEPS) - 1  # Exclude NOT_STARTED
        return {
            "current_step": self._current_step.value,
            "progress": max(0, step_index) / max(1, total - 1),
            "is_complete": self.is_complete,
            "hardware": self._hardware.to_dict() if self._hardware else None,
        }

    async def _save_step(self, step: SetupStep) -> None:
        self._current_step = step
        await self._config.set("setup.step", step.value)

    # --- Step handlers ---

    async def detect_hardware(self) -> HardwareProfile:
        """Step 1: Detect hardware and return profile."""
        self._hardware = detect_all()
        await self._save_step(SetupStep.HARDWARE_DETECTION)

        # Save detected hardware to config
        if self._hardware.rfid_reader != "none":
            await self._config.set("hardware.rfid_type", self._hardware.rfid_reader)
            await self._config.set("hardware.rfid_device", self._hardware.rfid_device)

        if self._hardware.gyro_detected:
            await self._config.set("gyro.enabled", True)
        else:
            await self._config.set("gyro.enabled", False)

        if self._hardware.pi.model != "unknown":
            await self._config.set("hardware.pi_model", self._hardware.pi.model)
            await self._config.set("hardware.pi_ram_mb", self._hardware.pi.ram_mb)

        logger.info("Hardware detection complete: %s", self._hardware.pi.model)
        return self._hardware

    async def setup_wifi(self, ssid: str, password: str = "") -> dict[str, Any]:
        """Step 2: Connect to WiFi network."""
        success = await self._wifi.connect(ssid, password)
        if success:
            await self._save_step(SetupStep.WIFI_SETUP)
            await self._config.set("wifi.ssid", ssid)
            status = await self._wifi.status()
            if status.ip_address:
                await self._config.set("wifi.ip_address", status.ip_address)
            return {"success": True, "status": status.to_dict()}
        return {"success": False, "error": "Verbindung fehlgeschlagen"}

    async def setup_audio(self, device: str) -> dict[str, Any]:
        """Step 3: Select audio output device."""
        await self._config.set("audio.device", device)
        await self._save_step(SetupStep.AUDIO_SETUP)
        logger.info("Audio output set to: %s", device)
        return {"success": True, "device": device}

    async def complete_first_card(self) -> dict[str, Any]:
        """Step 4: Mark first card assignment as done."""
        await self._save_step(SetupStep.FIRST_CARD)
        return {"success": True}

    async def complete_setup(self) -> dict[str, Any]:
        """Mark setup as fully complete."""
        await self._save_step(SetupStep.COMPLETED)
        logger.info("Setup wizard completed")
        return {"success": True}

    async def reset(self) -> None:
        """Reset setup to start over."""
        await self._save_step(SetupStep.NOT_STARTED)
        self._hardware = None
        logger.info("Setup wizard reset")
