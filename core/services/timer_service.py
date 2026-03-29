"""Sleep timer and idle shutdown service.

- Sleep timer: automatically stops playback after N minutes
- Idle shutdown: shuts down the system after N minutes of no playback
- Volume limit: enforces maximum volume from config
- Resume tracking: saves audiobook progress on pause/stop
"""

import asyncio
import logging
import time

from core.services.base import BaseService
from core.services.config_service import ConfigService
from core.services.event_bus import EventBus
from core.services.player_service import PlaybackState, PlayerService

logger = logging.getLogger(__name__)


class TimerService(BaseService):
    """Manages sleep timer, idle shutdown, volume enforcement, and resume tracking."""

    def __init__(
        self,
        event_bus: EventBus,
        player: PlayerService,
        config: ConfigService,
    ) -> None:
        super().__init__()
        self._event_bus = event_bus
        self._player = player
        self._config = config
        self._sleep_task: asyncio.Task | None = None
        self._idle_task: asyncio.Task | None = None
        self._sleep_remaining: float = 0
        self._sleep_active: bool = False
        self._last_activity: float = time.monotonic()

    async def start(self) -> None:
        """Subscribe to events and start background tasks."""
        self._event_bus.subscribe("player_state_changed", self._on_player_state)
        self._event_bus.subscribe("card_scanned", self._on_activity)
        self._event_bus.subscribe("gesture_detected", self._on_activity)
        self._idle_task = asyncio.create_task(self._idle_loop())
        logger.info("Timer service started")

    async def stop(self) -> None:
        if self._sleep_task:
            self._sleep_task.cancel()
        if self._idle_task:
            self._idle_task.cancel()

    # --- Sleep timer ---

    async def start_sleep_timer(self, minutes: float) -> None:
        """Start a sleep timer. Stops playback after N minutes."""
        await self.cancel_sleep_timer()
        self._sleep_remaining = minutes * 60
        self._sleep_active = True
        self._sleep_task = asyncio.create_task(self._sleep_countdown())
        logger.info("Sleep timer started: %.0f minutes", minutes)

    async def cancel_sleep_timer(self) -> None:
        """Cancel the active sleep timer."""
        if self._sleep_task:
            self._sleep_task.cancel()
            try:
                await self._sleep_task
            except asyncio.CancelledError:
                pass
        self._sleep_active = False
        self._sleep_remaining = 0

    def sleep_timer_status(self) -> dict:
        return {
            "active": self._sleep_active,
            "remaining_seconds": max(0, self._sleep_remaining),
        }

    async def _sleep_countdown(self) -> None:
        try:
            while self._sleep_remaining > 0:
                await asyncio.sleep(1)
                self._sleep_remaining -= 1

            # Timer expired — stop playback
            logger.info("Sleep timer expired, stopping playback")
            await self._player.stop_playback()
            self._sleep_active = False

            # Broadcast timer event
            await self._event_bus.publish("sleep_timer_expired")
        except asyncio.CancelledError:
            pass

    # --- Volume enforcement ---

    async def _enforce_max_volume(self) -> None:
        """Enforce the maximum volume setting."""
        max_vol = await self._config.get("player.max_volume")
        if max_vol is not None and self._player.state.volume > max_vol:
            await self._player.set_volume(max_vol)
            logger.debug("Volume capped to max: %d", max_vol)

    # --- Idle shutdown ---

    async def _idle_loop(self) -> None:
        """Check for idle timeout and trigger shutdown."""
        try:
            while True:
                await asyncio.sleep(60)  # Check every minute
                idle_minutes = await self._config.get("system.idle_shutdown_minutes")
                if not idle_minutes or idle_minutes <= 0:
                    continue

                # Only count idle when not playing
                if self._player.state.state == PlaybackState.PLAYING:
                    self._last_activity = time.monotonic()
                    continue

                idle_seconds = time.monotonic() - self._last_activity
                if idle_seconds > idle_minutes * 60:
                    logger.info("Idle shutdown triggered after %d minutes", idle_minutes)
                    await self._event_bus.publish("idle_shutdown")
                    # Actual shutdown is handled by the system layer
                    break
        except asyncio.CancelledError:
            pass

    # --- Resume tracking ---

    async def save_resume_position(self, card_id: str) -> None:
        """Save current playback position for audiobook resume."""
        if not card_id:
            return
        elapsed = await self._player.get_elapsed()
        if elapsed > 0:
            await self._event_bus.publish(
                "resume_position_save",
                card_id=card_id,
                position=elapsed,
            )

    # --- Event handlers ---

    async def _on_player_state(self, state: dict, **_) -> None:
        await self._enforce_max_volume()
        self._last_activity = time.monotonic()

    async def _on_activity(self, **_) -> None:
        self._last_activity = time.monotonic()
