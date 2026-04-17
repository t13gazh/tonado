"""Tests for the button service (H6)."""

import json

import pytest

from core.hardware.gpio_buttons import (
    ButtonAction,
    ButtonConfig,
    MockGpioButtonListener,
    MockGpioButtonScanner,
)
from core.services.button_service import CONFIG_KEY, ButtonService
from core.services.config_service import ConfigService
from core.services.event_bus import EventBus


@pytest.fixture
def scanner() -> MockGpioButtonScanner:
    return MockGpioButtonScanner()


@pytest.fixture
def listener() -> MockGpioButtonListener:
    return MockGpioButtonListener()


@pytest.fixture
async def service(
    scanner: MockGpioButtonScanner,
    listener: MockGpioButtonListener,
    event_bus: EventBus,
    config_service: ConfigService,
) -> ButtonService:
    svc = ButtonService(scanner, listener, event_bus, config_service)
    await svc.start()
    return svc


@pytest.mark.asyncio
async def test_start_without_config_reports_not_configured(service: ButtonService) -> None:
    assert service.has_buttons is False
    health = service.health()
    assert health["status"] == "not_configured"


@pytest.mark.asyncio
async def test_save_buttons_persists_to_config(
    service: ButtonService, config_service: ConfigService
) -> None:
    buttons = [
        ButtonConfig(action=ButtonAction.VOLUME_UP, gpio=23),
        ButtonConfig(action=ButtonAction.VOLUME_DOWN, gpio=24),
    ]
    await service.save_buttons(buttons)
    raw = await config_service.get(CONFIG_KEY)
    assert raw is not None
    data = json.loads(raw) if isinstance(raw, str) else raw
    assert len(data) == 2
    assert {b["action"] for b in data} == {"volume_up", "volume_down"}
    assert service.has_buttons
    health = service.health()
    assert health["status"] == "connected"
    assert "2 Tasten" in health["detail"]


@pytest.mark.asyncio
async def test_clear_buttons(
    service: ButtonService, config_service: ConfigService
) -> None:
    await service.save_buttons([ButtonConfig(action=ButtonAction.PLAY_PAUSE, gpio=17)])
    await service.clear_buttons()
    assert await config_service.get(CONFIG_KEY) is None
    assert service.has_buttons is False


@pytest.mark.asyncio
async def test_invalid_saved_config_is_ignored(
    scanner: MockGpioButtonScanner,
    listener: MockGpioButtonListener,
    event_bus: EventBus,
    config_service: ConfigService,
) -> None:
    """A corrupted button config in DB should not crash start()."""
    await config_service.set(CONFIG_KEY, "not json at all")
    svc = ButtonService(scanner, listener, event_bus, config_service)
    await svc.start()
    assert svc.has_buttons is False


@pytest.mark.asyncio
async def test_press_publishes_event(
    service: ButtonService,
    listener: MockGpioButtonListener,
    event_bus: EventBus,
) -> None:
    await service.save_buttons([ButtonConfig(action=ButtonAction.NEXT_TRACK, gpio=26)])

    received: list[dict] = []

    async def on_press(**payload):
        received.append(payload)

    event_bus.subscribe("button_pressed", on_press)
    await listener.simulate_press(ButtonAction.NEXT_TRACK)

    assert len(received) == 1
    assert received[0]["action"] == "next_track"


@pytest.mark.asyncio
async def test_test_mode_records_events(
    service: ButtonService,
    listener: MockGpioButtonListener,
) -> None:
    buttons = [ButtonConfig(action=ButtonAction.VOLUME_UP, gpio=23)]
    await service.start_test(buttons=buttons)
    await listener.simulate_press(ButtonAction.VOLUME_UP)
    events = service.get_test_events()
    assert len(events) == 1
    assert events[0]["action"] == "volume_up"
    # get_test_events clears the queue
    assert service.get_test_events() == []
    await service.stop_test()


@pytest.mark.asyncio
async def test_test_mode_does_not_fire_bus_event(
    service: ButtonService,
    listener: MockGpioButtonListener,
    event_bus: EventBus,
) -> None:
    """In test mode, presses go into the test queue, not on the bus."""
    received: list[dict] = []

    async def on_press(**payload):
        received.append(payload)

    event_bus.subscribe("button_pressed", on_press)
    await service.start_test(buttons=[ButtonConfig(action=ButtonAction.PREV_TRACK, gpio=5)])
    await listener.simulate_press(ButtonAction.PREV_TRACK)
    assert received == []
    await service.stop_test()


@pytest.mark.asyncio
async def test_get_config_returns_serialisable(service: ButtonService) -> None:
    await service.save_buttons([ButtonConfig(action=ButtonAction.PLAY_PAUSE, gpio=17)])
    cfg = service.get_config()
    assert cfg == [{"action": "play_pause", "gpio": 17}]


@pytest.mark.asyncio
async def test_scan_roundtrip(service: ButtonService, scanner: MockGpioButtonScanner) -> None:
    await service.start_scan([5, 6, 13])
    scanner.simulate_press(6)
    result = await service.get_scan_result(timeout=1.0)
    assert result.gpio == 6
    assert result.detected is True
