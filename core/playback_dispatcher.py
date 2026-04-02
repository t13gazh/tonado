"""Playback dispatcher — translates card/gesture events into player actions.

Extracted from lifespan() to keep main.py focused on service wiring.
"""

import logging

from core.schemas.common import ContentType
from core.services.card_service import CardService
from core.services.event_bus import EventBus
from core.services.player_service import PlayerService
from core.services.playlist_service import PlaylistService
from core.services.stream_service import StreamService
from core.services.timer_service import TimerService

logger = logging.getLogger(__name__)


class PlaybackDispatcher:
    """Wires event bus events to player actions."""

    def __init__(
        self,
        event_bus: EventBus,
        player: PlayerService,
        card_service: CardService,
        stream_service: StreamService,
        playlist_service: PlaylistService,
        timer_service: TimerService,
    ) -> None:
        self._player = player
        self._card_service = card_service
        self._stream_service = stream_service
        self._playlist_service = playlist_service
        self._timer_service = timer_service
        self._current_card_id: str | None = None

        event_bus.subscribe("card_scanned", self._on_card_scanned)
        event_bus.subscribe("card_removed", self._on_card_removed)
        event_bus.subscribe("gesture_detected", self._on_gesture)
        event_bus.subscribe("button_pressed", self._on_button_pressed)
        event_bus.subscribe("resume_position_save", self._on_resume_save)

    async def _on_card_scanned(self, card_id: str, mapping: dict, **_) -> None:
        # Save resume position of previous card
        if self._current_card_id and self._current_card_id != card_id:
            await self._timer_service.save_resume_position(self._current_card_id)
        self._current_card_id = card_id

        content_type = mapping["content_type"]
        content_path = mapping["content_path"]
        resume = mapping.get("resume_position", 0)

        if content_type == ContentType.FOLDER:
            await self._player.play_folder(content_path, resume_position=resume)
        elif content_type == ContentType.STREAM:
            await self._player.play_url(content_path)
        elif content_type == ContentType.PODCAST:
            if content_path.startswith("podcast:"):
                try:
                    podcast_id = int(content_path.split(":")[1])
                    episodes = await self._stream_service.list_episodes(podcast_id)
                    if episodes:
                        urls = [ep.audio_url for ep in episodes]
                        await self._player.play_urls(urls, resume_position=resume)
                except (ValueError, IndexError):
                    logger.warning("Invalid podcast path: %s", content_path)
            else:
                await self._player.play_url(content_path)
        elif content_type == ContentType.PLAYLIST:
            try:
                pl_id = int(content_path.split(":")[-1])
                playlist = await self._playlist_service.get_playlist(pl_id)
                if playlist and playlist.items:
                    urls = [item.content_path for item in playlist.items]
                    await self._player.play_urls(urls, resume_position=resume)
            except (ValueError, IndexError):
                logger.warning("Invalid playlist path: %s", content_path)
        elif content_type == ContentType.COMMAND:
            await self._execute_command(content_path)

    async def _execute_command(self, cmd: str) -> None:
        """Execute a box-control command triggered by a card."""
        if cmd == "sleep_timer":
            await self._timer_service.start_sleep_timer(30)
        elif cmd.startswith("volume:"):
            try:
                vol = int(cmd.split(":")[1])
                await self._player.set_volume(vol)
            except (ValueError, IndexError):
                pass
        elif cmd == "shuffle":
            await self._player.toggle_random()
        elif cmd == "next":
            await self._player.next_track()
        elif cmd == "previous":
            await self._player.previous_track()
        elif cmd == "pause":
            await self._player.pause()
        elif cmd == "play":
            await self._player.play()
        else:
            logger.warning("Unknown command: %s", cmd)

    async def _on_card_removed(self, card_id: str | None = None, should_pause: bool = False, **_) -> None:
        # Save resume position directly (not via event bus — avoids race condition)
        if self._current_card_id:
            elapsed = await self._player.get_elapsed()
            if elapsed > 0:
                await self._card_service.update_resume_position(self._current_card_id, elapsed)
        if should_pause:
            await self._player.pause()
        self._current_card_id = None

    async def _dispatch_action(self, action: str) -> None:
        """Shared dispatch logic for gesture and button actions."""
        match action:
            case "next_track":
                await self._player.next_track()
            case "previous_track":
                await self._player.previous_track()
            case "volume_up":
                await self._player.adjust_volume(5)
            case "volume_down":
                await self._player.adjust_volume(-5)
            case "shuffle":
                await self._player.toggle_random()
            case "play_pause":
                await self._player.toggle()

    async def _on_gesture(self, action: str, **_) -> None:
        await self._dispatch_action(action)

    async def _on_button_pressed(self, action: str, **_) -> None:
        await self._dispatch_action(action)

    async def _on_resume_save(self, card_id: str, position: float, **_) -> None:
        await self._card_service.update_resume_position(card_id, position)
