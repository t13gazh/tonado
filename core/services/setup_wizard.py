"""Setup wizard service for first-boot experience.

Guides the user through:
1. Hardware detection
2. WiFi configuration
3. Audio output selection
4. First card assignment (scan card → pick content)

Tracks setup state so the wizard can resume if interrupted.
"""

import hashlib
import logging
from dataclasses import asdict
from enum import StrEnum
from typing import Any

from core.hardware.detect import HardwareProfile, get_free_gpios
from core.services.base import BaseService
from core.services.config_service import ConfigService
from core.services.wifi_service import WifiService

logger = logging.getLogger(__name__)


class SetupStep(StrEnum):
    NOT_STARTED = "not_started"
    HARDWARE_DETECTION = "hardware_detection"
    WIFI_SETUP = "wifi_setup"
    AUDIO_SETUP = "audio_setup"
    BUTTONS_SETUP = "buttons_setup"
    FIRST_CARD = "first_card"
    COMPLETED = "completed"


# Ordered list of steps
_STEPS = list(SetupStep)


class SetupWizard(BaseService):
    """Manages the first-boot setup flow."""

    def __init__(
        self,
        config_service: ConfigService,
        wifi_service: WifiService,
        hardware_detector: "HardwareDetector | None" = None,
    ) -> None:
        super().__init__()
        self._config = config_service
        self._wifi = wifi_service
        self._detector = hardware_detector
        self._hardware: HardwareProfile | None = None
        self._current_step = SetupStep.NOT_STARTED
        self._hardware_changed = False

    async def start(self) -> None:
        """Load saved setup state and check for hardware changes."""
        saved = await self._config.get("setup.step")
        if saved and saved in SetupStep.__members__.values():
            self._current_step = SetupStep(saved)
        else:
            self._current_step = SetupStep.NOT_STARTED
        logger.info("Setup wizard state: %s", self._current_step)

        # If setup is complete, check for hardware changes
        if self.is_complete:
            await self._check_hardware_changes()

    @property
    def is_complete(self) -> bool:
        return self._current_step == SetupStep.COMPLETED

    @property
    def current_step(self) -> SetupStep:
        return self._current_step

    @property
    def hardware_changed(self) -> bool:
        return self._hardware_changed

    def status(self) -> dict[str, Any]:
        step_index = _STEPS.index(self._current_step)
        total = len(_STEPS) - 1  # Exclude NOT_STARTED
        return {
            "current_step": self._current_step.value,
            "progress": max(0, step_index) / max(1, total - 1),
            "is_complete": self.is_complete,
            "hardware": self._hardware.to_dict() if self._hardware else None,
            "hardware_changed": self._hardware_changed,
        }

    async def _save_step(self, step: SetupStep) -> None:
        self._current_step = step
        await self._config.set("setup.step", step.value)

    def _compute_hardware_fingerprint(self, profile: HardwareProfile) -> str:
        """Compute a hash fingerprint of the hardware configuration."""
        parts = [
            f"rfid:{profile.rfid_reader}",
            f"gyro:{profile.gyro_detected}",
            f"pi:{profile.pi.model}",
            f"free_gpios:{len(get_free_gpios(profile))}",
        ]
        for audio in sorted(profile.audio_outputs, key=lambda a: a.device):
            parts.append(f"audio:{audio.name}:{audio.device}")
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def _check_hardware_changes(self) -> None:
        """Compare cached hardware profile fingerprint to saved one."""
        try:
            profile = self._get_profile()
            if profile.is_mock:
                return  # Skip check on non-Pi systems
            current_fp = self._compute_hardware_fingerprint(profile)
            saved_fp = await self._config.get("setup.hardware_fingerprint")
            if saved_fp and saved_fp != current_fp:
                self._hardware_changed = True
                await self._config.set("setup.hardware_changed", True)
                logger.warning(
                    "Hardware change detected: saved=%s current=%s",
                    saved_fp, current_fp,
                )
            else:
                self._hardware_changed = False
            self._hardware = profile
        except Exception as e:
            logger.warning("Hardware change check failed: %s", e)

    # --- Step handlers ---

    def _get_profile(self) -> HardwareProfile:
        """Get hardware profile from detector or fallback to mock."""
        if self._detector is not None:
            return self._detector.profile
        return HardwareProfile(is_mock=True)

    async def detect_hardware(self) -> HardwareProfile:
        """Step 1: Detect hardware and return profile.

        Uses HardwareDetector's cached profile. Triggers redetect() to ensure
        fresh results during wizard flow.
        """
        if self._detector is not None:
            self._hardware = await self._detector.redetect()
        else:
            self._hardware = HardwareProfile(is_mock=True)
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

        # Save hardware fingerprint
        fingerprint = self._compute_hardware_fingerprint(self._hardware)
        await self._config.set("setup.hardware_fingerprint", fingerprint)

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
            return {"success": True, "status": asdict(status)}
        return {"success": False, "error": "Verbindung fehlgeschlagen"}

    async def setup_audio(self, device: str) -> dict[str, Any]:
        """Step 3: Select audio output device."""
        await self._config.set("audio.device", device)
        await self._save_step(SetupStep.AUDIO_SETUP)
        logger.info("Audio output set to: %s", device)
        return {"success": True, "device": device}

    async def setup_buttons(self, buttons: list[dict] | None = None) -> dict[str, Any]:
        """Step 4: Save GPIO button configuration."""
        if buttons:
            import json
            await self._config.set("hardware.buttons", json.dumps(buttons))
        await self._save_step(SetupStep.BUTTONS_SETUP)
        logger.info("Button setup complete: %d buttons", len(buttons) if buttons else 0)
        return {"success": True, "count": len(buttons) if buttons else 0}

    async def complete_first_card(self) -> dict[str, Any]:
        """Step 5: Mark first card assignment as done."""
        await self._save_step(SetupStep.FIRST_CARD)
        return {"success": True}

    async def complete_setup(self) -> dict[str, Any]:
        """Mark setup as fully complete."""
        # Update fingerprint on completion
        if self._hardware:
            fingerprint = self._compute_hardware_fingerprint(self._hardware)
            await self._config.set("setup.hardware_fingerprint", fingerprint)
        self._hardware_changed = False
        await self._config.set("setup.hardware_changed", False)
        await self._save_step(SetupStep.COMPLETED)
        logger.info("Setup wizard completed")
        return {"success": True}

    async def reset(self) -> None:
        """Reset setup to start over."""
        await self._save_step(SetupStep.NOT_STARTED)
        self._hardware = None
        self._hardware_changed = False
        await self._config.set("setup.hardware_changed", False)
        logger.info("Setup wizard reset")
