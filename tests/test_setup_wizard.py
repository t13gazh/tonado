"""Tests for the setup wizard service."""

from pathlib import Path

import pytest

from core.services.config_service import ConfigService
from core.services.setup_wizard import SetupStep, SetupWizard
from core.services.wifi_service import WifiService


@pytest.fixture
def wifi_service() -> WifiService:
    service = WifiService()
    # On Windows/non-Pi this will be in mock mode
    return service


@pytest.mark.asyncio
async def test_wizard_starts_not_complete(config_service: ConfigService, wifi_service: WifiService) -> None:
    wizard = SetupWizard(config_service, wifi_service)
    await wizard.start()
    assert not wizard.is_complete
    assert wizard.current_step == SetupStep.NOT_STARTED


@pytest.mark.asyncio
async def test_wizard_step_progression(config_service: ConfigService, wifi_service: WifiService) -> None:
    wizard = SetupWizard(config_service, wifi_service)
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

    # Complete
    result = await wizard.complete_setup()
    assert result["success"] is True
    assert wizard.is_complete


@pytest.mark.asyncio
async def test_wizard_persists_state(tmp_path: Path) -> None:
    db_path = tmp_path / "config.db"

    # First run: advance to WiFi step
    config1 = ConfigService(db_path)
    await config1.start()
    wifi = WifiService()
    wizard1 = SetupWizard(config1, wifi)
    await wizard1.start()
    await wizard1.detect_hardware()
    assert wizard1.current_step == SetupStep.HARDWARE_DETECTION
    await config1.stop()

    # Second run: should resume from saved state
    config2 = ConfigService(db_path)
    await config2.start()
    wizard2 = SetupWizard(config2, wifi)
    await wizard2.start()
    assert wizard2.current_step == SetupStep.HARDWARE_DETECTION
    await config2.stop()


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
