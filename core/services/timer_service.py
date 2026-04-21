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

    # Default fade-out duration in seconds
    DEFAULT_FADE_DURATION = 30

    # Maximum total remaining time allowed when extending the sleep timer.
    # Matches the upper bound of SleepTimerRequest (minutes: le=120).
    MAX_SLEEP_MINUTES = 120

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
        self._fade_task: asyncio.Task | None = None
        self._idle_task: asyncio.Task | None = None
        self._sleep_remaining: float = 0
        self._sleep_active: bool = False
        self._fading: bool = False
        self._pre_fade_volume: int | None = None
        # Last volume value the fade itself set. Used to distinguish fade-driven
        # player_state_changed echoes from real user intervention (turning the
        # volume back up during fade must cancel the timer).
        self._last_fade_target: int | None = None
        self._last_activity: float = time.monotonic()
        self._cached_max_volume: int | None = None
        self._max_volume_loaded: bool = False

    async def start(self) -> None:
        """Subscribe to events and start background tasks."""
        self._event_bus.subscribe("player_state_changed", self._on_player_state)
        self._event_bus.subscribe("card_scanned", self._on_activity)
        self._event_bus.subscribe("gesture_detected", self._on_activity)
        self._event_bus.subscribe("config_changed", self._on_config_changed)
        self._idle_task = asyncio.create_task(self._idle_loop())
        logger.info("Timer service started")

    async def stop(self) -> None:
        if self._sleep_task:
            self._sleep_task.cancel()
        if self._fade_task:
            self._fade_task.cancel()
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
        await self._publish_sleep_state(duration_seconds=int(minutes * 60))

    async def extend_sleep_timer(self, minutes: float) -> float:
        """Add minutes to the running sleep timer.

        Returns the new total remaining seconds.
        Raises RuntimeError if no timer is active or a fade-out is in progress.
        The resulting remaining time is clamped to MAX_SLEEP_MINUTES.
        """
        if not self._sleep_active:
            raise RuntimeError("no_active_timer")
        if self._fading:
            raise RuntimeError("timer_fading")
        if minutes <= 0:
            raise ValueError("minutes must be positive")

        max_seconds = self.MAX_SLEEP_MINUTES * 60
        self._sleep_remaining = min(max_seconds, self._sleep_remaining + minutes * 60)
        logger.info(
            "Sleep timer extended by %.0f min, new remaining: %.0fs",
            minutes, self._sleep_remaining,
        )
        await self._publish_sleep_state()
        return self._sleep_remaining

    async def cancel_sleep_timer(self) -> None:
        """Cancel the active sleep timer and any ongoing fade-out.

        Fade and countdown run as independent tasks (B1 semantics): both
        must be cancelled and awaited so a subsequent start_sleep_timer
        does not race with a half-cancelled fade still touching the volume.
        """
        was_active = self._sleep_active or self._fading
        # Snapshot the pre-fade volume before tearing down the fade task:
        # the task's own CancelledError handler also restores volume, but
        # awaiting that restore before we run our own set_volume below
        # avoids a brief dip if the task happened to be mid-step.
        restore_volume = self._pre_fade_volume if self._fading else None
        if self._fade_task:
            self._fade_task.cancel()
            try:
                await self._fade_task
            except asyncio.CancelledError:
                pass
            self._fade_task = None
        if self._sleep_task:
            self._sleep_task.cancel()
            try:
                await self._sleep_task
            except asyncio.CancelledError:
                pass
            self._sleep_task = None
        # Restore original volume if fade was in progress. The fade task's
        # CancelledError branch already does this, but it only runs if the
        # task had actually started; belt-and-suspenders for robustness.
        if restore_volume is not None:
            await self._player.set_volume(restore_volume)
        self._fading = False
        self._pre_fade_volume = None
        self._sleep_active = False
        self._sleep_remaining = 0
        if was_active:
            await self._publish_sleep_state()

    def sleep_timer_status(self) -> dict:
        return {
            "active": self._sleep_active,
            "remaining_seconds": max(0, self._sleep_remaining),
            "fading": self._fading,
        }

    async def _publish_sleep_state(self, duration_seconds: int | None = None) -> None:
        """Broadcast sleep-timer state so all connected clients stay in sync.

        `duration_seconds` is only meaningful on `start_sleep_timer`; the
        extend/cancel paths leave it `None` — the frontend uses it as a
        one-shot hint for any progress visualization.
        """
        try:
            await self._event_bus.publish(
                "sleep_timer_updated",
                remaining_seconds=max(0, self._sleep_remaining),
                fading=self._fading,
                active=self._sleep_active,
                duration_seconds=duration_seconds,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to publish sleep_timer_updated")

    async def _sleep_countdown(self) -> None:
        """Count down remaining seconds; start fade-out *inside* the window.

        B1 semantics: the fade runs concurrently with the countdown — once
        ``remaining <= fade_duration`` the fade task is spawned and both
        tasks tick together until ``remaining == 0``, at which point the
        fade is already at volume 0 and playback is stopped. The total
        timer duration the user requested is therefore exactly the time
        until silence, not until fade-start.
        """
        try:
            # Resolve fade duration once so countdown and fade agree on it.
            fade_duration = await self._config.get("sleep_fade_duration")
            if fade_duration is None or fade_duration <= 0:
                fade_duration = self.DEFAULT_FADE_DURATION
            # Clamp: a fade longer than the whole timer would never start.
            fade_duration = min(int(fade_duration), int(self._sleep_remaining))

            fade_started = False
            while self._sleep_remaining > 0:
                if not fade_started and self._sleep_remaining <= fade_duration:
                    fade_started = True
                    self._fade_task = asyncio.create_task(
                        self._fade_out(duration=fade_duration),
                    )
                await asyncio.sleep(1)
                self._sleep_remaining -= 1

            # Countdown exhausted. If fade was started, wait for it to finish
            # its final volume steps and stop_playback(); if not (fade_duration
            # was 0 for some reason), stop playback ourselves.
            if self._fade_task is not None:
                try:
                    await self._fade_task
                except asyncio.CancelledError:
                    pass
            else:
                await self._player.stop_playback()
                self._sleep_active = False
                self._sleep_remaining = 0
                await self._publish_sleep_state()
                await self._event_bus.publish("sleep_timer_expired")
        except asyncio.CancelledError:
            pass

    async def _fade_out(self, duration: float | None = None) -> None:
        """Gradually reduce volume to 0, then stop playback and restore volume.

        Under B1 semantics this runs *in parallel* with the tail of the
        countdown task. ``duration`` is the target fade length in seconds
        (normally equal to the time-until-zero that the countdown has left
        when the fade is spawned). When omitted, the config value is used —
        kept for callers that still want the legacy "fade after zero" shape.
        """
        try:
            if duration is None:
                fade_duration = await self._config.get("sleep_fade_duration")
                if fade_duration is None or fade_duration <= 0:
                    fade_duration = self.DEFAULT_FADE_DURATION
            else:
                fade_duration = duration

            start_volume = self._player.state.volume
            if start_volume <= 0:
                # Already silent — don't touch the volume; wait for the
                # countdown to finish, then stop playback ourselves.
                if fade_duration > 0:
                    await asyncio.sleep(fade_duration)
                await self._player.stop_playback()
                self._sleep_active = False
                self._sleep_remaining = 0
                self._fading = False
                await self._publish_sleep_state()
                await self._event_bus.publish("sleep_timer_expired")
                return

            self._pre_fade_volume = start_volume
            self._last_fade_target = start_volume
            self._fading = True
            await self._publish_sleep_state()

            # Calculate step interval: aim for ~1-2 second steps
            step_count = min(start_volume, max(1, int(fade_duration)))
            step_interval = fade_duration / step_count

            logger.info(
                "Fade-out: %d → 0 over %.0fs (%d steps, %.1fs interval)",
                start_volume, fade_duration, step_count, step_interval,
            )

            for i in range(1, step_count + 1):
                await asyncio.sleep(step_interval)

                # Check if fade was cancelled (e.g. by manual volume change)
                if not self._fading:
                    logger.info("Fade-out cancelled")
                    return

                new_volume = max(0, start_volume - int(start_volume * i / step_count))
                self._last_fade_target = new_volume
                await self._player.set_volume(new_volume)

            # Fade complete — stop playback
            await self._player.stop_playback()
            self._sleep_active = False
            self._fading = False
            self._sleep_remaining = 0

            # Restore original volume so next playback isn't silent
            await self._player.set_volume(self._pre_fade_volume)
            self._pre_fade_volume = None
            logger.info("Fade-out complete, volume restored to %d", start_volume)

            await self._publish_sleep_state()
            await self._event_bus.publish("sleep_timer_expired")
        except asyncio.CancelledError:
            # Restore volume on cancellation
            if self._pre_fade_volume is not None:
                await self._player.set_volume(self._pre_fade_volume)
                self._pre_fade_volume = None
            self._fading = False
            self._last_fade_target = None
            # Clear sleep state so the UI does not show a stale "active 0s" pill.
            self._sleep_active = False
            self._sleep_remaining = 0
            await self._publish_sleep_state()

    # --- Volume enforcement ---

    async def _enforce_max_volume(self) -> None:
        """Enforce the maximum volume setting (cached to avoid DB reads on every event)."""
        if not self._max_volume_loaded:
            self._cached_max_volume = await self._config.get("player.max_volume")
            self._max_volume_loaded = True
        if self._cached_max_volume is not None and self._player.state.volume > self._cached_max_volume:
            await self._player.set_volume(self._cached_max_volume)
            logger.debug("Volume capped to max: %d", self._cached_max_volume)

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

        # Detect manual volume change during fade-out → cancel fade and timer.
        # The fade itself calls set_volume which echoes back as player_state_changed.
        # We track the last value the fade *asked for* in `_last_fade_target` and
        # treat any reported value significantly above it as user intervention
        # (tolerance absorbs float/int rounding between MPD and our steps).
        if self._fading and self._last_fade_target is not None:
            reported_volume = state.get("volume")
            if reported_volume is not None and reported_volume > self._last_fade_target + 2:
                logger.info(
                    "Manual volume change during fade (%d), cancelling",
                    reported_volume,
                )
                was_active = self._sleep_active or self._fading
                self._fading = False
                self._pre_fade_volume = None
                self._last_fade_target = None
                if self._fade_task:
                    self._fade_task.cancel()
                    self._fade_task = None
                # Countdown runs independently under B1 — cancel it too
                # so the timer does not keep ticking to 0 in the background.
                if self._sleep_task:
                    self._sleep_task.cancel()
                    self._sleep_task = None
                self._sleep_active = False
                self._sleep_remaining = 0
                if was_active:
                    await self._publish_sleep_state()

    async def _on_config_changed(self, key: str = "", **_) -> None:
        """Invalidate cached config values when config changes."""
        if not key or key == "player.max_volume":
            self._max_volume_loaded = False

    async def _on_activity(self, **_) -> None:
        self._last_activity = time.monotonic()
