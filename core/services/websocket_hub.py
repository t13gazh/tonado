"""WebSocket hub for broadcasting real-time state to connected clients."""

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

from core.services.event_bus import EventBus

logger = logging.getLogger(__name__)


MAX_CONNECTIONS = 20


class WebSocketHub:
    """Manages WebSocket connections and broadcasts events to all clients."""

    def __init__(self, event_bus: EventBus, max_connections: int = MAX_CONNECTIONS) -> None:
        self._event_bus = event_bus
        self._connections: set[WebSocket] = set()
        self._last_state: dict[str, Any] = {}
        # Last authoritative sleep-timer snapshot. Hydrates late joiners so a
        # parent opening a second tab mid-countdown sees the pill immediately
        # instead of waiting for the next minute boundary. `None` means no
        # sleep-timer event has fired yet this process — in that case the
        # frontend's REST poll on mount still fills the gap.
        self._last_sleep_state: dict[str, Any] | None = None
        self._max_connections = max_connections

    @property
    def is_full(self) -> bool:
        return len(self._connections) >= self._max_connections

    async def stop(self) -> None:
        """Close all connections and unsubscribe from events."""
        for ws in list(self._connections):
            try:
                await ws.close()
            except Exception:
                pass
        self._connections.clear()
        logger.info("WebSocket hub stopped")

    @property
    def has_connections(self) -> bool:
        """True if at least one WebSocket client is connected."""
        return bool(self._connections)

    async def start(self) -> None:
        """Subscribe to events that should be broadcast."""
        self._event_bus.subscribe("player_state_changed", self._on_player_state)
        self._event_bus.subscribe("card_scanned", self._on_card_scanned)
        self._event_bus.subscribe("card_removed", self._on_card_removed)
        self._event_bus.subscribe("card_unknown", self._on_card_unknown)
        self._event_bus.subscribe("gesture_detected", self._on_gesture)
        self._event_bus.subscribe("sleep_timer_updated", self._on_sleep_timer)
        self._event_bus.subscribe("player_stream_ready", self._on_stream_ready)
        logger.info("WebSocket hub started")

    async def connect(self, ws: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await ws.accept()
        self._connections.add(ws)
        logger.debug("WebSocket client connected (%d total)", len(self._connections))
        # Send current state immediately so late joiners hydrate without waiting
        # for the next broadcast. Player state first (hero is most visible),
        # then sleep-timer snapshot if a countdown is running.
        if self._last_state:
            await self._send(ws, {"type": "player_state", "data": self._last_state})
        if self._last_sleep_state is not None:
            await self._send(ws, {"type": "sleep_timer", "data": self._last_sleep_state})

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

    async def _on_stream_ready(self, uri: str = "", **_: Any) -> None:
        """Signal the browser proxy that MPD's httpd output has a fresh
        stream for the new track and is ready to be reconnected.

        Sent after a track change once MPD reports ``play`` with non-zero
        elapsed/duration, so the browser doesn't race the encoder and
        receive an empty reply.
        """
        await self._broadcast({
            "type": "player_stream_ready",
            "data": {"uri": uri},
        })

    async def _on_sleep_timer(
        self,
        remaining_seconds: float = 0,
        fading: bool = False,
        active: bool = False,
        duration_seconds: int | None = None,
        **_: Any,
    ) -> None:
        """Forward sleep-timer state changes so all parent phones stay in sync."""
        payload = {
            "active": active,
            "remaining_seconds": max(0, int(remaining_seconds)),
            "fading": fading,
            "duration_seconds": duration_seconds,
        }
        # Cache the latest snapshot so new connections hydrate on connect(),
        # not on the next tick. Cancel events (active=False) are kept too so
        # a tab opened right after cancellation doesn't show a stale pill.
        self._last_sleep_state = payload
        await self._broadcast({"type": "sleep_timer", "data": payload})
