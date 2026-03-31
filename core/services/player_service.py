"""Player service controlling audio playback via MPD."""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable

from mpd.asyncio import MPDClient

from core.services.base import BaseService
from core.services.event_bus import EventBus

logger = logging.getLogger(__name__)


class PlaybackState(StrEnum):
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"


class RepeatMode(StrEnum):
    OFF = "off"
    ALL = "all"
    SINGLE = "single"


@dataclass
class PlayerState:
    """Current player state broadcast via WebSocket."""

    state: PlaybackState = PlaybackState.STOPPED
    volume: int = 50
    current_track: str = ""
    current_album: str = ""
    current_uri: str = ""
    elapsed: float = 0.0
    duration: float = 0.0
    playlist: list[str] = field(default_factory=list)
    playlist_position: int = -1
    repeat_mode: RepeatMode = RepeatMode.OFF
    shuffle: bool = False
    loading: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "volume": self.volume,
            "current_track": self.current_track,
            "current_album": self.current_album,
            "current_uri": self.current_uri,
            "is_stream": self.current_uri.startswith(("http://", "https://")) and self.duration == 0,
            "elapsed": self.elapsed,
            "duration": self.duration,
            "loading": self.loading,
            "playlist_length": len(self.playlist),
            "playlist_position": self.playlist_position,
            "repeat_mode": self.repeat_mode.value,
            "shuffle": self.shuffle,
        }


class PlayerService(BaseService):
    """Controls MPD for audio playback. Publishes state changes to event bus."""

    def __init__(self, event_bus: EventBus, host: str = "localhost", port: int = 6600) -> None:
        super().__init__()
        self._event_bus = event_bus
        self._host = host
        self._port = port
        self._client = MPDClient()
        self._state = PlayerState()
        self._idle_task: asyncio.Task | None = None
        self._elapsed_task: asyncio.Task | None = None
        self._connected = False
        self._has_listeners: Callable[[], bool] | None = None

    def set_listener_check(self, check: Callable[[], bool]) -> None:
        """Set a callback that returns True when broadcast listeners exist.

        Used by _elapsed_loop to skip publishing when no clients are connected.
        """
        self._has_listeners = check

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
            self._elapsed_task = asyncio.create_task(self._elapsed_loop())
        except (ConnectionRefusedError, OSError) as e:
            logger.warning("Could not connect to MPD: %s. Player will be unavailable.", e)
            self._connected = False

    async def stop(self) -> None:
        """Disconnect from MPD."""
        for task in (self._idle_task, self._elapsed_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._connected:
            self._client.disconnect()
            self._connected = False

    def health(self) -> dict:
        """Return MPD connection health."""
        if self._connected:
            return {"status": "connected", "detail": f"{self._host}:{self._port}"}
        return {"status": "disconnected", "detail": "MPD nicht erreichbar"}

    async def play_folder(self, folder_path: str, resume_position: float = 0, start_index: int = 0) -> None:
        """Clear queue, load folder, and start playback at given track index."""
        if not self._connected:
            return
        self._state.loading = True
        await self._client.stop()
        await self._client.clear()
        await self._client.add(folder_path)
        await self._client.play(start_index)
        if resume_position > 0:
            await self._client.seekcur(resume_position)
        await self._sync_state()

    async def play_urls(self, urls: list[str], start_index: int = 0, resume_position: float = 0) -> None:
        """Clear queue, add URLs from start_index onward, play immediately."""
        if not self._connected:
            return
        self._state.loading = True
        await self._client.stop()
        await asyncio.sleep(0.3)
        await self._client.clear()
        # Add the selected track and start playback immediately
        await self._client.add(urls[start_index])
        await self._client.play(0)
        if resume_position > 0:
            await self._client.seekcur(resume_position)
        # Queue remaining tracks after the selected one
        for url in urls[start_index + 1:]:
            await self._client.add(url)
        await self._sync_state()

    async def play_url(self, url: str) -> None:
        """Clear queue, add stream URL, and start playback."""
        if not self._connected:
            return
        self._state.loading = True
        await self._client.stop()
        await asyncio.sleep(0.3)
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

    async def list_outputs(self) -> list[dict]:
        """List MPD audio outputs."""
        if not self._connected:
            return []
        outputs = await self._client.outputs()
        return [{"id": int(o["outputid"]), "name": o["outputname"], "enabled": o["outputenabled"] == "1"} for o in outputs]

    async def toggle_output(self, output_id: int, enabled: bool) -> None:
        """Enable or disable an MPD audio output."""
        if not self._connected:
            return
        if enabled:
            await self._client.enableoutput(output_id)
        else:
            await self._client.disableoutput(output_id)

    async def seek(self, position: float) -> None:
        """Seek to position in seconds."""
        if not self._connected:
            return
        await self._client.seekcur(position)
        await self._sync_state()

    async def toggle_random(self) -> bool:
        """Toggle MPD random (shuffle) mode on/off."""
        if not self._connected:
            return False
        new_state = 0 if self._state.shuffle else 1
        await self._client.random(new_state)
        self._state.shuffle = new_state == 1
        await self._publish_state()
        return self._state.shuffle

    async def cycle_repeat(self) -> RepeatMode:
        """Cycle through repeat modes: off → all → single → off."""
        if not self._connected:
            return RepeatMode.OFF
        if self._state.repeat_mode == RepeatMode.OFF:
            await self._client.repeat(1)
            await self._client.single(0)
            self._state.repeat_mode = RepeatMode.ALL
        elif self._state.repeat_mode == RepeatMode.ALL:
            await self._client.repeat(1)
            await self._client.single(1)
            self._state.repeat_mode = RepeatMode.SINGLE
        else:
            await self._client.repeat(0)
            await self._client.single(0)
            self._state.repeat_mode = RepeatMode.OFF
        await self._publish_state()
        return self._state.repeat_mode

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

            # Clear loading flag once MPD reports actual playback
            if self._state.loading and mpd_state == "play" and (self._state.elapsed > 0 or self._state.duration > 0):
                self._state.loading = False

            # Sync shuffle (random) mode from MPD
            self._state.shuffle = status.get("random", "0") == "1"

            # Sync repeat mode from MPD
            repeat = status.get("repeat", "0")
            single = status.get("single", "0")
            if repeat == "1" and single == "1":
                self._state.repeat_mode = RepeatMode.SINGLE
            elif repeat == "1":
                self._state.repeat_mode = RepeatMode.ALL
            else:
                self._state.repeat_mode = RepeatMode.OFF

            song = status.get("song")
            if song is not None:
                self._state.playlist_position = int(song)
                try:
                    current = await self._client.currentsong()
                    self._state.current_uri = current.get("file", "")
                    self._state.current_track = current.get("title", self._state.current_uri)
                    self._state.current_album = current.get("album", "")
                except Exception:
                    pass
            else:
                self._state.playlist_position = -1

            status_pl_length = int(status.get("playlistlength", 0))
            # Only reload full playlist if length changed
            if status_pl_length != len(self._state.playlist):
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
                async for _ in self._client.idle(["player", "mixer", "playlist", "options"]):
                    await self._sync_state()
                    break  # Process one event, then re-enter idle
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("MPD idle error: %s", e)
                await asyncio.sleep(1)

    async def _elapsed_loop(self) -> None:
        """Periodically update elapsed time during playback for smooth progress.

        Skips publishing when no WebSocket clients are connected to avoid
        unnecessary JSON serialization and event bus overhead on Pi Zero W.
        """
        while self._connected:
            try:
                await asyncio.sleep(1)
                if self._state.state == PlaybackState.PLAYING:
                    self._state.elapsed += 1.0
                    if self._state.elapsed > self._state.duration and self._state.duration > 0:
                        self._state.elapsed = self._state.duration
                    # Only publish if someone is listening (WebSocket clients connected)
                    if self._has_listeners is None or self._has_listeners():
                        await self._publish_state()
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1)
