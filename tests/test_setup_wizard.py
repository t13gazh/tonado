"""Tests for the setup wizard service."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from core.hardware.detect import AudioOutput, HardwareProfile, PiModel
from core.services.auth_service import AuthService, AuthTier
from core.services.config_service import ConfigService
from core.services.setup_wizard import SetupStep, SetupWizard
from core.services.wifi_service import WifiService


@pytest.fixture
def wifi_service() -> WifiService:
    service = WifiService()
    # On Windows/non-Pi this will be in mock mode
    return service


@pytest_asyncio.fixture
async def auth_service_with_pin(config_service: ConfigService) -> AuthService:
    svc = AuthService(config_service)
    await svc.start()
    await svc.set_pin(AuthTier.PARENT, "1234")
    return svc


@pytest.mark.asyncio
async def test_wizard_starts_not_complete(config_service: ConfigService, wifi_service: WifiService) -> None:
    wizard = SetupWizard(config_service, wifi_service)
    await wizard.start()
    assert not wizard.is_complete
    assert wizard.current_step == SetupStep.NOT_STARTED


@pytest.mark.asyncio
async def test_wizard_step_progression(
    config_service: ConfigService,
    wifi_service: WifiService,
    auth_service_with_pin: AuthService,
) -> None:
    wizard = SetupWizard(
        config_service, wifi_service, auth_service=auth_service_with_pin
    )
    await wizard.start()

    # Step 1: Hardware detection (returns mock profile on Windows)
    hw = await wizard.detect_hardware()
    assert hw is not None
    assert wizard.current_step == SetupStep.HARDWARE_DETECTION

    # Step 2: WiFi (mock mode)
    result = await wizard.setup_wifi("TestNetwork", "password123")
    assert result["success"] is True
    assert wizard.current_step == SetupStep.WIFI_SETUP

    # Step 3: Audio
    result = await wizard.setup_audio("hw:0")
    assert result["success"] is True
    assert wizard.current_step == SetupStep.AUDIO_SETUP

    # Step 4: First card
    result = await wizard.complete_first_card()
    assert result["success"] is True
    assert wizard.current_step == SetupStep.FIRST_CARD

    # Step 5: PIN setup (wizard progression only; PIN is already set)
    result = await wizard.mark_pin_setup_done()
    assert result["success"] is True
    assert wizard.current_step == SetupStep.PIN_SETUP

    # Step 6: Recovery WiFi (wizard progression only; creds saved by router)
    result = await wizard.mark_recovery_wifi_done()
    assert result["success"] is True
    assert wizard.current_step == SetupStep.RECOVERY_WIFI

    # Complete
    result = await wizard.complete_setup()
    assert result["success"] is True
    assert wizard.is_complete


@pytest.mark.asyncio
async def test_recovery_wifi_step_is_idempotent(
    config_service: ConfigService, wifi_service: WifiService
) -> None:
    """mark_recovery_wifi_done() must be safe to call repeatedly (re-run)."""
    wizard = SetupWizard(config_service, wifi_service)
    await wizard.start()

    await wizard.mark_recovery_wifi_done()
    assert wizard.current_step == SetupStep.RECOVERY_WIFI
    # Calling again stays on the same step without raising.
    await wizard.mark_recovery_wifi_done()
    assert wizard.current_step == SetupStep.RECOVERY_WIFI


@pytest.mark.asyncio
async def test_complete_requires_parent_pin(
    config_service: ConfigService, wifi_service: WifiService
) -> None:
    """complete_setup() must fail if the parent PIN has not been set."""
    auth = AuthService(config_service)
    await auth.start()
    wizard = SetupWizard(config_service, wifi_service, auth_service=auth)
    await wizard.start()
    with pytest.raises(ValueError, match="Eltern-PIN"):
        await wizard.complete_setup()
    assert not wizard.is_complete


@pytest.mark.asyncio
async def test_complete_with_parent_pin_seals_auth(
    config_service: ConfigService,
    wifi_service: WifiService,
    auth_service_with_pin: AuthService,
) -> None:
    """complete_setup() should flip AuthService into sealed mode."""
    wizard = SetupWizard(
        config_service, wifi_service, auth_service=auth_service_with_pin
    )
    await wizard.start()
    result = await wizard.complete_setup()
    assert result["success"] is True
    assert wizard.is_complete
    # AuthService now seals off missing-PIN tiers
    assert not auth_service_with_pin.check_access(None, AuthTier.EXPERT)


@pytest.mark.asyncio
async def test_wizard_persists_state(tmp_path: Path) -> None:
    from core.database import DatabaseManager

    mgr = DatabaseManager(tmp_path / "persist.db")
    await mgr.start()
    db = mgr.connection

    # First run: advance to WiFi step
    config1 = ConfigService(db)
    await config1.start()
    wifi = WifiService()
    wizard1 = SetupWizard(config1, wifi)
    await wizard1.start()
    await wizard1.detect_hardware()
    assert wizard1.current_step == SetupStep.HARDWARE_DETECTION
    await mgr.stop()

    # Second run: should resume from saved state
    mgr2 = DatabaseManager(tmp_path / "persist.db")
    await mgr2.start()
    db2 = mgr2.connection
    config2 = ConfigService(db2)
    await config2.start()
    wizard2 = SetupWizard(config2, wifi)
    await wizard2.start()
    assert wizard2.current_step == SetupStep.HARDWARE_DETECTION
    await mgr2.stop()


@pytest.mark.asyncio
async def test_wizard_reset(config_service: ConfigService, wifi_service: WifiService) -> None:
    wizard = SetupWizard(config_service, wifi_service)
    await wizard.start()

    await wizard.detect_hardware()
    assert wizard.current_step == SetupStep.HARDWARE_DETECTION

    await wizard.reset()
    assert wizard.current_step == SetupStep.NOT_STARTED
    assert not wizard.is_complete


@pytest.mark.asyncio
async def test_wizard_status(config_service: ConfigService, wifi_service: WifiService) -> None:
    wizard = SetupWizard(config_service, wifi_service)
    await wizard.start()

    status = wizard.status()
    assert status["current_step"] == "not_started"
    assert status["is_complete"] is False
    assert status["hardware"] is None


# --- H9: hardware fingerprint is stable ---

def _make_wizard_for_fingerprint(config_service, wifi_service) -> SetupWizard:
    return SetupWizard(config_service, wifi_service)


@pytest.mark.asyncio
async def test_fingerprint_ignores_alsa_card_number(
    config_service: ConfigService, wifi_service: WifiService
) -> None:
    """H9: hw:0 ↔ hw:1 swaps must not invalidate the fingerprint."""
    from core.hardware.detect import AudioOutput, HardwareProfile, PiModel

    wizard = _make_wizard_for_fingerprint(config_service, wifi_service)

    base_pi = PiModel(model="Pi 3B+", ram_mb=1024)
    profile_a = HardwareProfile(
        pi=base_pi,
        rfid_reader="rc522",
        rfid_device="/dev/spidev0.0",
        audio_outputs=[
            AudioOutput(name="HifiBerry DAC", type="i2s", device="hw:0"),
            AudioOutput(name="HDMI Audio", type="hdmi", device="hw:1"),
        ],
        gyro_detected=True,
    )
    profile_b = HardwareProfile(
        pi=base_pi,
        rfid_reader="rc522",
        rfid_device="/dev/spidev0.0",
        audio_outputs=[
            AudioOutput(name="HifiBerry DAC", type="i2s", device="hw:1"),
            AudioOutput(name="HDMI Audio", type="hdmi", device="hw:0"),
        ],
        gyro_detected=True,
    )
    assert wizard._compute_hardware_fingerprint(profile_a) == wizard._compute_hardware_fingerprint(profile_b)


# --- TASK 4: audio overlay activation + requires_reboot ---


def _pi_profile(audio_outputs: list[AudioOutput]) -> HardwareProfile:
    return HardwareProfile(
        pi=PiModel(model="Pi 3B+", ram_mb=1024),
        rfid_reader="rc522",
        audio_outputs=audio_outputs,
        gyro_detected=False,
        is_mock=False,
    )


@pytest.mark.asyncio
async def test_setup_audio_mock_no_reboot(
    config_service: ConfigService, wifi_service: WifiService
) -> None:
    """On a dev/mock box selecting audio never triggers a reboot."""
    wizard = SetupWizard(config_service, wifi_service)
    await wizard.start()
    result = await wizard.setup_audio("hw:0")
    assert result["success"] is True
    assert result["device"] == "hw:0"
    assert result["requires_reboot"] is False


@pytest.mark.asyncio
async def test_setup_audio_already_active_no_overlay_call(
    config_service: ConfigService, wifi_service: WifiService
) -> None:
    """Choosing a device whose type is already live → no helper call, no reboot."""
    wizard = SetupWizard(config_service, wifi_service)
    await wizard.start()
    # I2S DAC already detected live → overlay already baked in.
    wizard._hardware = _pi_profile([
        AudioOutput(name="HifiBerry DAC", type="i2s", device="hw:0"),
    ])

    with patch(
        "core.services.setup_wizard.async_run",
        new=AsyncMock(return_value=(0, "", "")),
    ) as run:
        result = await wizard.setup_audio("hw:0")

    assert result["requires_reboot"] is False
    run.assert_not_called()
    assert await config_service.get("audio.reboot_pending") in (None, False)


@pytest.mark.asyncio
async def test_setup_audio_flip_to_i2s_calls_helper_and_sets_reboot(
    config_service: ConfigService, wifi_service: WifiService
) -> None:
    """User picks an I2S DAC whose overlay isn't live yet → helper + reboot.

    detect_audio only lists active cards, so when only analog is live the user
    chooses a logical 'i2s'/DAC option. The chosen mode (i2s) is absent from
    the live outputs → flip + reboot pending.
    """
    wizard = SetupWizard(config_service, wifi_service)
    await wizard.start()
    # Live = onboard analog only (DAC overlay not applied yet).
    wizard._hardware = _pi_profile([
        AudioOutput(name="Onboard 3.5mm", type="analog", device="hw:0"),
    ])

    captured: list[list[str]] = []

    async def fake_run(cmd, **kwargs):
        captured.append(cmd)
        return (0, "I2S aktiviert", "")

    with patch("core.services.setup_wizard.async_run", new=fake_run):
        # The UI offers the DAC by a logical identifier that has no hw:N yet.
        result = await wizard.setup_audio("hifiberry-dac")

    assert result["requires_reboot"] is True
    assert await config_service.get("audio.reboot_pending") is True
    # Exactly one privileged helper call, with sudo -n + i2s mode.
    assert len(captured) == 1
    assert captured[0][:2] == ["sudo", "-n"]
    assert captured[0][-1] == "i2s"


@pytest.mark.asyncio
async def test_setup_audio_flip_helper_failure_no_reboot(
    config_service: ConfigService, wifi_service: WifiService
) -> None:
    """If the overlay helper fails, no reboot is claimed and nothing persists."""
    wizard = SetupWizard(config_service, wifi_service)
    await wizard.start()
    wizard._hardware = _pi_profile([
        AudioOutput(name="Onboard 3.5mm", type="analog", device="hw:0"),
    ])

    async def failing_run(cmd, **kwargs):
        return (1, "", "command not found")

    with patch("core.services.setup_wizard.async_run", new=failing_run):
        result = await wizard.setup_audio("hifiberry-dac")

    assert result["requires_reboot"] is False
    assert await config_service.get("audio.reboot_pending") in (None, False)


@pytest.mark.asyncio
async def test_setup_audio_hdmi_no_overlay(
    config_service: ConfigService, wifi_service: WifiService
) -> None:
    """HDMI/USB outputs are not overlay-controlled → never a reboot."""
    wizard = SetupWizard(config_service, wifi_service)
    await wizard.start()
    wizard._hardware = _pi_profile([
        AudioOutput(name="HDMI Audio", type="hdmi", device="hw:0"),
    ])

    with patch(
        "core.services.setup_wizard.async_run",
        new=AsyncMock(return_value=(0, "", "")),
    ) as run:
        result = await wizard.setup_audio("hw:0")

    assert result["requires_reboot"] is False
    run.assert_not_called()


@pytest.mark.asyncio
async def test_fingerprint_changes_when_hardware_actually_changes(
    config_service: ConfigService, wifi_service: WifiService
) -> None:
    """H9: adding or removing real hardware must still flip the fingerprint."""
    from core.hardware.detect import AudioOutput, HardwareProfile, PiModel

    wizard = _make_wizard_for_fingerprint(config_service, wifi_service)
    base_pi = PiModel(model="Pi 3B+", ram_mb=1024)

    without_dac = HardwareProfile(
        pi=base_pi,
        rfid_reader="rc522",
        audio_outputs=[AudioOutput(name="Eingebauter Audio-Ausgang (3.5mm)", type="analog", device="hw:0")],
        gyro_detected=False,
    )
    with_dac = HardwareProfile(
        pi=base_pi,
        rfid_reader="rc522",
        audio_outputs=[AudioOutput(name="HifiBerry DAC", type="i2s", device="hw:0")],
        gyro_detected=False,
    )
    assert wizard._compute_hardware_fingerprint(without_dac) != wizard._compute_hardware_fingerprint(with_dac)
