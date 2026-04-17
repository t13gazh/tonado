"""Tests for the captive portal service — password generation + auto-timeout."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.captive_portal import (
    CONFIG_KEY_PASSWORD,
    CONFIG_KEY_TIMEOUT,
    MIN_PASSWORD_LENGTH,
    CaptivePortalService,
)
from core.services.config_service import ConfigService


def _mock_running_proc() -> MagicMock:
    """Create a fake process that looks like it's still running."""
    proc = MagicMock()
    proc.returncode = None
    proc.terminate = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    return proc


def _prep_portal(portal: CaptivePortalService, tmp_path: Path) -> None:
    """Redirect hostapd/dnsmasq config paths into tmp_path so write_text works."""
    portal._hostapd_conf = tmp_path / "hostapd.conf"
    portal._dnsmasq_conf = tmp_path / "dnsmasq.conf"


def _portal_env():
    """Context-manager stack patching subprocess + shutil.which for start()."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(
        patch("core.services.captive_portal.shutil.which", return_value="/usr/bin/mock")
    )
    stack.enter_context(
        patch(
            "core.services.captive_portal.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=lambda *a, **kw: _mock_running_proc()),
        )
    )
    stack.enter_context(
        patch(
            "core.services.captive_portal.async_run",
            new=AsyncMock(return_value=(0, "", "")),
        )
    )
    return stack


@pytest.mark.asyncio
async def test_generates_password_on_first_start(
    config_service: ConfigService, tmp_path: Path
) -> None:
    portal = CaptivePortalService(config_service=config_service)
    _prep_portal(portal, tmp_path)
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
async def test_reuses_existing_password(
    config_service: ConfigService, tmp_path: Path
) -> None:
    await config_service.set(CONFIG_KEY_PASSWORD, "preexisting-password-12345")
    await config_service.set(CONFIG_KEY_TIMEOUT, 60)
    portal = CaptivePortalService(config_service=config_service)
    _prep_portal(portal, tmp_path)
    with _portal_env():
        await portal.start()
        assert portal.ap_password == "preexisting-password-12345"
        # Confirm hostapd.conf contains WPA2 + the password
        content = (tmp_path / "hostapd.conf").read_text()
        assert "wpa=2" in content
        assert "wpa_passphrase=preexisting-password-12345" in content
        await portal.stop()


@pytest.mark.asyncio
async def test_timeout_stops_portal(
    config_service: ConfigService, tmp_path: Path
) -> None:
    portal = CaptivePortalService(config_service=config_service)
    _prep_portal(portal, tmp_path)
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
    _prep_portal(portal, tmp_path)
    with _portal_env():
        await portal.start()
        timeout_task = portal._timeout_task
        assert timeout_task is not None
        await portal.stop()
    assert timeout_task.cancelled() or timeout_task.done()
    assert portal._timeout_task is None


@pytest.mark.asyncio
async def test_status_reports_timeout_and_password_flag(
    config_service: ConfigService, tmp_path: Path
) -> None:
    await config_service.set(CONFIG_KEY_TIMEOUT, 60)
    portal = CaptivePortalService(config_service=config_service)
    _prep_portal(portal, tmp_path)
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
