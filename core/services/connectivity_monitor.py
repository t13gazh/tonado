"""Background monitor that starts the captive portal AP when WiFi stays down.

Use case: the box is taken somewhere its known WiFi is unreachable (grandma's
place, in the car). Music keeps playing from the local library, but the phone
app would be unreachable. The monitor watches `WifiService.status()` and, after
a grace period, spins up the `CaptivePortalService` so the phone can
reconnect and configure a new WiFi.

State machine:
    MONITORING      → WiFi up, all good. Poll every _poll_interval.
    BOOT_GRACE      → Initial post-start window. Never triggers fallback so
                      NetworkManager has time to associate.
    GRACE           → WiFi just dropped. Wait `fallback_timeout_seconds`
                      before pulling the trigger. Reset to MONITORING if
                      WiFi comes back within this window.
    FALLBACK_ACTIVE → Portal was started (or already running under an
                      owner we don't control). Monitor pauses; user drives
                      recovery via UI.
    COOLDOWN        → Portal stopped (recovery succeeded or manual stop).
                      Ignore WiFi drops for `post_recovery_grace_seconds`
                      to avoid ping-pong when the user's new password is
                      wrong and `nmcli connect` gives a false-positive.
    CIRCUIT_OPEN    → Too many auto-starts in the last hour. Stay silent
                      until a clean connected-interval resets the counter.

The monitor never stops a portal whose `owner != "auto"` — the setup wizard
and expert-tier manual starts own their portals and are the only ones who may
stop them.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from enum import Enum
from typing import Any

from core.services.base import BaseService
from core.services.captive_portal import CaptivePortalService
from core.services.config_service import ConfigService
from core.services.event_bus import EventBus
from core.services.wifi_service import WifiService

logger = logging.getLogger(__name__)


CONFIG_KEY_ENABLED = "wifi.auto_fallback_enabled"
CONFIG_KEY_TIMEOUT = "wifi.fallback_timeout_seconds"
CONFIG_KEY_BOOT_GRACE = "wifi.boot_grace_seconds"
CONFIG_KEY_POST_RECOVERY = "wifi.post_recovery_grace_seconds"

DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_BOOT_GRACE_SECONDS = 60
DEFAULT_POST_RECOVERY_SECONDS = 300
PRE_WARN_SECONDS = 10
POLL_INTERVAL_SECONDS = 15
DOUBLE_CHECK_DELAY_SECONDS = 2

# Circuit breaker: if the monitor auto-started the portal this often inside
# this window, stop trying until a clean connected interval is seen.
CIRCUIT_MAX_STARTS = 2
CIRCUIT_WINDOW_SECONDS = 3600


class MonitorState(str, Enum):
    MONITORING = "monitoring"
    BOOT_GRACE = "boot_grace"
    GRACE = "grace"
    FALLBACK_ACTIVE = "fallback_active"
    COOLDOWN = "cooldown"
    CIRCUIT_OPEN = "circuit_open"


class ConnectivityMonitor(BaseService):
    """Watches WiFi connectivity and triggers the captive portal on sustained
    outages. See module docstring for the state machine."""

    def __init__(
        self,
        wifi: WifiService,
        portal: CaptivePortalService,
        config: ConfigService,
        event_bus: EventBus,
        *,
        poll_interval: float = POLL_INTERVAL_SECONDS,
        time_source: Any = time.monotonic,
        mock: bool = False,
    ) -> None:
        super().__init__()
        self._wifi = wifi
        self._portal = portal
        self._config = config
        self._event_bus = event_bus
        self._poll_interval = poll_interval
        self._now = time_source
        self._mock = mock

        # State
        self._state: MonitorState = MonitorState.BOOT_GRACE
        self._state_since: float = 0.0
        self._started_at: float = 0.0
        self._pre_warn_sent: bool = False

        # Circuit breaker
        self._recent_auto_starts: deque[float] = deque()

        # Exclusive wlan0 access — taken around portal.start() so a manual
        # /portal/start can't race us between the double-check and the
        # hostapd spin-up. External callers don't need this yet; keep it
        # internal until that wiring exists.
        self._lock = asyncio.Lock()

        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._pending_emits: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------
    # BaseService lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._started_at = self._now()
        self._state = MonitorState.BOOT_GRACE
        self._state_since = self._started_at
        self._pre_warn_sent = False
        self._stopped.clear()
        self._task = asyncio.create_task(self._run(), name="connectivity-monitor")
        logger.info(
            "ConnectivityMonitor started (mock=%s, poll=%ss)",
            self._mock,
            self._poll_interval,
        )

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

        # If we own the portal, bring it down so `systemctl stop tonado`
        # doesn't leave a dangling AP. Manual/setup portals are left alone.
        if self._portal.active and self._portal.owner == "auto":
            try:
                await self._portal.stop()
            except Exception:
                logger.exception("Failed to stop auto-portal during shutdown")

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "state": self._state.value,
            "state_for_seconds": int(self._now() - self._state_since),
            "auto_starts_in_window": len(self._recent_auto_starts),
        }

    # ------------------------------------------------------------------
    # Public inspection / control
    # ------------------------------------------------------------------

    @property
    def state(self) -> MonitorState:
        return self._state

    @property
    def is_running(self) -> bool:
        if self._task is None or self._task.done():
            # If the task died with an unhandled exception, surface it in
            # the log once — otherwise the setup-complete endpoint would
            # silently re-start it and the original traceback would be lost.
            if self._task is not None and self._task.done():
                try:
                    exc = self._task.exception()
                except (asyncio.InvalidStateError, asyncio.CancelledError):
                    exc = None
                if exc is not None:
                    logger.error(
                        "ConnectivityMonitor task died: %s", exc, exc_info=exc
                    )
            return False
        return True

    def status(self) -> dict[str, Any]:
        return {
            "state": self._state.value,
            "state_for_seconds": int(self._now() - self._state_since),
            "enabled": True,  # Resolved lazily inside the loop
            "auto_starts_in_window": len(self._recent_auto_starts),
        }

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        try:
            while not self._stopped.is_set():
                try:
                    await self._tick()
                except Exception:
                    logger.exception("ConnectivityMonitor tick failed")
                try:
                    await asyncio.wait_for(
                        self._stopped.wait(), timeout=self._poll_interval
                    )
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            raise

    async def _tick(self) -> None:
        enabled = await self._is_enabled()
        connected = await self._is_connected()

        # Disabled → reset state machine to MONITORING and leave portal alone.
        # Don't auto-stop: if a portal is active, user may be mid-recovery.
        if not enabled:
            if self._state not in (MonitorState.MONITORING, MonitorState.BOOT_GRACE):
                self._transition(MonitorState.MONITORING, reason="disabled")
            return

        if self._state == MonitorState.BOOT_GRACE:
            boot_grace = await self._load_int(
                CONFIG_KEY_BOOT_GRACE, DEFAULT_BOOT_GRACE_SECONDS
            )
            if connected:
                self._transition(MonitorState.MONITORING, reason="boot-connected")
            elif self._now() - self._started_at >= boot_grace:
                # Still not connected after boot grace — treat as drop
                self._transition(MonitorState.GRACE, reason="boot-grace-expired")
            return

        if self._state == MonitorState.MONITORING:
            if not connected:
                self._transition(MonitorState.GRACE, reason="wifi-lost")
            else:
                # Reset circuit-breaker history once we've been connected
                # for the full window.
                self._prune_circuit_history()
            return

        if self._state == MonitorState.GRACE:
            if connected:
                self._transition(MonitorState.MONITORING, reason="wifi-recovered")
                return
            timeout = await self._load_int(
                CONFIG_KEY_TIMEOUT, DEFAULT_TIMEOUT_SECONDS
            )
            elapsed = self._now() - self._state_since

            # Pre-warn 10s before triggering so the UI can tell the user
            # "about to cut the WiFi" instead of silently dropping the
            # WebSocket.
            if (
                not self._pre_warn_sent
                and elapsed >= max(0, timeout - PRE_WARN_SECONDS)
            ):
                self._pre_warn_sent = True
                await self._emit(
                    "connectivity.fallback_imminent",
                    seconds_until_fallback=PRE_WARN_SECONDS,
                )

            if elapsed >= timeout:
                await self._trigger_fallback()
            return

        if self._state == MonitorState.FALLBACK_ACTIVE:
            # Portal should be up. If the user / a timeout stopped it,
            # drop into COOLDOWN and resume watching.
            if not self._portal.active:
                self._transition(MonitorState.COOLDOWN, reason="portal-stopped")
            return

        if self._state == MonitorState.COOLDOWN:
            post_recovery = await self._load_int(
                CONFIG_KEY_POST_RECOVERY, DEFAULT_POST_RECOVERY_SECONDS
            )
            if connected and self._now() - self._state_since >= post_recovery:
                self._transition(MonitorState.MONITORING, reason="cooldown-done")
                await self._emit("connectivity.recovered")
            # If still disconnected during cooldown, we just wait — no
            # immediate re-trigger. That's the ping-pong guard.
            return

        if self._state == MonitorState.CIRCUIT_OPEN:
            if connected:
                # A stable connected interval resets the breaker.
                self._recent_auto_starts.clear()
                self._transition(MonitorState.MONITORING, reason="circuit-reset")

    # ------------------------------------------------------------------
    # Fallback trigger (with double-check + circuit breaker)
    # ------------------------------------------------------------------

    async def _trigger_fallback(self) -> None:
        # Double-check: one 2s-later poll must still be disconnected.
        # Transient poll glitches shouldn't rip the WiFi away.
        await asyncio.sleep(DOUBLE_CHECK_DELAY_SECONDS)
        if await self._is_connected():
            self._transition(MonitorState.MONITORING, reason="double-check-ok")
            return

        if not self._circuit_allows_start():
            self._transition(MonitorState.CIRCUIT_OPEN, reason="circuit-breaker")
            await self._emit("connectivity.circuit_open")
            return

        async with self._lock:
            # Re-check inside the lock: a manual portal start or
            # `/api/wifi/connect` may have won the race.
            if self._portal.active:
                logger.info(
                    "Portal already active (owner=%s) — not starting auto-fallback",
                    self._portal.owner,
                )
                self._transition(MonitorState.FALLBACK_ACTIVE, reason="portal-pre-active")
                return

            if self._mock:
                # Keep the state machine moving for tests, skip the
                # actual AP spin-up.
                logger.info("Mock mode: skipping real portal start")
                self._recent_auto_starts.append(self._now())
                self._transition(MonitorState.FALLBACK_ACTIVE, reason="mock-fallback")
                await self._emit("connectivity.fallback_active", owner="auto", mock=True)
                return

            success = await self._portal.start(owner="auto")
            if success:
                self._recent_auto_starts.append(self._now())
                self._transition(
                    MonitorState.FALLBACK_ACTIVE, reason="portal-started"
                )
                await self._emit("connectivity.fallback_active", owner="auto")
            else:
                # hostapd/dnsmasq missing → back off for a full window
                # rather than hammering every poll.
                logger.warning(
                    "Captive portal start failed — opening circuit breaker"
                )
                self._transition(MonitorState.CIRCUIT_OPEN, reason="portal-start-failed")
                await self._emit("connectivity.circuit_open", reason="portal_unavailable")

    def _circuit_allows_start(self) -> bool:
        self._prune_circuit_history()
        return len(self._recent_auto_starts) < CIRCUIT_MAX_STARTS

    def _prune_circuit_history(self) -> None:
        cutoff = self._now() - CIRCUIT_WINDOW_SECONDS
        while self._recent_auto_starts and self._recent_auto_starts[0] < cutoff:
            self._recent_auto_starts.popleft()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _transition(self, new: MonitorState, *, reason: str) -> None:
        if new == self._state:
            return
        old = self._state
        self._state = new
        self._state_since = self._now()
        if new != MonitorState.GRACE:
            self._pre_warn_sent = False
        logger.info(
            "ConnectivityMonitor: %s → %s (%s)", old.value, new.value, reason
        )
        # Fire bus event for grace so the UI can show "connection check…".
        # We're in a sync method but the loop might already be tearing down —
        # create_task can raise RuntimeError("no running event loop"). Guard
        # it and keep a reference so the task isn't GC'd before it runs.
        if new == MonitorState.GRACE:
            try:
                task = asyncio.create_task(self._emit("connectivity.grace_started"))
            except RuntimeError:
                return
            self._pending_emits.add(task)
            task.add_done_callback(self._pending_emits.discard)

    async def _is_connected(self) -> bool:
        try:
            status = await self._wifi.status()
        except Exception:
            logger.exception("WifiService.status() failed")
            return True  # Treat unknown as connected — safer than false-positive fallback
        return bool(status.connected)

    async def _is_enabled(self) -> bool:
        value = await self._config.get(CONFIG_KEY_ENABLED)
        if value is None:
            return True  # Default on
        if isinstance(value, bool):
            return value
        return bool(value)

    async def _load_int(self, key: str, default: int) -> int:
        value = await self._config.get(key)
        if value is None:
            return default
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return default

    async def _emit(self, event: str, **data: Any) -> None:
        try:
            await self._event_bus.publish(event, **data)
        except Exception:
            logger.exception("Failed to publish %s", event)
