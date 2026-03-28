"""Player service controlling audio playback via MPD."""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from mpd.asyncio import MPDClient

from core.services.event_bus import EventBus

logger = logging.getLogger(__name__)


class PlaybackState(StrEnum):
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class PlayerState:
    """Current player state broadcast via WebSocket."""

    state: PlaybackState = PlaybackState.STOPPED
    volume: int = 50
    current_track: str = ""
    current_album: str = ""
    elapsed: float = 0.0
    duration: float = 0.0
    playlist: list[str] = field(default_factory=list)
    playlist_position: int = -1

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "volume": self.volume,
            "current_track": self.current_track,
            "current_album": self.current_album,
            "elapsed": self.elapsed,
            "duration": self.duration,
            "playlist_length": len(self.playlist),
            "playlist_position": self.playlist_position,
        }


class PlayerService:
    """Controls MPD for audio playback. Publishes state changes to event bus."""

    def __init__(self, event_bus: EventBus, host: str = "localhost", port: int = 6600) -> None:
        self._event_bus = event_bus
        self._host = host
        self._port = port
        self._client = MPDClient()
        self._state = PlayerState()
        self._idle_task: asyncio.Task | None = None
        self._connected = False

    @property
    def state(self) -> PlayerState:
        return self._state

    async def start(self) -> None:
        """Connect to MPD and start listening for state changes."""
        try:
            await self._client.connect(self._host, self._port)
            self._connected = True
            logger.info("Connected to MPD at %s:%d", self._host, self._port)
            await self._sync_state()
            self._idle_task = asyncio.create_task(self._idle_loop())
        except (ConnectionRefusedError, OSError) as e:
            logger.warning("Could not connect to MPD: %s. Player will be unavailable.", e)
            self._connected = False

    async def stop(self) -> None:
        """Disconnect from MPD."""
        if self._idle_task:
            self._idle_task.cancel()
            try:
                await self._idle_task
            except asyncio.CancelledError:
                pass
        if self._connected:
            self._client.disconnect()
            self._connected = False

    async def play_folder(self, folder_path: str, resume_position: float = 0) -> None:
        """Clear queue, load folder, and start playback."""
        if not self._connected:
            return
        await self._client.clear()
        await self._client.add(folder_path)
        await self._client.play(0)
        if resume_position > 0:
            await self._client.seekcur(resume_position)
        await self._sync_state()

    async def play_url(self, url: str) -> None:
        """Clear queue, add stream URL, and start playback."""
        if not self._connected:
            return
        await self._client.clear()
        await self._client.add(url)
        await self._client.play(0)
        await self._sync_state()

    async def play(self) -> None:
        """Resume playback."""
        if not self._connected:
            return
        await self._client.pause(0)
        await self._sync_state()

    async def pause(self) -> None:
        """Pause playback."""
        if not self._connected:
            return
        await self._client.pause(1)
        await self._sync_state()

    async def toggle(self) -> None:
        """Toggle play/pause."""
        if self._state.state == PlaybackState.PLAYING:
            await self.pause()
        else:
            await self.play()

    async def stop_playback(self) -> None:
        """Stop playback entirely."""
        if not self._connected:
            return
        await self._client.stop()
        await self._sync_state()

    async def next_track(self) -> None:
        """Skip to next track."""
        if not self._connected:
            return
        try:
            await self._client.next()
        except Exception:
            logger.debug("No next track available")
        await self._sync_state()

    async def previous_track(self) -> None:
        """Skip to previous track."""
        if not self._connected:
            return
        try:
            await self._client.previous()
        except Exception:
            logger.debug("No previous track available")
        await self._sync_state()

    async def set_volume(self, volume: int) -> None:
        """Set volume (0-100)."""
        if not self._connected:
            return
        volume = max(0, min(100, volume))
        try:
            await self._client.setvol(volume)
        except Exception:
            logger.warning("Mixer not available, volume control disabled")
            return
        self._state.volume = volume
        await self._publish_state()

    async def adjust_volume(self, delta: int) -> None:
        """Adjust volume by delta."""
        await self.set_volume(self._state.volume + delta)

    async def seek(self, position: float) -> None:
        """Seek to position in seconds."""
        if not self._connected:
            return
        await self._client.seekcur(position)
        await self._sync_state()

    async def shuffle(self) -> None:
        """Shuffle the current playlist."""
        if not self._connected:
            return
        await self._client.shuffle()
        await self._sync_state()

    async def get_elapsed(self) -> float:
        """Get current elapsed position in seconds."""
        if not self._connected:
            return 0.0
        status = await self._client.status()
        return float(status.get("elapsed", 0))

    async def _sync_state(self) -> None:
        """Read MPD state and update local state."""
        if not self._connected:
            return
        try:
            status = await self._client.status()
            mpd_state = status.get("state", "stop")
            state_map = {"play": "playing", "pause": "paused", "stop": "stopped"}
            self._state.state = PlaybackState(state_map.get(mpd_state, "stopped"))
            self._state.volume = int(status.get("volume", 50))
            self._state.elapsed = float(status.get("elapsed", 0))
            self._state.duration = float(status.get("duration", 0))

            song = status.get("song")
            if song is not None:
                self._state.playlist_position = int(song)
                try:
                    current = await self._client.currentsong()
                    self._state.current_track = current.get("title", current.get("file", ""))
                    self._state.current_album = current.get("album", "")
                except Exception:
                    pass

            playlist_info = await self._client.playlistinfo()
            self._state.playlist = [t.get("file", "") for t in playlist_info]
        except Exception as e:
            logger.error("Failed to sync MPD state: %s", e)

        await self._publish_state()

    async def _publish_state(self) -> None:
        """Publish current state to event bus."""
        await self._event_bus.publish("player_state_changed", state=self._state.to_dict())

    async def _idle_loop(self) -> None:
        """Listen for MPD subsystem changes and sync state."""
        while self._connected:
            try:
                async for _ in self._client.idle(["player", "mixer", "playlist"]):
                    await self._sync_state()
                    break  # Process one event, then re-enter idle
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("MPD idle error: %s", e)
                await asyncio.sleep(1)
