"""Tests for the captive portal service.

Since v0.4 the service no longer drives hostapd/dnsmasq itself — it delegates
every wlan0 operation to `setup-ap.sh` via sudo. These tests patch
`async_run` to record the delegated commands and assert on those, plus the
password generation / auto-timeout / owner state machine that still lives here.
"""

import asyncio
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.services.captive_portal import (
    CONFIG_KEY_PASSWORD,
    CONFIG_KEY_SSID,
    CONFIG_KEY_TIMEOUT,
    MIN_PASSWORD_LENGTH,
    SETUP_AP_SCRIPT,
    CaptivePortalService,
)
from core.services.config_service import ConfigService


@contextmanager
def _portal_env():
    """Patch shutil.which (prereq check) + async_run (sudo delegation).

    Yields the list of argv lists passed to async_run so tests can assert
    on the setup-ap.sh delegation.
    """
    calls: list[list[str]] = []

    async def fake_async_run(cmd, **kwargs):
        calls.append(list(cmd))
        return (0, "", "")

    with patch(
        "core.services.captive_portal.shutil.which", return_value="/usr/bin/mock"
    ), patch("core.services.captive_portal.async_run", new=fake_async_run):
        yield calls


@pytest.mark.asyncio
async def test_generates_password_on_first_start(
    config_service: ConfigService, tmp_path: Path
) -> None:
    portal = CaptivePortalService(config_service=config_service)
    # Long timeout so auto-timeout doesn't race the assertions.
    await config_service.set(CONFIG_KEY_TIMEOUT, 60)
    with _portal_env():
        started = await portal.start()
        assert started is True
        stored = await config_service.get(CONFIG_KEY_PASSWORD)
        assert isinstance(stored, str)
        assert len(stored) >= MIN_PASSWORD_LENGTH
        assert portal.ap_password == stored
        await portal.stop()


@pytest.mark.asyncio
async def test_start_delegates_secured_ap_to_setup_ap_script(
    config_service: ConfigService, tmp_path: Path
) -> None:
    await config_service.set(CONFIG_KEY_PASSWORD, "preexisting-password-12345")
    await config_service.set(CONFIG_KEY_SSID, "Tonado-Recovery")
    await config_service.set(CONFIG_KEY_TIMEOUT, 60)
    portal = CaptivePortalService(config_service=config_service)
    with _portal_env() as calls:
        await portal.start()
        assert portal.ap_password == "preexisting-password-12345"
        # The recovery AP must be brought up as WPA2 (secured) with the
        # configured SSID + password, delegated via sudo to setup-ap.sh.
        start_calls = [
            c for c in calls if SETUP_AP_SCRIPT in c and "start" in c
        ]
        assert start_calls, "start must delegate to setup-ap.sh"
        argv = start_calls[0]
        assert argv[:2] == ["sudo", "-n"]
        assert "secured" in argv
        assert "Tonado-Recovery" in argv
        assert "preexisting-password-12345" in argv
        await portal.stop()
        # stop must also delegate
        assert any(SETUP_AP_SCRIPT in c and "stop" in c for c in calls)


@pytest.mark.asyncio
async def test_start_fails_when_script_fails(
    config_service: ConfigService, tmp_path: Path
) -> None:
    await config_service.set(CONFIG_KEY_TIMEOUT, 60)
    portal = CaptivePortalService(config_service=config_service)

    async def failing_run(cmd, **kwargs):
        # `stop` (cleanup) succeeds, `start` fails.
        return (0 if "stop" in cmd else 5, "", "boom")

    with patch(
        "core.services.captive_portal.shutil.which", return_value="/usr/bin/mock"
    ), patch("core.services.captive_portal.async_run", new=failing_run):
        started = await portal.start()
    assert started is False
    assert portal.active is False


@pytest.mark.asyncio
async def test_start_returns_false_without_binaries(
    config_service: ConfigService,
) -> None:
    portal = CaptivePortalService(config_service=config_service)
    with patch("core.services.captive_portal.shutil.which", return_value=None):
        started = await portal.start()
    assert started is False
    assert portal.active is False


@pytest.mark.asyncio
async def test_timeout_stops_portal(
    config_service: ConfigService, tmp_path: Path
) -> None:
    portal = CaptivePortalService(config_service=config_service)
    # Patch the loader to bypass the min-60s clamp on the Config path.
    with patch.object(portal, "_load_timeout_seconds", new=AsyncMock(return_value=0)):
        with _portal_env():
            await portal.start()
            # _auto_timeout sleeps 0s, then calls stop()
            for _ in range(20):
                if not portal.active:
                    break
                await asyncio.sleep(0.02)
    assert portal.active is False


@pytest.mark.asyncio
async def test_stop_cancels_timeout(
    config_service: ConfigService, tmp_path: Path
) -> None:
    await config_service.set(CONFIG_KEY_TIMEOUT, 60)
    portal = CaptivePortalService(config_service=config_service)
    with _portal_env():
        await portal.start()
        timeout_task = portal._timeout_task
        assert timeout_task is not None
        await portal.stop()
    assert timeout_task.cancelled() or timeout_task.done()
    assert portal._timeout_task is None


@pytest.mark.asyncio
async def test_owner_defaults_to_manual_and_resets_on_stop(
    config_service: ConfigService, tmp_path: Path
) -> None:
    await config_service.set(CONFIG_KEY_TIMEOUT, 60)
    portal = CaptivePortalService(config_service=config_service)
    with _portal_env():
        assert portal.owner is None
        await portal.start()
        assert portal.owner == "manual"
        assert portal.status()["owner"] == "manual"
        await portal.stop()
    assert portal.owner is None
    assert portal.status()["owner"] is None


@pytest.mark.asyncio
async def test_owner_records_auto_and_setup(
    config_service: ConfigService, tmp_path: Path
) -> None:
    await config_service.set(CONFIG_KEY_TIMEOUT, 60)
    portal = CaptivePortalService(config_service=config_service)
    with _portal_env():
        await portal.start(owner="auto")
        assert portal.owner == "auto"
        await portal.stop()

        await portal.start(owner="setup")
        assert portal.owner == "setup"
        await portal.stop()


@pytest.mark.asyncio
async def test_offline_owner_has_no_auto_timeout(
    config_service: ConfigService, tmp_path: Path
) -> None:
    """owner='offline' must run permanently — no auto-timeout task, and the
    status reports no countdown. Otherwise an offline box would silently drop
    its only AP after the timeout and lock the parents out."""
    # Even a 0s timeout config must not tear an offline AP down.
    portal = CaptivePortalService(config_service=config_service)
    with patch.object(portal, "_load_timeout_seconds", new=AsyncMock(return_value=0)):
        with _portal_env():
            await portal.start(owner="offline")
            assert portal.owner == "offline"
            # No timeout task scheduled at all.
            assert portal._timeout_task is None
            # Give a normal-mode timeout a chance to fire (it must not).
            await asyncio.sleep(0.05)
            assert portal.active is True
            status = portal.status()
            assert status["seconds_until_timeout"] is None
            await portal.stop()
    assert portal.owner is None


@pytest.mark.asyncio
async def test_status_reports_timeout_and_password_flag(
    config_service: ConfigService, tmp_path: Path
) -> None:
    await config_service.set(CONFIG_KEY_TIMEOUT, 60)
    portal = CaptivePortalService(config_service=config_service)
    with _portal_env():
        await portal.start()
        status = portal.status()
        assert status["active"] is True
        assert status["password_available"] is True
        assert status["seconds_until_timeout"] is not None
        assert status["seconds_until_timeout"] >= 0
        # Password itself must not leak into status payload
        assert "password" not in status
        await portal.stop()
    status = portal.status()
    assert status["active"] is False
    assert status["seconds_until_timeout"] is None
