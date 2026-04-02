"""Tests for TimerService — sleep timer, volume enforcement, idle shutdown."""

import asyncio

import pytest
import pytest_asyncio

from core.services.config_service import ConfigService
from core.services.event_bus import EventBus
from core.services.player_service import PlayerService
from core.services.timer_service import TimerService
from tests.mock_mpd import MockMPDClient


@pytest_asyncio.fixture
async def timer_setup(event_bus: EventBus, config_service: ConfigService):
    player = PlayerService(event_bus=event_bus)
    player._client = MockMPDClient()
    await player.start()

    timer = TimerService(event_bus, player, config_service)
    await timer.start()

    yield timer, player, config_service, event_bus

    await timer.stop()
    await player.stop()


# --- Sleep timer ---


@pytest.mark.asyncio
async def test_sleep_timer_status_default(timer_setup):
    timer, _, _, _ = timer_setup
    status = timer.sleep_timer_status()
    assert status["active"] is False
    assert status["remaining_seconds"] == 0


@pytest.mark.asyncio
async def test_sleep_timer_start(timer_setup):
    timer, _, _, _ = timer_setup
    await timer.start_sleep_timer(5)
    status = timer.sleep_timer_status()
    assert status["active"] is True
    assert status["remaining_seconds"] > 0


@pytest.mark.asyncio
async def test_sleep_timer_cancel(timer_setup):
    timer, _, _, _ = timer_setup
    await timer.start_sleep_timer(5)
    await timer.cancel_sleep_timer()
    status = timer.sleep_timer_status()
    assert status["active"] is False
    assert status["remaining_seconds"] == 0


@pytest.mark.asyncio
async def test_sleep_timer_stops_playback(timer_setup):
    timer, player, config, _ = timer_setup
    # Use very short fade to keep test fast
    await config.set("sleep_fade_duration", 2)
    await player.play_url("http://test.mp3")
    assert player.state.state.value == "playing"

    # Start very short timer
    await timer.start_sleep_timer(0.05)  # ~3 seconds
    await asyncio.sleep(8)

    assert player.state.state.value == "stopped"
    assert timer.sleep_timer_status()["active"] is False


# --- Sleep timer fade-out ---


@pytest.mark.asyncio
async def test_sleep_timer_fades_volume(timer_setup):
    """Volume should decrease during fade-out before stopping."""
    timer, player, config, _ = timer_setup
    await config.set("sleep_fade_duration", 2)
    await player.play_url("http://test.mp3")
    await player.set_volume(80)

    await timer.start_sleep_timer(0.02)  # ~1.2 second countdown
    # Wait for countdown + fade (1.2s + 2s) + margin
    await asyncio.sleep(6)

    assert player.state.state.value == "stopped"
    # Volume restored after stop
    assert player.state.volume == 80


@pytest.mark.asyncio
async def test_sleep_timer_status_shows_fading(timer_setup):
    """Status should include fading flag."""
    timer, player, config, _ = timer_setup
    await config.set("sleep_fade_duration", 3)
    await player.play_url("http://test.mp3")

    status = timer.sleep_timer_status()
    assert "fading" in status
    assert status["fading"] is False


@pytest.mark.asyncio
async def test_sleep_fade_cancel_restores_volume(timer_setup):
    """Cancelling during fade-out should restore original volume."""
    timer, player, config, _ = timer_setup
    await config.set("sleep_fade_duration", 5)
    await player.play_url("http://test.mp3")
    await player.set_volume(70)

    await timer.start_sleep_timer(0.02)
    await asyncio.sleep(2)  # Let fade start

    # Cancel while fading
    await timer.cancel_sleep_timer()

    # Volume should be restored
    assert player.state.volume == 70
    assert timer._fading is False


@pytest.mark.asyncio
async def test_sleep_fade_default_duration(timer_setup):
    """Without config, fade duration should use default (30s)."""
    timer, _, _, _ = timer_setup
    assert timer.DEFAULT_FADE_DURATION == 30


# --- Volume enforcement ---


@pytest.mark.asyncio
async def test_volume_enforcement(timer_setup):
    timer, player, config, bus = timer_setup
    await config.set("player.max_volume", 60)
    # Invalidate cache
    await bus.publish("config_changed", key="player.max_volume", value=60)

    await player.set_volume(80)
    # Trigger enforcement via player_state_changed event
    await bus.publish("player_state_changed", state=player.state.to_dict())

    assert player.state.volume <= 60


@pytest.mark.asyncio
async def test_volume_under_limit_unchanged(timer_setup):
    timer, player, config, bus = timer_setup
    await config.set("player.max_volume", 80)
    await bus.publish("config_changed", key="player.max_volume", value=80)

    await player.set_volume(50)
    await bus.publish("player_state_changed", state=player.state.to_dict())

    assert player.state.volume == 50


# --- Resume tracking ---


@pytest.mark.asyncio
async def test_save_resume_position(timer_setup):
    timer, player, _, bus = timer_setup
    await player.play_url("http://audiobook.mp3")
    await player.seek(120.5)

    events: list[dict] = []

    async def capture(**kwargs):
        events.append(kwargs)

    bus.subscribe("resume_position_save", capture)
    await timer.save_resume_position("card123")

    assert len(events) == 1
    assert events[0]["card_id"] == "card123"
    assert events[0]["position"] == 120.5
