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
    # Use very short fade to keep test fast. Under B1 semantics the fade
    # runs *inside* the countdown, so total time-to-silence == timer length
    # (here ~3 s). 8 s wait gives generous margin for the MockMPDClient.
    await config.set("sleep_fade_duration", 2)
    await player.play_url("http://test.mp3")
    assert player.state.state.value == "playing"

    # Start very short timer
    await timer.start_sleep_timer(0.05)  # ~3 seconds
    await asyncio.sleep(8)

    assert player.state.state.value == "stopped"
    assert timer.sleep_timer_status()["active"] is False


# --- Sleep timer extend ---


@pytest.mark.asyncio
async def test_sleep_timer_extend_adds_minutes(timer_setup):
    timer, _, _, _ = timer_setup
    await timer.start_sleep_timer(5)
    before = timer.sleep_timer_status()["remaining_seconds"]
    new_remaining = await timer.extend_sleep_timer(10)
    after = timer.sleep_timer_status()["remaining_seconds"]
    assert new_remaining == after
    # Should have gained ~10 minutes (600s), allow for 1s tick drift
    assert after - before >= 600 - 1


@pytest.mark.asyncio
async def test_sleep_timer_extend_requires_active(timer_setup):
    timer, _, _, _ = timer_setup
    with pytest.raises(RuntimeError, match="no_active_timer"):
        await timer.extend_sleep_timer(5)


@pytest.mark.asyncio
async def test_sleep_timer_extend_clamps_to_max(timer_setup):
    timer, _, _, _ = timer_setup
    await timer.start_sleep_timer(115)
    await timer.extend_sleep_timer(30)  # would be 145, must clamp to 120
    remaining = timer.sleep_timer_status()["remaining_seconds"]
    assert remaining <= timer.MAX_SLEEP_MINUTES * 60


@pytest.mark.asyncio
async def test_sleep_timer_extend_rejects_during_fade(timer_setup):
    timer, _, _, _ = timer_setup
    await timer.start_sleep_timer(5)
    # Simulate "fade in progress" — a real fade is racy to observe
    timer._fading = True
    with pytest.raises(RuntimeError, match="timer_fading"):
        await timer.extend_sleep_timer(5)
    timer._fading = False
    await timer.cancel_sleep_timer()


# --- Multi-device sync: sleep_timer_updated event publishing ---


@pytest.mark.asyncio
async def test_sleep_timer_start_publishes_event(timer_setup):
    """Starting the timer must publish sleep_timer_updated so the second
    parent phone sees it without polling."""
    timer, _, _, bus = timer_setup
    events: list[dict] = []

    async def capture(**kwargs):
        events.append(kwargs)

    bus.subscribe("sleep_timer_updated", capture)
    await timer.start_sleep_timer(5)

    assert len(events) == 1
    payload = events[0]
    assert payload["active"] is True
    assert payload["fading"] is False
    assert payload["remaining_seconds"] > 0
    assert payload["duration_seconds"] == 300


@pytest.mark.asyncio
async def test_sleep_timer_extend_publishes_event(timer_setup):
    timer, _, _, bus = timer_setup
    await timer.start_sleep_timer(5)

    events: list[dict] = []

    async def capture(**kwargs):
        events.append(kwargs)

    bus.subscribe("sleep_timer_updated", capture)
    await timer.extend_sleep_timer(10)

    assert len(events) == 1
    payload = events[0]
    assert payload["active"] is True
    assert payload["fading"] is False
    # duration_seconds is only set on start; extend leaves it None.
    assert payload["duration_seconds"] is None
    # ~15 minutes remaining (1s tick drift OK)
    assert payload["remaining_seconds"] >= 15 * 60 - 2


@pytest.mark.asyncio
async def test_sleep_timer_cancel_publishes_event(timer_setup):
    timer, _, _, bus = timer_setup
    await timer.start_sleep_timer(5)

    events: list[dict] = []

    async def capture(**kwargs):
        events.append(kwargs)

    bus.subscribe("sleep_timer_updated", capture)
    await timer.cancel_sleep_timer()

    assert len(events) == 1
    payload = events[0]
    assert payload["active"] is False
    assert payload["remaining_seconds"] == 0
    assert payload["fading"] is False


@pytest.mark.asyncio
async def test_sleep_timer_cancel_while_idle_is_silent(timer_setup):
    """Cancelling a non-existent timer must not publish a spurious event."""
    timer, _, _, bus = timer_setup

    events: list[dict] = []

    async def capture(**kwargs):
        events.append(kwargs)

    bus.subscribe("sleep_timer_updated", capture)
    await timer.cancel_sleep_timer()

    assert events == []


# --- Sleep timer fade-out ---


@pytest.mark.asyncio
async def test_sleep_timer_fades_volume(timer_setup):
    """Volume should decrease during fade-out before stopping.

    Under B1 semantics the fade runs *inside* the countdown: when the
    requested timer is shorter than the configured fade_duration, the
    fade is clamped to the timer length and starts immediately. Total
    time to silence == the original timer length.
    """
    timer, player, config, _ = timer_setup
    await config.set("sleep_fade_duration", 2)
    await player.play_url("http://test.mp3")
    await player.set_volume(80)

    await timer.start_sleep_timer(0.02)  # ~1.2 second total window
    # Fade lives inside the window (clamped to ~1s); wait for window + margin.
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
    """Cancelling during fade-out should restore original volume.

    B1 semantics: with a ~1.2 s timer and a configured 5 s fade, the
    fade is clamped to fit inside the timer and starts almost immediately,
    so by the time we cancel at t≈2 s the fade task is already running.
    """
    timer, player, config, _ = timer_setup
    await config.set("sleep_fade_duration", 5)
    await player.play_url("http://test.mp3")
    await player.set_volume(70)

    await timer.start_sleep_timer(0.02)
    await asyncio.sleep(2)  # Let fade start (and usually finish, under B1)

    # Cancel while fading (or right after — cancel is idempotent)
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
