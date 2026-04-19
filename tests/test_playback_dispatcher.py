"""Tests for PlaybackDispatcher — event-to-player action routing."""

import pytest
import pytest_asyncio

from core.playback_dispatcher import PlaybackDispatcher
from core.schemas.common import ContentType
from core.services.event_bus import EventBus
from core.services.player_service import PlayerService
from tests.mock_mpd import MockMPDClient


class FakeCardService:
    """Minimal mock for card_service.update_resume_position."""

    def __init__(self):
        self.saved_positions: dict[str, float] = {}

    async def update_resume_position(self, card_id: str, position: float) -> None:
        self.saved_positions[card_id] = position


class FakeStreamService:
    """Minimal mock for stream_service.list_episodes."""

    class Episode:
        def __init__(self, url: str):
            self.audio_url = url

    async def list_episodes(self, podcast_id: int):
        return [self.Episode(f"http://podcast/{podcast_id}/ep{i}") for i in range(3)]


class FakePlaylistService:
    """Minimal mock for playlist_service.get_playlist."""

    class Item:
        def __init__(self, path: str):
            self.content_path = path

    class Playlist:
        def __init__(self, items):
            self.items = items

    async def get_playlist(self, pl_id: int):
        return self.Playlist([self.Item(f"track{i}.mp3") for i in range(3)])


class FakeTimerService:
    """Minimal mock for timer_service."""

    def __init__(self):
        self.sleep_started = False

    async def save_resume_position(self, card_id: str) -> None:
        pass

    async def start_sleep_timer(self, minutes: float) -> None:
        self.sleep_started = True


@pytest_asyncio.fixture
async def setup(event_bus: EventBus):
    player = PlayerService(event_bus=event_bus)
    player._client = MockMPDClient()
    await player.start()

    card_svc = FakeCardService()
    stream_svc = FakeStreamService()
    playlist_svc = FakePlaylistService()
    timer_svc = FakeTimerService()

    dispatcher = PlaybackDispatcher(
        event_bus=event_bus,
        player=player,
        card_service=card_svc,
        stream_service=stream_svc,
        playlist_service=playlist_svc,
        timer_service=timer_svc,
    )

    yield player, dispatcher, card_svc, timer_svc, event_bus
    await player.stop()


@pytest.mark.asyncio
async def test_card_scanned_folder(setup):
    player, _, _, _, bus = setup
    await bus.publish("card_scanned", card_id="abc123", mapping={
        "content_type": ContentType.FOLDER,
        "content_path": "Music/Album1",
        "resume_position": 0,
    })
    assert player.state.state.value == "playing"
    assert player.state.current_uri == "Music/Album1"


@pytest.mark.asyncio
async def test_card_scanned_stream(setup):
    player, _, _, _, bus = setup
    await bus.publish("card_scanned", card_id="abc123", mapping={
        "content_type": ContentType.STREAM,
        "content_path": "http://radio.example.com/live",
        "resume_position": 0,
    })
    assert player.state.current_uri == "http://radio.example.com/live"


@pytest.mark.asyncio
async def test_card_scanned_podcast(setup):
    player, _, _, _, bus = setup
    await bus.publish("card_scanned", card_id="abc123", mapping={
        "content_type": ContentType.PODCAST,
        "content_path": "podcast:42",
        "resume_position": 0,
    })
    assert player.state.state.value == "playing"
    assert len(player.state.playlist) >= 1


@pytest.mark.asyncio
async def test_card_scanned_playlist(setup):
    player, _, _, _, bus = setup
    await bus.publish("card_scanned", card_id="abc123", mapping={
        "content_type": ContentType.PLAYLIST,
        "content_path": "playlist:1",
        "resume_position": 0,
    })
    assert player.state.state.value == "playing"


@pytest.mark.asyncio
async def test_card_scanned_command_sleep(setup):
    _, _, _, timer_svc, bus = setup
    await bus.publish("card_scanned", card_id="abc123", mapping={
        "content_type": ContentType.COMMAND,
        "content_path": "sleep_timer",
        "resume_position": 0,
    })
    assert timer_svc.sleep_started is True


@pytest.mark.asyncio
async def test_card_removed_pauses(setup):
    player, _, _, _, bus = setup
    await bus.publish("card_scanned", card_id="abc123", mapping={
        "content_type": ContentType.FOLDER,
        "content_path": "Music/Test",
        "resume_position": 0,
    })
    assert player.state.state.value == "playing"

    await bus.publish("card_removed", card_id="abc123", should_pause=True)
    assert player.state.state.value == "paused"


@pytest.mark.asyncio
async def test_card_removed_saves_resume(setup):
    player, _, card_svc, _, bus = setup
    # Play a folder
    await bus.publish("card_scanned", card_id="card1", mapping={
        "content_type": ContentType.FOLDER,
        "content_path": "Music/Test",
        "resume_position": 0,
    })
    # Simulate some playback
    await player.seek(42.0)

    await bus.publish("card_removed", card_id="card1", should_pause=False)
    assert card_svc.saved_positions.get("card1") == 42.0


@pytest.mark.asyncio
async def test_gesture_next_track(setup):
    player, _, _, _, bus = setup
    urls = ["http://a.mp3", "http://b.mp3"]
    await player.play_urls(urls)
    await bus.publish("gesture_detected", action="next_track")
    assert player.state.playlist_position == 1


@pytest.mark.asyncio
async def test_gesture_volume(setup):
    player, _, _, _, bus = setup
    await player.set_volume(50)
    await bus.publish("gesture_detected", action="volume_up")
    assert player.state.volume == 55
    await bus.publish("gesture_detected", action="volume_down")
    assert player.state.volume == 50


@pytest.mark.asyncio
async def test_gesture_shuffle(setup):
    """The shuffle gesture calls player.shuffle_play() — jumping to a
    random track in the current queue (not toggling the MPD random flag)."""
    from unittest.mock import AsyncMock

    player, _, _, _, bus = setup
    player.shuffle_play = AsyncMock()
    await bus.publish("gesture_detected", action="shuffle")
    player.shuffle_play.assert_awaited_once()


# --- current_source tracking (FLAG B1) ---


@pytest.mark.asyncio
async def test_current_source_set_on_folder_scan(setup):
    _, dispatcher, _, _, bus = setup
    assert dispatcher.current_source is None
    await bus.publish("card_scanned", card_id="c1", mapping={
        "content_type": ContentType.FOLDER,
        "content_path": "Music/Album1",
        "resume_position": 0,
    })
    src = dispatcher.current_source
    assert src is not None
    assert src["type"] == str(ContentType.FOLDER)
    assert src["content_path"] == "Music/Album1"


@pytest.mark.asyncio
async def test_current_source_set_on_stream_scan(setup):
    _, dispatcher, _, _, bus = setup
    await bus.publish("card_scanned", card_id="c2", mapping={
        "content_type": ContentType.STREAM,
        "content_path": "http://radio.example.com/live",
        "resume_position": 0,
    })
    src = dispatcher.current_source
    assert src is not None
    assert src["type"] == str(ContentType.STREAM)
    assert src["content_path"] == "http://radio.example.com/live"


@pytest.mark.asyncio
async def test_current_source_set_on_podcast_marker(setup):
    _, dispatcher, _, _, bus = setup
    await bus.publish("card_scanned", card_id="c3", mapping={
        "content_type": ContentType.PODCAST,
        "content_path": "podcast:42",
        "resume_position": 0,
    })
    src = dispatcher.current_source
    assert src is not None
    assert src["type"] == str(ContentType.PODCAST)
    assert src["id"] == 42


@pytest.mark.asyncio
async def test_current_source_cleared_on_stop_action(setup):
    _, dispatcher, _, _, bus = setup
    await bus.publish("card_scanned", card_id="c4", mapping={
        "content_type": ContentType.FOLDER,
        "content_path": "Music/Album1",
        "resume_position": 0,
    })
    assert dispatcher.current_source is not None
    await bus.publish("gesture_detected", action="stop")
    assert dispatcher.current_source is None


@pytest.mark.asyncio
async def test_set_and_clear_source_directly(setup):
    """Routers use set_source / clear_source directly — verify the public API."""
    _, dispatcher, _, _, _ = setup
    dispatcher.set_source(ContentType.FOLDER, "Hoerspiele")
    src = dispatcher.current_source
    assert src is not None and src["type"] == str(ContentType.FOLDER)
    assert src["content_path"] == "Hoerspiele"

    dispatcher.clear_source()
    assert dispatcher.current_source is None
