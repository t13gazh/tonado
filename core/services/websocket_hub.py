"""WebSocket hub for broadcasting real-time state to connected clients."""

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

from core.services.event_bus import EventBus

logger = logging.getLogger(__name__)


class WebSocketHub:
    """Manages WebSocket connections and broadcasts events to all clients."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._connections: set[WebSocket] = set()
        self._last_state: dict[str, Any] = {}

    async def start(self) -> None:
        """Subscribe to events that should be broadcast."""
        self._event_bus.subscribe("player_state_changed", self._on_player_state)
        self._event_bus.subscribe("card_scanned", self._on_card_scanned)
        self._event_bus.subscribe("card_removed", self._on_card_removed)
        self._event_bus.subscribe("card_unknown", self._on_card_unknown)
        self._event_bus.subscribe("gesture_detected", self._on_gesture)
        logger.info("WebSocket hub started")

    async def connect(self, ws: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await ws.accept()
        self._connections.add(ws)
        logger.debug("WebSocket client connected (%d total)", len(self._connections))
        # Send current state immediately
        if self._last_state:
            await self._send(ws, {"type": "player_state", "data": self._last_state})

    async def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket connection."""
        self._connections.discard(ws)
        logger.debug("WebSocket client disconnected (%d remaining)", len(self._connections))

    async def _broadcast(self, message: dict[str, Any]) -> None:
        """Send a message to all connected clients."""
        if not self._connections:
            return
        payload = json.dumps(message)
        disconnected = set()
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                disconnected.add(ws)
        self._connections -= disconnected

    async def _send(self, ws: WebSocket, message: dict[str, Any]) -> None:
        """Send a message to a single client."""
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            self._connections.discard(ws)

    # Event handlers

    async def _on_player_state(self, state: dict[str, Any], **_: Any) -> None:
        self._last_state = state
        await self._broadcast({"type": "player_state", "data": state})

    async def _on_card_scanned(self, card_id: str, mapping: dict[str, Any], **_: Any) -> None:
        await self._broadcast({
            "type": "card_scanned",
            "data": {"card_id": card_id, "mapping": mapping},
        })

    async def _on_card_removed(self, card_id: str | None, should_pause: bool, **_: Any) -> None:
        await self._broadcast({
            "type": "card_removed",
            "data": {"card_id": card_id, "should_pause": should_pause},
        })

    async def _on_card_unknown(self, card_id: str, **_: Any) -> None:
        await self._broadcast({
            "type": "card_unknown",
            "data": {"card_id": card_id},
        })

    async def _on_gesture(self, gesture: str, action: str, **_: Any) -> None:
        await self._broadcast({
            "type": "gesture",
            "data": {"gesture": gesture, "action": action},
        })
