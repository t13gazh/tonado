"""Tests for the WebSocket hub (H6)."""

import json
from unittest.mock import AsyncMock

import pytest

from core.services.event_bus import EventBus
from core.services.websocket_hub import WebSocketHub


class FakeWebSocket:
    """Minimal stand-in for starlette.websockets.WebSocket used by the hub."""

    def __init__(self, *, send_raises: bool = False) -> None:
        self.accepted = False
        self.closed = False
        self.sent: list[str] = []
        self._send_raises = send_raises

    async def accept(self) -> None:
        self.accepted = True

    async def close(self) -> None:
        self.closed = True

    async def send_text(self, text: str) -> None:
        if self._send_raises:
            raise RuntimeError("peer gone")
        self.sent.append(text)


@pytest.fixture
async def hub(event_bus: EventBus) -> WebSocketHub:
    h = WebSocketHub(event_bus)
    await h.start()
    return h


@pytest.mark.asyncio
async def test_connect_accepts_and_tracks(hub: WebSocketHub) -> None:
    ws = FakeWebSocket()
    assert hub.has_connections is False
    await hub.connect(ws)
    assert ws.accepted is True
    assert hub.has_connections is True


@pytest.mark.asyncio
async def test_disconnect_removes_connection(hub: WebSocketHub) -> None:
    ws = FakeWebSocket()
    await hub.connect(ws)
    await hub.disconnect(ws)
    assert hub.has_connections is False


@pytest.mark.asyncio
async def test_broadcasts_player_state(hub: WebSocketHub, event_bus: EventBus) -> None:
    ws = FakeWebSocket()
    await hub.connect(ws)
    await event_bus.publish("player_state_changed", state={"volume": 42})
    assert len(ws.sent) == 1
    msg = json.loads(ws.sent[0])
    assert msg["type"] == "player_state"
    assert msg["data"] == {"volume": 42}


@pytest.mark.asyncio
async def test_new_client_receives_last_state(
    hub: WebSocketHub, event_bus: EventBus
) -> None:
    await event_bus.publish("player_state_changed", state={"volume": 77})
    ws = FakeWebSocket()
    await hub.connect(ws)
    assert len(ws.sent) == 1
    msg = json.loads(ws.sent[0])
    assert msg["data"]["volume"] == 77


@pytest.mark.asyncio
async def test_card_scanned_broadcast(hub: WebSocketHub, event_bus: EventBus) -> None:
    ws = FakeWebSocket()
    await hub.connect(ws)
    await event_bus.publish(
        "card_scanned", card_id="abc", mapping={"content_type": "folder"}
    )
    msg = json.loads(ws.sent[-1])
    assert msg["type"] == "card_scanned"
    assert msg["data"]["card_id"] == "abc"


@pytest.mark.asyncio
async def test_gesture_broadcast(hub: WebSocketHub, event_bus: EventBus) -> None:
    ws = FakeWebSocket()
    await hub.connect(ws)
    await event_bus.publish(
        "gesture_detected", gesture="tilt_left", action="previous_track"
    )
    msg = json.loads(ws.sent[-1])
    assert msg["type"] == "gesture"
    assert msg["data"] == {"gesture": "tilt_left", "action": "previous_track"}


@pytest.mark.asyncio
async def test_failed_send_prunes_connection(
    hub: WebSocketHub, event_bus: EventBus
) -> None:
    """A dead peer must be dropped from the connection set on broadcast failure."""
    good = FakeWebSocket()
    bad = FakeWebSocket(send_raises=True)
    await hub.connect(good)
    await hub.connect(bad)
    await event_bus.publish("player_state_changed", state={"x": 1})
    # Good peer still connected, bad peer evicted
    assert good in hub._connections
    assert bad not in hub._connections


@pytest.mark.asyncio
async def test_stop_closes_all_connections(hub: WebSocketHub) -> None:
    ws1 = FakeWebSocket()
    ws2 = FakeWebSocket()
    await hub.connect(ws1)
    await hub.connect(ws2)
    await hub.stop()
    assert ws1.closed and ws2.closed
    assert hub.has_connections is False
