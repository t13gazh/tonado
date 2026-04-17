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
