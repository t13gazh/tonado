"""Tests for the browser-audio proxy endpoint ``/api/player/stream`` and
the ``player_stream_ready`` WebSocket event.

The stream endpoint is a stateless proxy in front of MPD's httpd output.
These tests exercise its resource-cleanup and MIME/icy pass-through
behaviour without a real MPD server, by injecting a stubbed
``httpx.AsyncClient.stream``.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import core.routers.player as player_router
from core.services.event_bus import EventBus
from core.services.player_service import PlaybackState, PlayerService
from core.services.websocket_hub import WebSocketHub
from tests.mock_mpd import MockMPDClient


class _FakeUpstreamResponse:
    """Minimal stand-in for ``httpx.Response`` in streaming mode."""

    def __init__(
        self,
        chunks: list[bytes],
        headers: dict[str, str] | None = None,
        on_close: list[bool] | None = None,
        raise_after: int | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._chunks = chunks
        self.headers = headers or {"content-type": "audio/mpeg"}
        self._closed = on_close if on_close is not None else []
        self._raise_after = raise_after
        self._exc = exc
        self._iter_count = 0

    async def aiter_bytes(self, chunk_size: int = 4096) -> AsyncIterator[bytes]:
        for i, chunk in enumerate(self._chunks):
            if self._raise_after is not None and i == self._raise_after and self._exc:
                raise self._exc
            self._iter_count += 1
            yield chunk

    async def aclose(self) -> None:  # pragma: no cover - not exercised directly
        self._closed.append(True)


class _FakeClientStreamContext:
    """Async context manager returned by ``client.stream()``."""

    def __init__(self, response: _FakeUpstreamResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeUpstreamResponse:
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._response.aclose()


class _FakeAsyncClient:
    """Stand-in for ``httpx.AsyncClient`` used by the proxy endpoint."""

    def __init__(self, response: _FakeUpstreamResponse, *, connect_error: Exception | None = None) -> None:
        self._response = response
        self._connect_error = connect_error
        self.closed = False

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.closed = True

    def stream(self, method: str, url: str) -> _FakeClientStreamContext:
        if self._connect_error is not None:
            # Simulate an error inside the context manager's __aenter__
            err = self._connect_error

            @asynccontextmanager
            async def _raiser():
                raise err
                yield  # unreachable

            return _raiser()  # type: ignore[return-value]
        return _FakeClientStreamContext(self._response)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(player_router.router)
    return app


async def _hit_stream(app: FastAPI) -> tuple[int, bytes, dict[str, str]]:
    transport = ASGITransport(app=app, client=("127.0.0.1", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/player/stream")
        body = resp.content
        return resp.status_code, body, dict(resp.headers)


# --- MIME + icy-header pass-through -----------------------------------------


@pytest.mark.asyncio
async def test_stream_mime_and_icy_headers_passed_through(monkeypatch):
    closed: list[bool] = []
    response = _FakeUpstreamResponse(
        chunks=[b"OggS\x00\x00", b"more"],
        headers={
            "content-type": "audio/ogg",
            "icy-name": "Tonado Radio",
            "icy-br": "128",
            "icy-genre": "Kids",
        },
        on_close=closed,
    )
    fake_client = _FakeAsyncClient(response)

    def factory(*a: Any, **kw: Any) -> _FakeAsyncClient:
        return fake_client

    monkeypatch.setattr(player_router.httpx, "AsyncClient", factory)

    status, body, headers = await _hit_stream(_build_app())

    assert status == 200
    assert headers["content-type"].startswith("audio/ogg")
    assert headers.get("cache-control") == "no-store"
    assert headers.get("icy-name") == "Tonado Radio"
    assert headers.get("icy-br") == "128"
    assert headers.get("icy-genre") == "Kids"
    assert body == b"OggS\x00\x00more"
    # AsyncExitStack should have closed both context managers.
    assert fake_client.closed is True
    assert closed == [True]


# --- Cleanup on connect error ------------------------------------------------


@pytest.mark.asyncio
async def test_stream_retries_and_cleans_up_on_connect_error(monkeypatch):
    """When the first attempt fails with a connection error, the proxy
    must (a) close the failed client before retrying, (b) after
    ``max_attempts`` give up with 503, not a hang."""
    import httpx

    created: list[_FakeAsyncClient] = []

    def factory(*a: Any, **kw: Any) -> _FakeAsyncClient:
        c = _FakeAsyncClient(
            _FakeUpstreamResponse([b""]),
            connect_error=httpx.ConnectError("refused"),
        )
        created.append(c)
        return c

    monkeypatch.setattr(player_router.httpx, "AsyncClient", factory)
    # Make the retry loop fast by patching just the module-level alias
    # the endpoint uses, NOT asyncio.sleep globally.
    _real_sleep = asyncio.sleep

    async def _fast_sleep(_delay: float) -> None:
        await _real_sleep(0)

    monkeypatch.setattr(player_router.asyncio, "sleep", _fast_sleep)

    status, _body, _headers = await _hit_stream(_build_app())

    assert status == 503
    # 3 attempts per the new retry count.
    assert len(created) == 3
    # Every client must have been closed (AsyncExitStack cleanup path).
    assert all(c.closed for c in created)


# --- StopAsyncIteration (empty reply) ---------------------------------------


@pytest.mark.asyncio
async def test_stream_empty_upstream_retries(monkeypatch):
    """MPD's httpd returns an empty 200 when idle → first read raises
    StopAsyncIteration before any chunk arrives.  The proxy should
    retry, and if every attempt stays empty, return 503."""
    created: list[_FakeAsyncClient] = []

    def factory(*a: Any, **kw: Any) -> _FakeAsyncClient:
        c = _FakeAsyncClient(_FakeUpstreamResponse(chunks=[]))
        created.append(c)
        return c

    monkeypatch.setattr(player_router.httpx, "AsyncClient", factory)
    _real_sleep = asyncio.sleep

    async def _fast_sleep(_delay: float) -> None:
        await _real_sleep(0)

    monkeypatch.setattr(player_router.asyncio, "sleep", _fast_sleep)

    status, _body, _headers = await _hit_stream(_build_app())
    assert status == 503
    assert len(created) == 3
    assert all(c.closed for c in created)


# --- player_stream_ready broadcast ------------------------------------------


@pytest.mark.asyncio
async def test_stream_ready_broadcasts_on_event_bus():
    """When PlayerService detects a new track, WebSocketHub should
    forward the ``player_stream_ready`` event to connected clients."""
    bus = EventBus()
    hub = WebSocketHub(bus)
    await hub.start()

    received: list[dict] = []

    async def _capture(message: dict) -> None:
        received.append(message)

    # Replace the private broadcast with a capture so we don't need a
    # real WebSocket.
    hub._broadcast = _capture  # type: ignore[assignment]

    await bus.publish("player_stream_ready", uri="http://example/stream.mp3")

    assert len(received) == 1
    assert received[0]["type"] == "player_stream_ready"
    assert received[0]["data"] == {"uri": "http://example/stream.mp3"}


@pytest.mark.asyncio
async def test_player_service_emits_stream_ready_on_track_change(event_bus: EventBus):
    """A track change while MPD reports ``play`` must produce exactly
    one ``player_stream_ready`` event with the new URI."""
    player = PlayerService(event_bus=event_bus)
    player._client = MockMPDClient()
    await player.start()
    try:
        events: list[str] = []

        async def collect(uri: str = "", **_: Any) -> None:
            events.append(uri)

        event_bus.subscribe("player_stream_ready", collect)

        # Queue + start playback — this triggers a sync_state with a
        # fresh URI.
        await player.play_folder("Album1/track1.mp3")
        assert player.state.state == PlaybackState.PLAYING

        # Give the scheduled task a chance to fire (its internal delay
        # is 300 ms).
        await asyncio.sleep(0.5)

        assert len(events) == 1, f"Expected 1 stream_ready, got {events!r}"
        assert events[0] == player.state.current_uri

        # Second sync without URI change must NOT emit again.
        await player._sync_state()
        await asyncio.sleep(0.4)
        assert len(events) == 1, "stream_ready fired again for same track"
    finally:
        await player.stop()
