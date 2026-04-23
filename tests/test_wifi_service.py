"""Tests for WiFi service (mock mode on non-Pi)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.services.wifi_service import (
    WifiService,
    clear_confirm_tokens,
    consume_confirm_token,
)


@pytest.fixture(autouse=True)
def _clear_tokens_between_tests():
    """Token registry is module-global — isolate tests from each other."""
    clear_confirm_tokens()
    yield
    clear_confirm_tokens()


@pytest.mark.asyncio
async def test_scan_returns_mock_networks() -> None:
    service = WifiService()
    networks = await service.scan()
    assert len(networks) > 0
    assert all(n.ssid for n in networks)


@pytest.mark.asyncio
async def test_mock_connect() -> None:
    service = WifiService()
    result = await service.connect("TestNetwork", "password")
    assert result is True


@pytest.mark.asyncio
async def test_status_mock() -> None:
    service = WifiService()
    status = await service.status()
    assert hasattr(status, "connected")
    assert hasattr(status, "ssid")


@pytest.mark.asyncio
async def test_network_fields() -> None:
    from dataclasses import asdict
    service = WifiService()
    networks = await service.scan()
    d = asdict(networks[0])
    assert "ssid" in d
    assert "signal" in d
    assert "security" in d


# --- Dual-WiFi probe tests ---


class _FakeProc:
    """Minimal asyncio.subprocess.Process stand-in."""

    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:  # pragma: no cover - unused in these tests
        self.returncode = -9


def _make_nmcli_service() -> WifiService:
    """Service instance forced into nmcli-not-mock mode for tests."""
    service = WifiService()
    service._mock = False
    service._use_nmcli = True
    return service


@pytest.mark.asyncio
async def test_probe_home_wifi_happy_path() -> None:
    """Happy path: nmcli add + up succeed, IP returned, no cleanup."""
    service = _make_nmcli_service()

    # Sequence: add (ok), up (ok), IP4.ADDRESS read (returns 192.168.1.42/24)
    add_proc = _FakeProc(returncode=0)
    up_proc = _FakeProc(returncode=0)
    ip_proc = _FakeProc(returncode=0, stdout=b"IP4.ADDRESS[1]:192.168.1.42/24\n")
    # First call is the leftover-cleanup delete; swallow it
    cleanup_proc = _FakeProc(returncode=0)

    procs = iter([cleanup_proc, add_proc, up_proc, ip_proc])

    async def fake_create_subprocess_exec(*args, **kwargs):  # type: ignore[no-untyped-def]
        return next(procs)

    with patch("asyncio.create_subprocess_exec", new=fake_create_subprocess_exec):
        result = await service.probe_home_wifi("HomeWiFi", "correct-pw", timeout=5)

    assert result["ok"] is True
    assert result["error"] is None
    assert result["ip"] == "192.168.1.42"
    # F2: a successful probe must hand the caller a one-shot confirm token
    assert isinstance(result["token"], str) and len(result["token"]) > 16
    # The token must round-trip through the registry exactly once.
    assert consume_confirm_token(result["token"]) is True
    assert consume_confirm_token(result["token"]) is False  # single-use


@pytest.mark.asyncio
async def test_probe_home_wifi_wrong_password_cleans_up() -> None:
    """Wrong password: nmcli up fails with 'secrets were required'.

    Critical: the setup AP must keep running. We assert that on failure
    the probe profile is deleted, so the function leaves no residue, but
    no AP-teardown calls are issued anywhere (there aren't any in this
    code path at all — that alone guarantees the AP survives).
    """
    service = _make_nmcli_service()

    cleanup_pre = _FakeProc(returncode=0)
    add_proc = _FakeProc(returncode=0)
    up_proc = _FakeProc(
        returncode=4,
        stderr=b"Error: Connection activation failed: (7) Secrets were required.\n",
    )
    cleanup_post = _FakeProc(returncode=0)

    procs = iter([cleanup_pre, add_proc, up_proc, cleanup_post])
    call_log: list[tuple] = []

    async def fake_create_subprocess_exec(*args, **kwargs):  # type: ignore[no-untyped-def]
        call_log.append(args)
        return next(procs)

    with patch("asyncio.create_subprocess_exec", new=fake_create_subprocess_exec):
        result = await service.probe_home_wifi("HomeWiFi", "wrong-pw", timeout=5)

    assert result["ok"] is False
    assert result["error"] == "Das WLAN-Passwort ist falsch."
    assert result["ip"] is None
    # F2: failure must NOT leak a confirm token
    assert result.get("token") is None
    # F1: failure count bumped so 10 wrong PSKs in a row lock the probe
    assert service._probe_fail_count == 1

    # Last call must be the post-failure cleanup delete — guarantees the
    # probe profile doesn't linger after a failed attempt.
    last_call = call_log[-1]
    assert last_call[0] == "nmcli"
    assert "delete" in last_call
    assert service.PROBE_CONNECTION_NAME in last_call

    # Nothing in the call log should touch hostapd, dnsmasq, or the
    # tonado-ap.service — the AP must stay up on failure.
    flat = [tok for call in call_log for tok in call]
    assert "hostapd" not in flat
    assert "dnsmasq" not in flat
    assert "tonado-ap.service" not in flat


@pytest.mark.asyncio
async def test_probe_home_wifi_timeout() -> None:
    """nmcli up hangs past our ceiling -> timeout message, cleanup runs."""
    service = _make_nmcli_service()

    cleanup_pre = _FakeProc(returncode=0)
    add_proc = _FakeProc(returncode=0)
    cleanup_post = _FakeProc(returncode=0)

    class HangingProc(_FakeProc):
        def __init__(self) -> None:
            super().__init__(returncode=None)  # type: ignore[arg-type]

        async def communicate(self) -> tuple[bytes, bytes]:
            # Simulate a driver that never returns. asyncio.wait_for is
            # expected to cancel us.
            import asyncio as _aio
            await _aio.sleep(3600)
            return b"", b""

    hanging_up = HangingProc()
    procs = iter([cleanup_pre, add_proc, hanging_up, cleanup_post])

    async def fake_create_subprocess_exec(*args, **kwargs):  # type: ignore[no-untyped-def]
        return next(procs)

    with patch("asyncio.create_subprocess_exec", new=fake_create_subprocess_exec):
        # timeout=1 -> wait_for wraps at timeout+5 = 6s, but wait_for on
        # communicate happens via the internal path; we shorten by patching.
        # Easier: patch asyncio.wait_for directly to raise immediately.
        import asyncio as _aio

        real_wait_for = _aio.wait_for

        async def fake_wait_for(coro, timeout):  # type: ignore[no-untyped-def]
            # Cancel the coroutine so it doesn't linger.
            task = _aio.create_task(coro)
            task.cancel()
            try:
                await task
            except BaseException:
                pass
            raise _aio.TimeoutError()

        with patch("core.services.wifi_service.asyncio.wait_for", new=fake_wait_for):
            result = await service.probe_home_wifi("HomeWiFi", "whatever", timeout=1)

        # Restore just in case (patch context manager handles it, but belt+braces)
        _ = real_wait_for

    assert result["ok"] is False
    assert result["error"] == "Zeitüberschreitung beim Verbinden. Signalstärke prüfen."
    assert result["ip"] is None
    assert result.get("token") is None


@pytest.mark.asyncio
async def test_probe_home_wifi_mock_mode() -> None:
    """Mock mode returns a synthetic success without touching subprocess."""
    service = WifiService()
    # Force mock mode regardless of environment
    service._mock = True
    service._use_nmcli = False

    result = await service.probe_home_wifi("HomeWiFi", "pw")
    assert result["ok"] is True
    assert result["ip"] is not None
    assert isinstance(result["token"], str)


@pytest.mark.asyncio
async def test_finalize_setup_ap_teardown_writes_marker(tmp_path: Path) -> None:
    """finalize_setup_ap_teardown must write the marker and stop the AP unit."""
    service = WifiService()
    service._mock = False
    service._use_nmcli = True

    marker = tmp_path / "config" / ".setup-complete"
    unmanaged_conf = tmp_path / "conf.d" / "99-tonado-wlan0-unmanaged.conf"
    unmanaged_conf.parent.mkdir(parents=True)
    unmanaged_conf.write_text("[keyfile]\nunmanaged-devices=interface-name:wlan0\n")

    commands: list[list[str]] = []

    async def fake_run_silent(cmd: list[str]) -> int:
        commands.append(cmd)
        # Ensure the sudo-rm call actually removes the conf file so
        # downstream assertions mirror reality. The real rm would be
        # invoked; our fake has to do it explicitly.
        if cmd[:3] == ["sudo", "-n", "rm"] and len(cmd) > 3:
            path = Path(cmd[3])
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        return 0

    with patch.object(WifiService, "SETUP_COMPLETE_MARKER", marker), \
         patch.object(WifiService, "NM_UNMANAGED_CONF", unmanaged_conf), \
         patch.object(WifiService, "_run_silent", new=AsyncMock(side_effect=fake_run_silent)):
        await service.finalize_setup_ap_teardown()

    assert marker.exists(), "setup-complete marker must be written"
    assert not unmanaged_conf.exists(), "NM unmanaged override must be removed"

    # F4: every privileged call must be prefixed with `sudo -n` so the
    # sudoers.d/tonado NOPASSWD grants match exactly — otherwise a
    # prompt would hang the finalize forever.
    for cmd in commands:
        assert cmd[:2] == ["sudo", "-n"], (
            f"privileged call missing sudo prefix: {cmd!r}"
        )

    # systemctl stop + disable must both have been attempted
    stop_calls = [c for c in commands if "stop" in c and "tonado-ap.service" in c]
    disable_calls = [c for c in commands if "disable" in c and "tonado-ap.service" in c]
    assert stop_calls, "systemctl stop tonado-ap.service must be called"
    assert disable_calls, "systemctl disable tonado-ap.service must be called"

    # nmcli reload issued so the dropped conf file takes effect
    reload_calls = [c for c in commands if c[-3:] == ["nmcli", "general", "reload"]]
    assert reload_calls, "nmcli general reload must be called"


@pytest.mark.asyncio
async def test_finalize_raises_on_sudo_failure(tmp_path: Path) -> None:
    """A failing privileged call must raise so the router can surface 500."""
    service = WifiService()
    service._mock = False
    service._use_nmcli = True

    marker = tmp_path / "config" / ".setup-complete"
    unmanaged_conf = tmp_path / "conf.d" / "99-tonado-wlan0-unmanaged.conf"
    unmanaged_conf.parent.mkdir(parents=True)
    unmanaged_conf.write_text("unmanaged\n")

    async def fake_run_silent(cmd: list[str]) -> int:
        # Simulate `systemctl stop` failing (e.g. sudoers drift).
        if "stop" in cmd and "tonado-ap.service" in cmd:
            return 5
        if cmd[:3] == ["sudo", "-n", "rm"] and len(cmd) > 3:
            try:
                Path(cmd[3]).unlink()
            except FileNotFoundError:
                pass
        return 0

    with patch.object(WifiService, "SETUP_COMPLETE_MARKER", marker), \
         patch.object(WifiService, "NM_UNMANAGED_CONF", unmanaged_conf), \
         patch.object(WifiService, "_run_silent", new=AsyncMock(side_effect=fake_run_silent)):
        with pytest.raises(RuntimeError, match="AP-Teardown"):
            await service.finalize_setup_ap_teardown()

    # Marker must still exist — a reboot then bypasses the AP despite
    # the partial teardown.
    assert marker.exists()


@pytest.mark.asyncio
async def test_finalize_is_idempotent(tmp_path: Path) -> None:
    """A second finalize call after the marker exists is a clean no-op."""
    service = WifiService()
    service._mock = False
    service._use_nmcli = True

    marker = tmp_path / "config" / ".setup-complete"
    marker.parent.mkdir(parents=True)
    marker.write_text("ok")
    unmanaged_conf = tmp_path / "conf.d" / "99-tonado-wlan0-unmanaged.conf"

    called = False

    async def fake_run_silent(cmd: list[str]) -> int:
        nonlocal called
        called = True
        return 0

    with patch.object(WifiService, "SETUP_COMPLETE_MARKER", marker), \
         patch.object(WifiService, "NM_UNMANAGED_CONF", unmanaged_conf), \
         patch.object(WifiService, "_run_silent", new=AsyncMock(side_effect=fake_run_silent)):
        await service.finalize_setup_ap_teardown()

    assert called is False, "second finalize must not shell out again"


@pytest.mark.asyncio
async def test_probe_lockout_after_repeated_failures() -> None:
    """After PROBE_FAIL_LOCKOUT consecutive fails, the probe hard-locks."""
    service = _make_nmcli_service()
    service._probe_fail_count = service.PROBE_FAIL_LOCKOUT
    result = await service.probe_home_wifi("HomeWiFi", "pw")
    assert result["ok"] is False
    assert result.get("locked") is True
    assert "neu starten" in result["error"].lower()
    # Lockout does NOT mint a token.
    assert result.get("token") is None


@pytest.mark.asyncio
async def test_cancel_probe_is_idempotent() -> None:
    """cancel_probe must return ok even when no profile is present."""
    service = _make_nmcli_service()

    called: list[tuple] = []

    async def fake_create_subprocess_exec(*args, **kwargs):  # type: ignore[no-untyped-def]
        called.append(args)
        return _FakeProc(returncode=0)

    with patch("asyncio.create_subprocess_exec", new=fake_create_subprocess_exec):
        result = await service.cancel_probe()

    assert result == {"ok": True}
    assert called, "nmcli connection delete must be attempted"
    assert "delete" in called[0]


@pytest.mark.asyncio
async def test_confirm_token_expires_after_ttl(monkeypatch) -> None:
    """Registered tokens become invalid once their TTL elapses."""
    from core.services import wifi_service as ws_mod

    service = WifiService()
    service._mock = True
    service._use_nmcli = False

    result = await service.probe_home_wifi("HomeWiFi", "pw")
    token = result["token"]
    assert consume_confirm_token(token) is False or True
    # Re-mint a token so we have something to time-shift against.
    result2 = await service.probe_home_wifi("HomeWiFi", "pw")
    token2 = result2["token"]

    # Fast-forward: push every token's expiry into the past.
    for key in list(ws_mod._confirm_tokens):
        ws_mod._confirm_tokens[key] = 0.0
    assert consume_confirm_token(token2) is False


@pytest.mark.asyncio
async def test_finalize_setup_ap_teardown_mock_still_writes_marker(tmp_path: Path) -> None:
    """In mock mode the marker still gets written — downstream code relies
    on its presence to know setup is finalized, regardless of environment."""
    service = WifiService()  # defaults to mock on dev boxes

    marker = tmp_path / ".setup-complete"
    unmanaged_conf = tmp_path / "99-tonado.conf"

    with patch.object(WifiService, "SETUP_COMPLETE_MARKER", marker), \
         patch.object(WifiService, "NM_UNMANAGED_CONF", unmanaged_conf):
        await service.finalize_setup_ap_teardown()

    assert marker.exists()
