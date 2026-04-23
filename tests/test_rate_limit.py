"""Tests for the global rate-limit middleware."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.utils.rate_limit import RateLimitMiddleware


def _build_app(**middleware_kwargs) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, **middleware_kwargs)

    @app.post("/echo")
    async def echo() -> dict:
        return {"ok": True}

    @app.get("/echo")
    async def echo_get() -> dict:
        return {"ok": True}

    @app.post("/api/library/upload/foo")
    async def upload() -> dict:
        return {"ok": True}

    @app.post("/api/player/stream/whatever")
    async def stream() -> dict:
        return {"ok": True}

    @app.post("/api/auth/login")
    async def login() -> dict:
        return {"ok": True}

    @app.post("/api/system/restore")
    async def restore() -> dict:
        return {"ok": True}

    @app.post("/api/auth/sleep-timer")
    async def sleep_start() -> dict:
        return {"ok": True}

    @app.delete("/api/auth/sleep-timer")
    async def sleep_cancel() -> dict:
        return {"ok": True}

    @app.post("/api/auth/sleep-timer/extend")
    async def sleep_extend() -> dict:
        return {"ok": True}

    # Future sibling that must NOT inherit the sleep-timer bucket by prefix.
    @app.post("/api/auth/sleep-timer-history")
    async def sleep_history() -> dict:
        return {"ok": True}

    # F1: /api/system/update/check does a `git fetch` on every call —
    # it must be rate-limited despite being a GET.
    @app.get("/api/system/update/check")
    async def update_check() -> dict:
        return {"ok": True}

    @app.get("/api/player/status")
    async def player_status() -> dict:
        return {"ok": True}

    # F1: /api/setup/test-wifi spawns nmcli + joins a WPA handshake on every
    # call — brute-force-adjacent on the open setup AP. Register both probe
    # endpoints so the new `wifi_probe` bucket can be exercised.
    @app.post("/api/setup/test-wifi")
    async def setup_test_wifi() -> dict:
        return {"ok": True}

    @app.post("/api/setup/wifi/connect")
    async def setup_wifi_connect() -> dict:
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_default_limit_blocks_after_threshold():
    app = _build_app(default_limit=3, default_window=60)
    transport = ASGITransport(app=app, client=("1.1.1.1", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(3):
            resp = await c.post("/echo")
            assert resp.status_code == 200
        resp = await c.post("/echo")
        assert resp.status_code == 429


@pytest.mark.asyncio
async def test_get_requests_are_exempt():
    app = _build_app(default_limit=2, default_window=60)
    transport = ASGITransport(app=app, client=("2.2.2.2", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(10):
            resp = await c.get("/echo")
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_upload_bucket_has_stricter_limit():
    app = _build_app(default_limit=100, upload_limit=2, upload_window=60)
    transport = ASGITransport(app=app, client=("3.3.3.3", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(2):
            resp = await c.post("/api/library/upload/foo")
            assert resp.status_code == 200
        resp = await c.post("/api/library/upload/foo")
        assert resp.status_code == 429
        # Non-upload bucket is unaffected
        resp = await c.post("/echo")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_stream_endpoint_bypasses_limit():
    app = _build_app(default_limit=1, default_window=60)
    transport = ASGITransport(app=app, client=("4.4.4.4", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(5):
            resp = await c.post("/api/player/stream/whatever")
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_limit_is_per_ip():
    """Two distinct clients must not share a bucket."""
    app = _build_app(default_limit=2, default_window=60)
    transport = ASGITransport(app=app, client=("127.0.0.1", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(2):
            resp = await c.post("/echo", headers={"X-Forwarded-For": "5.5.5.5"})
            assert resp.status_code == 200
        # 5.5.5.5 is locked out
        resp = await c.post("/echo", headers={"X-Forwarded-For": "5.5.5.5"})
        assert resp.status_code == 429
        # 6.6.6.6 still has quota
        resp = await c.post("/echo", headers={"X-Forwarded-For": "6.6.6.6"})
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_login_bucket_stricter_than_default():
    """Login must not fall through to the 100/min default — PBKDF2 burns CPU
    on the Pi even when the PIN is correct."""
    app = _build_app(default_limit=100, login_limit=2, login_window=60)
    transport = ASGITransport(app=app, client=("7.7.7.7", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(2):
            resp = await c.post("/api/auth/login")
            assert resp.status_code == 200
        resp = await c.post("/api/auth/login")
        assert resp.status_code == 429
        # Unrelated endpoint must still work
        resp = await c.post("/echo")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_restore_bucket_stricter_than_default():
    """Backup restore parses up to 10 MB JSON — own bucket so a single IP
    can't DoS the Pi Zero W."""
    app = _build_app(default_limit=100, restore_limit=1, restore_window=60)
    transport = ASGITransport(app=app, client=("8.8.8.8", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/system/restore")
        assert resp.status_code == 200
        resp = await c.post("/api/system/restore")
        assert resp.status_code == 429
        # Login bucket is separate
        resp = await c.post("/api/auth/login")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_sleep_timer_bucket_limits_rapid_taps():
    """Pill button spam (start/extend/cancel/start/...) must not burn the
    default 100/min write bucket — a child can tap 20 times per minute
    before the server starts logging 429s."""
    app = _build_app(default_limit=100, sleep_timer_limit=3, sleep_timer_window=60)
    transport = ASGITransport(app=app, client=("9.9.9.9", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/auth/sleep-timer")
        assert resp.status_code == 200
        resp = await c.post("/api/auth/sleep-timer/extend")
        assert resp.status_code == 200
        resp = await c.delete("/api/auth/sleep-timer")
        assert resp.status_code == 200
        # Fourth request across any sleep-timer sub-path is blocked.
        resp = await c.post("/api/auth/sleep-timer/extend")
        assert resp.status_code == 429


@pytest.mark.asyncio
async def test_sleep_timer_bucket_isolated_from_other_endpoints():
    """Hitting the sleep-timer bucket must NOT spill into the default or
    login buckets (and vice versa)."""
    app = _build_app(
        default_limit=100,
        login_limit=100,
        sleep_timer_limit=2,
        sleep_timer_window=60,
    )
    transport = ASGITransport(app=app, client=("10.10.10.10", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Exhaust sleep-timer quota
        for _ in range(2):
            resp = await c.post("/api/auth/sleep-timer")
            assert resp.status_code == 200
        resp = await c.post("/api/auth/sleep-timer")
        assert resp.status_code == 429
        # Generic write endpoint stays open
        resp = await c.post("/echo")
        assert resp.status_code == 200
        # Login bucket stays open
        resp = await c.post("/api/auth/login")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_sleep_timer_prefix_does_not_capture_siblings():
    """Regression guard: exhausting the sleep-timer bucket must NOT block a
    sibling route like `/sleep-timer-history` that merely shares the prefix.
    We use `path in _SLEEP_TIMER_PATHS` exactly like the login/restore paths
    so new sibling endpoints opt in explicitly."""
    app = _build_app(
        default_limit=100,
        sleep_timer_limit=1,
        sleep_timer_window=60,
    )
    transport = ASGITransport(app=app, client=("11.11.11.11", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Exhaust sleep-timer bucket with the real write endpoint.
        resp = await c.post("/api/auth/sleep-timer")
        assert resp.status_code == 200
        resp = await c.post("/api/auth/sleep-timer")
        assert resp.status_code == 429
        # Sibling route shares the prefix but falls into the default bucket,
        # so it stays open even though the sleep-timer bucket is saturated.
        resp = await c.post("/api/auth/sleep-timer-history")
        assert resp.status_code == 200


# --- F1: /api/system/update/check must be rate-limited despite being a GET ---


@pytest.mark.asyncio
async def test_update_check_rate_limited():
    """F1: 6 GETs on /api/system/update/check pass, 7th is rejected.

    Each call does a git fetch (network + disk) — a loop would wear out
    the SD card. Parent-tier auth is enforced at the router level, but
    we still need a per-IP bucket to stop a compromised LAN device with
    a valid token."""
    app = _build_app(update_check_limit=6, update_check_window=60)
    transport = ASGITransport(app=app, client=("12.12.12.12", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(6):
            resp = await c.get("/api/system/update/check")
            assert resp.status_code == 200
        resp = await c.get("/api/system/update/check")
        assert resp.status_code == 429


@pytest.mark.asyncio
async def test_update_check_rate_limited_with_trailing_slash():
    """Trailing-slash bypass guard: `/api/system/update/check/` must fall
    into the same 6/min bucket as `/api/system/update/check`. Without
    path normalisation the exact string compare would miss, the request
    would be re-classified as a plain GET, and the GET exempt would
    serve it for free — defeating the whole F1 bucket."""
    app = _build_app(update_check_limit=6, update_check_window=60)

    # Register the trailing-slash variant as its own route so Starlette
    # doesn't 307-redirect before the middleware bucket has a chance to
    # run. The middleware itself must catch both forms.
    @app.get("/api/system/update/check/")
    async def update_check_slash() -> dict:
        return {"ok": True}

    transport = ASGITransport(app=app, client=("18.18.18.18", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(6):
            resp = await c.get("/api/system/update/check/")
            assert resp.status_code == 200
        resp = await c.get("/api/system/update/check/")
        assert resp.status_code == 429


@pytest.mark.asyncio
async def test_update_check_per_ip_bucket():
    """Two distinct clients must have separate update-check buckets."""
    app = _build_app(update_check_limit=6, update_check_window=60)
    transport = ASGITransport(app=app, client=("127.0.0.1", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(6):
            resp = await c.get(
                "/api/system/update/check",
                headers={"X-Forwarded-For": "13.13.13.13"},
            )
            assert resp.status_code == 200
        for _ in range(6):
            resp = await c.get(
                "/api/system/update/check",
                headers={"X-Forwarded-For": "14.14.14.14"},
            )
            assert resp.status_code == 200
        # First IP is now locked out
        resp = await c.get(
            "/api/system/update/check",
            headers={"X-Forwarded-For": "13.13.13.13"},
        )
        assert resp.status_code == 429


@pytest.mark.asyncio
async def test_other_get_endpoints_not_rate_limited():
    """Polling GETs (e.g. /api/player/status) must stay exempt — the
    frontend hits them multiple times per second. Putting them into the
    100/min default would break the live UI."""
    app = _build_app(default_limit=2, default_window=60, update_check_limit=6)
    transport = ASGITransport(app=app, client=("15.15.15.15", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(200):
            resp = await c.get("/api/player/status")
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_check_does_not_share_default_bucket():
    """Exhausting the update-check bucket must not leak into the default
    write bucket — POST /echo should still work after 7 update-check
    calls on the same IP."""
    app = _build_app(default_limit=100, update_check_limit=1, update_check_window=60)
    transport = ASGITransport(app=app, client=("16.16.16.16", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/system/update/check")
        assert resp.status_code == 200
        resp = await c.get("/api/system/update/check")
        assert resp.status_code == 429
        # Default write bucket is untouched
        resp = await c.post("/echo")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_check_429_body_is_german():
    """Error bodies are user-facing — German with real umlauts."""
    app = _build_app(update_check_limit=1, update_check_window=60)
    transport = ASGITransport(app=app, client=("17.17.17.17", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/system/update/check")
        assert resp.status_code == 200
        resp = await c.get("/api/system/update/check")
        assert resp.status_code == 429
        detail = resp.json()["detail"]
        assert "Zu viele Anfragen" in detail


# --- F1: wifi_probe bucket limits brute-force against neighbouring PSKs ---


@pytest.mark.asyncio
async def test_wifi_probe_bucket_limits_brute_force():
    """6 calls to /api/setup/test-wifi pass, 7th is 429.

    Each call spawns nmcli + attempts a WPA handshake. On the open setup
    AP a neighbour could otherwise brute-force the user's home PSK in a
    tight loop. The in-process fail-counter catches wrong passwords; this
    middleware bucket additionally caps call rate across concurrent
    clients.
    """
    app = _build_app(wifi_probe_limit=6, wifi_probe_window=60)
    transport = ASGITransport(app=app, client=("30.30.30.30", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(6):
            resp = await c.post("/api/setup/test-wifi", json={"ssid": "x", "password": "y"})
            assert resp.status_code == 200
        resp = await c.post("/api/setup/test-wifi", json={"ssid": "x", "password": "y"})
        assert resp.status_code == 429


@pytest.mark.asyncio
async def test_wifi_probe_bucket_covers_wifi_connect():
    """wifi/connect is an alias path — same bucket, not the default 100/min."""
    app = _build_app(default_limit=100, wifi_probe_limit=2, wifi_probe_window=60)
    transport = ASGITransport(app=app, client=("31.31.31.31", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/setup/wifi/connect", json={"ssid": "x"})
        assert resp.status_code == 200
        resp = await c.post("/api/setup/test-wifi", json={"ssid": "x"})
        assert resp.status_code == 200
        # 3rd request across both probe endpoints → 429 (shared bucket)
        resp = await c.post("/api/setup/wifi/connect", json={"ssid": "x"})
        assert resp.status_code == 429


@pytest.mark.asyncio
async def test_wifi_probe_bucket_isolated_from_default():
    """Exhausting wifi_probe must not spill into the default write bucket."""
    app = _build_app(default_limit=10, wifi_probe_limit=1, wifi_probe_window=60)
    transport = ASGITransport(app=app, client=("32.32.32.32", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/setup/test-wifi", json={"ssid": "x"})
        assert resp.status_code == 200
        resp = await c.post("/api/setup/test-wifi", json={"ssid": "x"})
        assert resp.status_code == 429
        # Unrelated write endpoint keeps working
        resp = await c.post("/echo")
        assert resp.status_code == 200
