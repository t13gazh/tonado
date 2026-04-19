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
