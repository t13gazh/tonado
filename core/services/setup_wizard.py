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

from core.hardware.detect import HardwareProfile
from core.services.auth_service import AuthService, AuthTier
from core.services.base import BaseService
from core.services.config_service import ConfigService
from core.utils.subprocess import async_run
from core.services.wifi_service import WifiService

logger = logging.getLogger(__name__)

# Privileged helper that edits config.txt to (de)activate the I2S DAC overlay.
# Owned + sudoers-granted by the boot layer; we only invoke it via sudo -n.
AUDIO_OVERLAY_SCRIPT = "/opt/tonado/system/apply-audio-overlay.sh"


class SetupStep(StrEnum):
    NOT_STARTED = "not_started"
    HARDWARE_DETECTION = "hardware_detection"
    WIFI_SETUP = "wifi_setup"
    AUDIO_SETUP = "audio_setup"
    BUTTONS_SETUP = "buttons_setup"
    FIRST_CARD = "first_card"
    PIN_SETUP = "pin_setup"
    RECOVERY_WIFI = "recovery_wifi"
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
        auth_service: AuthService | None = None,
    ) -> None:
        super().__init__()
        self._config = config_service
        self._wifi = wifi_service
        self._detector = hardware_detector
        self._auth = auth_service
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
        """Compute a hash fingerprint of the hardware configuration.

        Ignores ALSA card numbers (hw:0/hw:1). Those shift on kernel
        updates even when the physical hardware is unchanged and were
        the main false-positive source of "hardware changed" banners.
        """
        parts = [
            f"rfid:{profile.rfid_reader}",
            f"gyro:{profile.gyro_detected}",
            f"pi:{profile.pi.model}",
        ]
        # Sort by (type, name) — both stable across reboots. Use only
        # type+name, not device, so hw:0↔hw:1 swaps don't invalidate the
        # fingerprint.
        for audio in sorted(profile.audio_outputs, key=lambda a: (a.type, a.name)):
            parts.append(f"audio:{audio.type}:{audio.name}")
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
            # Skip RFID SPI probe to avoid disrupting a running scan loop
            self._hardware = await self._detector.redetect(skip_rfid=True)
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
        """Step 3: Select audio output device and activate it if needed.

        Selecting an output may require flipping the firmware config.txt
        overlay (analog ↔ I2S DAC). The common case is "already active":
        `detect_audio` only reports a HifiBerry/I2S card when the overlay is
        already live, so picking that card needs no config change. When the
        chosen type differs from what's live, we call the privileged
        apply-audio-overlay.sh helper and flag a pending reboot — the actual
        reboot is deferred to setup completion so the wizard doesn't drop the
        phone mid-flow.

        Returns {success, device, requires_reboot}.
        """
        await self._config.set("audio.device", device)
        await self._save_step(SetupStep.AUDIO_SETUP)

        requires_reboot = await self._activate_audio_overlay(device)

        logger.info(
            "Audio output set to: %s (requires_reboot=%s)", device, requires_reboot
        )
        return {"success": True, "device": device, "requires_reboot": requires_reboot}

    async def _activate_audio_overlay(self, device: str) -> bool:
        """Activate the firmware overlay for `device` if it differs from live.

        Returns True iff a config.txt change was made and a reboot is now
        pending (also persists audio.reboot_pending=True in that case).

        Decision:
          1. Map the chosen device to a target overlay mode (i2s | analog).
             Prefer the type of the matching live output; fall back to a
             string heuristic so the wizard can offer an I2S DAC option even
             before its overlay is live (detect_audio only lists *active*
             cards, so a not-yet-enabled DAC has no hw:N entry to resolve).
             A device that maps to neither mode (HDMI/USB/unknown) → no-op.
          2. If the live profile already has a card of the target type, the
             overlay is already baked in → no-op, no reboot. This is the
             common case (DAC overlay applied at install time).
          3. Otherwise call apply-audio-overlay.sh {mode} and flag a pending
             reboot. The reboot itself is deferred to setup completion.
        """
        profile = self._hardware or self._get_profile()
        if profile.is_mock:
            # Dev/Windows: nothing to flip, never a reboot.
            return False

        outputs = profile.audio_outputs or []
        target_mode = self._resolve_audio_mode(device, outputs)
        if target_mode is None:
            # HDMI/USB/unknown — no config.txt overlay involved.
            return False

        # detect_audio only surfaces a card whose overlay is already live, so
        # if a card of the target mode is present, that mode is already active.
        already_active = any(a.type == target_mode for a in outputs)
        if already_active:
            return False

        rc, _, stderr = await async_run(
            ["sudo", "-n", AUDIO_OVERLAY_SCRIPT, target_mode]
        )
        if rc != 0:
            # Helper missing (dev) or sudoers drift. Don't claim a reboot is
            # pending — the overlay wasn't changed.
            logger.warning(
                "apply-audio-overlay.sh %s failed (rc=%s): %s",
                target_mode, rc, stderr.strip(),
            )
            return False

        await self._config.set("audio.reboot_pending", True)
        logger.info("Audio overlay activated (%s) — reboot pending", target_mode)
        return True

    @staticmethod
    def _resolve_audio_mode(device: str, outputs: list) -> str | None:
        """Map a chosen audio `device` to its overlay mode (i2s | analog).

        Returns None for outputs that are not overlay-controlled (HDMI, USB)
        or that can't be classified. Resolution order:
          1. Exact device match against a live output's type.
          2. String heuristic on the device identifier — lets the UI pass a
             logical choice ("i2s" / "hifiberry-dac" / "analog") for a card
             whose overlay isn't live yet and therefore has no hw:N entry.
        """
        for out in outputs:
            if out.device == device:
                return out.type if out.type in ("i2s", "analog") else None
        token = device.lower()
        if any(k in token for k in ("i2s", "hifiberry", "dac")):
            return "i2s"
        if any(k in token for k in ("analog", "3.5", "headphone", "onboard", "bcm2835")):
            return "analog"
        return None

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

    async def mark_pin_setup_done(self) -> dict[str, Any]:
        """Step 6: Mark PIN setup as done (advances the wizard state)."""
        await self._save_step(SetupStep.PIN_SETUP)
        return {"success": True}

    async def mark_recovery_wifi_done(self) -> dict[str, Any]:
        """Step 7: Mark the recovery-WiFi credentials step as done.

        The actual SSID + password are persisted by the setup router via
        the captive portal config keys; this method only advances the
        wizard's own step state so the UI can proceed. Idempotent — calling
        it again is a no-op beyond re-saving the same step.
        """
        await self._save_step(SetupStep.RECOVERY_WIFI)
        return {"success": True}

    async def complete_setup(self) -> dict[str, Any]:
        """Mark setup as fully complete.

        Requires a parent PIN to be set — a completed wizard without PIN
        would leave the whole LAN-exposed API wide open (see K1).
        """
        if self._auth is not None and not await self._auth.is_pin_set(AuthTier.PARENT):
            raise ValueError(
                "Eltern-PIN muss gesetzt sein, bevor die Einrichtung abgeschlossen wird."
            )

        # Update fingerprint on completion
        if self._hardware:
            fingerprint = self._compute_hardware_fingerprint(self._hardware)
            await self._config.set("setup.hardware_fingerprint", fingerprint)
        self._hardware_changed = False
        await self._config.set("setup.hardware_changed", False)
        await self._save_step(SetupStep.COMPLETED)
        if self._auth is not None:
            self._auth.set_setup_complete(True)
        logger.info("Setup wizard completed")
        return {"success": True}

    async def reset(self) -> None:
        """Reset setup to start over."""
        await self._save_step(SetupStep.NOT_STARTED)
        self._hardware = None
        self._hardware_changed = False
        await self._config.set("setup.hardware_changed", False)
        logger.info("Setup wizard reset")
