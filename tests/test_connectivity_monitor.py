"""Tests for the ConnectivityMonitor state machine + auto-fallback behaviour.

The monitor is tick-driven, and the production loop is driven by wall clock
time. To keep tests deterministic we:

* inject a ``FakeClock`` via ``time_source`` so we can jump ahead without
  ``asyncio.sleep`` calls,
* stub ``WifiService.status()`` and ``CaptivePortalService.start/stop`` with
  ``AsyncMock`` / ``MagicMock`` shims so no real ``wlan0`` mutation happens,
* invoke ``_tick()`` directly instead of starting the background task. The
  loop is a thin ``while not stopped: tick(); await wait()`` shell — ticks
  are what matters for behaviour.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.config_service import ConfigService
from core.services.connectivity_monitor import (
    CONFIG_KEY_BOOT_GRACE,
    CONFIG_KEY_ENABLED,
    CONFIG_KEY_POST_RECOVERY,
    CONFIG_KEY_TIMEOUT,
    DEFAULT_BOOT_GRACE_SECONDS,
    DEFAULT_POST_RECOVERY_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    PRE_WARN_SECONDS,
    ConnectivityMonitor,
    MonitorState,
)
from core.services.event_bus import EventBus


class FakeClock:
    """Monotonic-compatible clock whose current value is under test control."""

    def __init__(self, start: float = 1000.0) -> None:
        self._t = start

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


@dataclass
class WifiStatusStub:
    connected: bool = True
    ssid: str = "Home"
    ip_address: str = "192.168.1.42"
    signal: int = 75


def _wifi(connected: bool) -> MagicMock:
    wifi = MagicMock()
    wifi.status = AsyncMock(return_value=WifiStatusStub(connected=connected))
    return wifi


def _portal(active: bool = False, start_ok: bool = True) -> MagicMock:
    portal = MagicMock()
    portal.active = active
    portal.owner = None
    portal.start = AsyncMock(return_value=start_ok)
    portal.stop = AsyncMock()
    return portal


def _make_monitor(
    wifi: Any, portal: Any, clock: FakeClock, config: ConfigService, *, mock: bool = True
) -> ConnectivityMonitor:
    mon = ConnectivityMonitor(
        wifi=wifi,
        portal=portal,
        config=config,
        event_bus=EventBus(),
        time_source=clock,
        mock=mock,
    )
    # Simulate start() without spinning the actual task
    mon._started_at = clock()
    mon._state_since = clock()
    return mon


# ----------------------------------------------------------------------
# Boot-grace transitions
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_boot_grace_transitions_to_monitoring_on_connect(
    config_service: ConfigService,
) -> None:
    clock = FakeClock()
    mon = _make_monitor(_wifi(connected=True), _portal(), clock, config_service)
    assert mon.state == MonitorState.BOOT_GRACE
    await mon._tick()
    assert mon.state == MonitorState.MONITORING


@pytest.mark.asyncio
async def test_boot_grace_expires_to_grace_when_offline(
    config_service: ConfigService,
) -> None:
    clock = FakeClock()
    mon = _make_monitor(_wifi(connected=False), _portal(), clock, config_service)
    # Still inside boot grace → no transition
    clock.advance(DEFAULT_BOOT_GRACE_SECONDS - 1)
    await mon._tick()
    assert mon.state == MonitorState.BOOT_GRACE
    # Boot grace elapsed
    clock.advance(2)
    await mon._tick()
    assert mon.state == MonitorState.GRACE


# ----------------------------------------------------------------------
# Normal run-time state transitions
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monitoring_to_grace_on_disconnect(
    config_service: ConfigService,
) -> None:
    clock = FakeClock()
    wifi = _wifi(connected=True)
    mon = _make_monitor(wifi, _portal(), clock, config_service)
    await mon._tick()  # → MONITORING
    wifi.status.return_value = WifiStatusStub(connected=False)
    await mon._tick()
    assert mon.state == MonitorState.GRACE


@pytest.mark.asyncio
async def test_grace_recovers_when_wifi_returns(
    config_service: ConfigService,
) -> None:
    clock = FakeClock()
    wifi = _wifi(connected=True)
    mon = _make_monitor(wifi, _portal(), clock, config_service)
    await mon._tick()  # → MONITORING
    wifi.status.return_value = WifiStatusStub(connected=False)
    await mon._tick()  # → GRACE
    clock.advance(DEFAULT_TIMEOUT_SECONDS // 2)
    wifi.status.return_value = WifiStatusStub(connected=True)
    await mon._tick()
    assert mon.state == MonitorState.MONITORING


# ----------------------------------------------------------------------
# Trigger + double-check + portal-owner
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_triggers_portal_with_auto_owner(
    config_service: ConfigService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    wifi = _wifi(connected=False)
    portal = _portal()
    mon = _make_monitor(wifi, portal, clock, config_service, mock=False)
    # Pin the timeout explicitly so the test is independent of the DB seed
    # default (which is 300s, not DEFAULT_TIMEOUT_SECONDS=180s).
    await config_service.set(CONFIG_KEY_TIMEOUT, DEFAULT_TIMEOUT_SECONDS)
    # Skip boot grace
    mon._state = MonitorState.GRACE
    mon._state_since = clock()
    clock.advance(DEFAULT_TIMEOUT_SECONDS + 1)

    async def no_sleep(_seconds: float) -> None:
        return None

    # Short-circuit the double-check sleep. monkeypatch restores cleanly.
    import core.services.connectivity_monitor as mod

    monkeypatch.setattr(mod.asyncio, "sleep", no_sleep)
    await mon._tick()

    assert mon.state == MonitorState.FALLBACK_ACTIVE
    portal.start.assert_awaited_once()
    assert portal.start.await_args.kwargs.get("owner") == "auto"


@pytest.mark.asyncio
async def test_double_check_rescues_transient_dropout(
    config_service: ConfigService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    wifi = _wifi(connected=False)
    portal = _portal()
    mon = _make_monitor(wifi, portal, clock, config_service, mock=False)
    await config_service.set(CONFIG_KEY_TIMEOUT, DEFAULT_TIMEOUT_SECONDS)
    mon._state = MonitorState.GRACE
    mon._state_since = clock()
    clock.advance(DEFAULT_TIMEOUT_SECONDS + 1)

    # Flip to connected *after* the 2s double-check sleep — the tick must
    # notice and bail.
    calls = {"n": 0}

    async def status_side_effect() -> WifiStatusStub:
        calls["n"] += 1
        # First read (grace-gate) reports offline; second read (double-check)
        # is connected → fallback aborts.
        return WifiStatusStub(connected=calls["n"] >= 2)

    wifi.status.side_effect = status_side_effect

    async def no_sleep(_seconds: float) -> None:
        return None

    import core.services.connectivity_monitor as mod

    monkeypatch.setattr(mod.asyncio, "sleep", no_sleep)
    await mon._tick()

    portal.start.assert_not_called()
    assert mon.state == MonitorState.MONITORING


# ----------------------------------------------------------------------
# Circuit breaker
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_two_auto_starts(
    config_service: ConfigService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    wifi = _wifi(connected=False)
    portal = _portal()
    mon = _make_monitor(wifi, portal, clock, config_service, mock=False)
    await config_service.set(CONFIG_KEY_TIMEOUT, DEFAULT_TIMEOUT_SECONDS)

    async def no_sleep(_seconds: float) -> None:
        return None

    import core.services.connectivity_monitor as mod

    monkeypatch.setattr(mod.asyncio, "sleep", no_sleep)

    for i in range(3):
        mon._state = MonitorState.GRACE
        mon._state_since = clock()
        clock.advance(DEFAULT_TIMEOUT_SECONDS + 1)
        await mon._tick()
        # Pretend portal went down again so next grace is reachable
        portal.active = False

    # After 2 starts the 3rd attempt must leave the breaker open.
    assert portal.start.await_count == 2
    assert mon.state == MonitorState.CIRCUIT_OPEN


# ----------------------------------------------------------------------
# Cooldown + disabled config
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_portal_stopped_enters_cooldown(
    config_service: ConfigService,
) -> None:
    clock = FakeClock()
    portal = _portal(active=True)
    mon = _make_monitor(_wifi(connected=True), portal, clock, config_service)
    mon._state = MonitorState.FALLBACK_ACTIVE
    mon._state_since = clock()
    portal.active = False  # user stopped the portal
    await mon._tick()
    assert mon.state == MonitorState.COOLDOWN


@pytest.mark.asyncio
async def test_cooldown_holds_until_post_recovery_window(
    config_service: ConfigService,
) -> None:
    clock = FakeClock()
    mon = _make_monitor(_wifi(connected=True), _portal(), clock, config_service)
    mon._state = MonitorState.COOLDOWN
    mon._state_since = clock()
    # Still inside cooldown
    clock.advance(DEFAULT_POST_RECOVERY_SECONDS - 1)
    await mon._tick()
    assert mon.state == MonitorState.COOLDOWN
    # Window elapsed + connected → recovered
    clock.advance(5)
    await mon._tick()
    assert mon.state == MonitorState.MONITORING


@pytest.mark.asyncio
async def test_disabled_config_resets_to_monitoring(
    config_service: ConfigService,
) -> None:
    clock = FakeClock()
    wifi = _wifi(connected=False)
    mon = _make_monitor(wifi, _portal(), clock, config_service)
    mon._state = MonitorState.GRACE
    mon._state_since = clock()
    await config_service.set(CONFIG_KEY_ENABLED, False)
    await mon._tick()
    assert mon.state == MonitorState.MONITORING


# ----------------------------------------------------------------------
# Portal owner semantics
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_stops_only_auto_portal(
    config_service: ConfigService,
) -> None:
    clock = FakeClock()
    mon = _make_monitor(_wifi(connected=True), _portal(active=True), clock, config_service)
    mon._portal.owner = "manual"
    await mon.stop()
    mon._portal.stop.assert_not_called()

    # Second monitor owns the portal — stop should cascade.
    mon2 = _make_monitor(_wifi(connected=True), _portal(active=True), clock, config_service)
    mon2._portal.owner = "auto"
    await mon2.stop()
    mon2._portal.stop.assert_awaited_once()
