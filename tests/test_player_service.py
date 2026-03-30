"""Tests for PlayerService using MockMPDClient."""

import asyncio

import pytest
import pytest_asyncio

from core.services.event_bus import EventBus
from core.services.player_service import PlaybackState, PlayerService, RepeatMode
from tests.mock_mpd import MockMPDClient


@pytest_asyncio.fixture
async def player(event_bus: EventBus):
    """Create a PlayerService with a mock MPD client."""
    svc = PlayerService(event_bus=event_bus)
    svc._client = MockMPDClient()
    await svc.start()
    yield svc
    await svc.stop()


# --- Connection ---


@pytest.mark.asyncio
async def test_start_connects(player: PlayerService):
    assert player._connected is True
    assert player.health()["status"] == "connected"


@pytest.mark.asyncio
async def test_health_disconnected(event_bus: EventBus):
    svc = PlayerService(event_bus=event_bus)
    assert svc.health()["status"] == "disconnected"


# --- Playback control ---


@pytest.mark.asyncio
async def test_play_folder(player: PlayerService, event_bus: EventBus):
    events: list[dict] = []

    async def collect(state, **_):
        events.append(state)

    event_bus.subscribe("player_state_changed", collect)

    await player.play_folder("Music/Album1")

    assert player.state.state == PlaybackState.PLAYING
    assert player.state.current_uri == "Music/Album1"
    assert len(player.state.playlist) == 1
    assert len(events) > 0


@pytest.mark.asyncio
async def test_play_urls(player: PlayerService):
    urls = ["http://radio.example.com/stream1", "http://radio.example.com/stream2"]
    await player.play_urls(urls, start_index=0)

    assert player.state.state == PlaybackState.PLAYING
    assert player.state.current_uri == urls[0]
    assert len(player.state.playlist) == 2


@pytest.mark.asyncio
async def test_play_urls_start_index(player: PlayerService):
    urls = ["http://a.mp3", "http://b.mp3", "http://c.mp3"]
    await player.play_urls(urls, start_index=1)

    assert player.state.current_uri == urls[1]
    # Playlist: b.mp3 (playing) + c.mp3 (queued)
    assert len(player.state.playlist) == 2


@pytest.mark.asyncio
async def test_play_url_stream(player: PlayerService):
    await player.play_url("http://stream.example.com/live")
    assert player.state.state == PlaybackState.PLAYING
    assert player.state.current_uri == "http://stream.example.com/live"


@pytest.mark.asyncio
async def test_pause_resume(player: PlayerService):
    await player.play_folder("Music/Test")
    assert player.state.state == PlaybackState.PLAYING

    await player.pause()
    assert player.state.state == PlaybackState.PAUSED

    await player.play()
    assert player.state.state == PlaybackState.PLAYING


@pytest.mark.asyncio
async def test_toggle(player: PlayerService):
    await player.play_folder("Music/Test")
    await player.toggle()
    assert player.state.state == PlaybackState.PAUSED
    await player.toggle()
    assert player.state.state == PlaybackState.PLAYING


@pytest.mark.asyncio
async def test_stop_playback(player: PlayerService):
    await player.play_folder("Music/Test")
    await player.stop_playback()
    assert player.state.state == PlaybackState.STOPPED


# --- Navigation ---


@pytest.mark.asyncio
async def test_next_previous(player: PlayerService):
    urls = ["http://a.mp3", "http://b.mp3", "http://c.mp3"]
    await player.play_urls(urls)

    await player.next_track()
    assert player.state.playlist_position == 1

    await player.previous_track()
    assert player.state.playlist_position == 0


@pytest.mark.asyncio
async def test_next_at_end_no_crash(player: PlayerService):
    await player.play_url("http://single.mp3")
    # Should not crash, just log
    await player.next_track()


# --- Volume ---


@pytest.mark.asyncio
async def test_set_volume(player: PlayerService):
    await player.set_volume(75)
    assert player.state.volume == 75


@pytest.mark.asyncio
async def test_volume_clamped(player: PlayerService):
    await player.set_volume(150)
    assert player.state.volume == 100
    await player.set_volume(-10)
    assert player.state.volume == 0


@pytest.mark.asyncio
async def test_adjust_volume(player: PlayerService):
    await player.set_volume(50)
    await player.adjust_volume(10)
    assert player.state.volume == 60
    await player.adjust_volume(-20)
    assert player.state.volume == 40


# --- Seek ---


@pytest.mark.asyncio
async def test_seek(player: PlayerService):
    await player.play_folder("Music/Test")
    await player.seek(42.5)
    assert player.state.elapsed == 42.5


# --- Shuffle / Repeat ---


@pytest.mark.asyncio
async def test_toggle_random(player: PlayerService):
    assert player.state.shuffle is False
    result = await player.toggle_random()
    assert result is True
    assert player.state.shuffle is True
    result = await player.toggle_random()
    assert result is False


@pytest.mark.asyncio
async def test_cycle_repeat(player: PlayerService):
    assert player.state.repeat_mode == RepeatMode.OFF
    mode = await player.cycle_repeat()
    assert mode == RepeatMode.ALL
    mode = await player.cycle_repeat()
    assert mode == RepeatMode.SINGLE
    mode = await player.cycle_repeat()
    assert mode == RepeatMode.OFF


# --- Outputs ---


@pytest.mark.asyncio
async def test_list_outputs(player: PlayerService):
    outputs = await player.list_outputs()
    assert len(outputs) == 1
    assert outputs[0]["name"] == "Default"
    assert outputs[0]["enabled"] is True


@pytest.mark.asyncio
async def test_toggle_output(player: PlayerService):
    await player.toggle_output(0, False)
    outputs = await player.list_outputs()
    assert outputs[0]["enabled"] is False

    await player.toggle_output(0, True)
    outputs = await player.list_outputs()
    assert outputs[0]["enabled"] is True


# --- State serialization ---


@pytest.mark.asyncio
async def test_state_to_dict(player: PlayerService):
    await player.play_url("http://stream.example.com/live")
    d = player.state.to_dict()
    assert d["state"] == "playing"
    assert "is_stream" in d
    assert "loading" in d
    assert "shuffle" in d
    assert d["playlist_length"] == 1


# --- Disconnected graceful degradation ---


@pytest.mark.asyncio
async def test_operations_when_disconnected(event_bus: EventBus):
    svc = PlayerService(event_bus=event_bus)
    # All operations should be no-ops, not crash
    await svc.play_folder("test")
    await svc.play_url("http://test")
    await svc.play()
    await svc.pause()
    await svc.stop_playback()
    await svc.next_track()
    await svc.set_volume(50)
    await svc.seek(10)
    result = await svc.toggle_random()
    assert result is False
    elapsed = await svc.get_elapsed()
    assert elapsed == 0.0
    outputs = await svc.list_outputs()
    assert outputs == []
