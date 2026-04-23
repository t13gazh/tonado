"""Integration tests for the REST API."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.services.event_bus import EventBus
from core.services.player_service import PlayerService, PlayerState, PlaybackState


@pytest.fixture
def mock_player() -> PlayerService:
    """Create a player service with mocked MPD connection."""
    event_bus = EventBus()
    player = PlayerService(event_bus=event_bus, host="localhost", port=6600)
    player._connected = False  # Don't try to connect to MPD
    player._state = PlayerState(state=PlaybackState.STOPPED, volume=50)
    return player


@pytest.mark.asyncio
async def test_health_endpoint(tmp_path: Path) -> None:
    """Test that the health endpoint works without any services."""
    # Patch settings to use temp paths and mock hardware
    with patch("core.main.Settings") as MockSettings:
        settings = MagicMock()
        settings.db_path = tmp_path / "test.db"
        settings.hardware_mode = "mock"
        settings.mpd_host = "localhost"
        settings.mpd_port = 6600
        settings.card_rescan_cooldown = 2.0
        settings.card_remove_pauses = False
        settings.gyro_enabled = False
        settings.gyro_sensitivity = "normal"
        settings.host = "0.0.0.0"
        settings.port = 8080
        MockSettings.return_value = settings

        # Also mock MPD connection
        with patch("core.services.player_service.MPDClient"):
            from core.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/health")
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "ok"
                assert data["version"] == "0.3.1-beta"
