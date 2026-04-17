"""Integration tests for API routers — auth middleware, path traversal, input validation.

Uses a real FastAPI app with in-memory services (no mocking of app internals).
"""

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from core.database import DatabaseManager
from core.hardware.rfid import MockRfidReader
from core.routers import auth, cards, config, library, player, playlists, streams, system
from core.services.auth_service import AuthService, AuthTier
from core.services.backup_service import BackupService
from core.services.card_service import CardService
from core.services.config_service import ConfigService
from core.services.event_bus import EventBus
from core.services.gyro_service import GyroService
from core.services.hardware_detector import HardwareDetector
from core.services.library_service import LibraryService
from core.services.player_service import PlayerService
from core.services.playlist_service import PlaylistService
from core.services.stream_service import StreamService
from core.services.system_service import SystemService
from core.services.timer_service import TimerService
from core.services.wifi_service import WifiService
from tests.mock_mpd import MockMPDClient


@pytest_asyncio.fixture
async def client(tmp_path: Path):
    """Create a real FastAPI app with all routers and in-memory services."""
    app = FastAPI()

    # Database
    db_mgr = DatabaseManager(tmp_path / "test.db")
    await db_mgr.start()
    db = db_mgr.connection

    # Services
    event_bus = EventBus()
    config_svc = ConfigService(db, event_bus)
    await config_svc.start()

    auth_svc = AuthService(config_svc)
    await auth_svc.start()

    player_svc = PlayerService(event_bus=event_bus)
    player_svc._client = MockMPDClient()
    await player_svc.start()

    card_svc = CardService(MockRfidReader(), event_bus, db, config_svc)
    await card_svc.start()

    library_svc = LibraryService(tmp_path / "media")
    await library_svc.start()

    stream_svc = StreamService(db, podcast_dir=tmp_path / "podcasts")
    await stream_svc.start()

    playlist_svc = PlaylistService(db, media_dir=tmp_path / "media")
    await playlist_svc.start()

    gyro_svc = GyroService(sensor=None, event_bus=event_bus)
    timer_svc = TimerService(event_bus, player_svc, config_svc)
    system_svc = SystemService()
    backup_svc = BackupService(db, config_svc)
    wifi_svc = WifiService()
    hw_detector = HardwareDetector()

    # Wire app.state
    app.state.player_service = player_svc
    app.state.card_service = card_svc
    app.state.config_service = config_svc
    app.state.library_service = library_svc
    app.state.stream_service = stream_svc
    app.state.playlist_service = playlist_svc
    app.state.auth_service = auth_svc
    app.state.timer_service = timer_svc
    app.state.system_service = system_svc
    app.state.backup_service = backup_svc
    app.state.wifi_service = wifi_svc
    app.state.hardware_detector = hw_detector
    app.state.gyro_service = gyro_svc

    # Include routers
    app.include_router(auth.router)
    app.include_router(cards.router)
    app.include_router(config.router)
    app.include_router(library.router)
    app.include_router(streams.router)
    app.include_router(playlists.router)
    app.include_router(system.router)
    app.include_router(player.router)

    transport = ASGITransport(app=app, client=("127.0.0.1", 0))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, auth_svc

    await card_svc.stop()
    await player_svc.stop()
    await db_mgr.stop()


async def _get_token(auth_svc: AuthService, tier: AuthTier, pin: str = "1234") -> str:
    """Helper to set PIN and get a JWT token."""
    await auth_svc.set_pin(tier, pin)
    result = await auth_svc.login(pin)
    return result["token"]


# --- Auth middleware tests ---


@pytest.mark.asyncio
async def test_public_endpoints_no_auth(client):
    c, _ = client
    # Read endpoints should work without auth
    for path in ["/api/cards/", "/api/config/", "/api/streams/radio", "/api/streams/podcasts",
                 "/api/playlists/", "/api/library/folders"]:
        resp = await c.get(path)
        assert resp.status_code == 200, f"GET {path} should be public, got {resp.status_code}"


@pytest.mark.asyncio
async def test_write_endpoints_require_auth(client):
    c, auth_svc = client
    # Set a PIN so auth is enforced
    await auth_svc.set_pin(AuthTier.PARENT, "1234")

    # POST/PUT/DELETE without token → 403
    endpoints = [
        ("POST", "/api/cards/", {"card_id": "x", "name": "x", "content_type": "folder", "content_path": "x"}),
        ("PUT", "/api/config/", {"key": "test", "value": "x"}),
        ("DELETE", "/api/cards/nonexistent"),
        ("POST", "/api/streams/radio", {"name": "x", "url": "http://x.com"}),
        ("DELETE", "/api/streams/radio/999"),
        ("POST", "/api/playlists/", {"name": "test"}),
    ]
    for method, path, *body in endpoints:
        kwargs = {"json": body[0]} if body else {}
        resp = await c.request(method, path, **kwargs)
        assert resp.status_code == 403, f"{method} {path} without auth should be 403, got {resp.status_code}"


@pytest.mark.asyncio
async def test_write_with_valid_token(client):
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}

    # Config set should work with valid parent token
    resp = await c.put("/api/config/", json={"key": "test.key", "value": "hello"}, headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_expert_endpoints_reject_parent_token(client):
    c, auth_svc = client
    await auth_svc.set_pin(AuthTier.PARENT, "1234")
    await auth_svc.set_pin(AuthTier.EXPERT, "9999")
    result = await auth_svc.login("1234")  # Parent token
    headers = {"Authorization": f"Bearer {result['token']}"}

    # System restart requires EXPERT
    resp = await c.post("/api/system/restart", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_no_pin_set_allows_access(client):
    c, _ = client
    # No PINs set → all write endpoints accessible
    resp = await c.put("/api/config/", json={"key": "test", "value": "ok"})
    assert resp.status_code == 200


# --- Path traversal ---


@pytest.mark.asyncio
async def test_library_path_traversal(client):
    c, _ = client
    # Attempt path traversal on library endpoints
    for path in ["/api/library/folders/../../etc/passwd",
                 "/api/library/folders/..%2F..%2Fetc%2Fpasswd",
                 "/api/library/folders/%2e%2e/secret"]:
        resp = await c.get(path)
        # Should not return 200 with file content — 404 or cleaned path
        assert resp.status_code in (404, 422), f"Path traversal on {path} should fail"


@pytest.mark.asyncio
async def test_play_folder_rejects_traversal(client):
    c, _ = client
    for bad_path in ["../etc/passwd", "/etc/passwd", "foo/../../bar", "evil\x00", ""]:
        resp = await c.post("/api/player/play-folder", json={"path": bad_path, "start_index": 0})
        assert resp.status_code in (400, 422), f"play-folder accepted traversal: {bad_path!r}"


@pytest.mark.asyncio
async def test_play_folder_accepts_valid(client, tmp_path: Path):
    c, _ = client
    media_root = tmp_path / "media"
    media_root.mkdir(exist_ok=True)
    (media_root / "Hoerbuch").mkdir()
    resp = await c.post("/api/player/play-folder", json={"path": "Hoerbuch", "start_index": 0})
    assert resp.status_code == 200


# --- Input validation ---


@pytest.mark.asyncio
async def test_card_create_validation(client):
    c, _ = client
    # Missing required fields
    resp = await c.post("/api/cards/", json={})
    assert resp.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_login_rate_limiting(client):
    c, auth_svc = client
    await auth_svc.set_pin(AuthTier.PARENT, "1234")

    # 5 failed attempts
    for _ in range(5):
        resp = await c.post("/api/auth/login", json={"pin": "wrong"})
        assert resp.status_code == 401

    # 6th attempt should be rate limited
    resp = await c.post("/api/auth/login", json={"pin": "wrong"})
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_uses_forwarded_ip_behind_trusted_proxy(client):
    """X-Forwarded-For must be honoured so nginx doesn't globalise the bucket."""
    from core.routers import auth as auth_router

    c, auth_svc = client
    await auth_svc.set_pin(AuthTier.PARENT, "1234")
    auth_router._login_attempts.clear()

    # Attacker at 5.5.5.5 locks themselves out
    for _ in range(5):
        resp = await c.post(
            "/api/auth/login",
            json={"pin": "wrong"},
            headers={"X-Forwarded-For": "5.5.5.5"},
        )
        assert resp.status_code == 401
    resp = await c.post(
        "/api/auth/login",
        json={"pin": "wrong"},
        headers={"X-Forwarded-For": "5.5.5.5"},
    )
    assert resp.status_code == 429

    # A different IP must still be able to log in
    resp = await c.post(
        "/api/auth/login",
        json={"pin": "1234"},
        headers={"X-Forwarded-For": "6.6.6.6"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_ignores_forwarded_from_untrusted_peer():
    """Spoofed X-Forwarded-For from a non-proxy peer must be ignored."""
    from core.utils.client_ip import extract_client_ip
    from starlette.datastructures import Headers

    class _Req:
        def __init__(self, peer: str, headers: dict[str, str]) -> None:
            self.client = type("C", (), {"host": peer})()
            self.headers = Headers(headers)

    # Untrusted peer — header ignored
    ip = extract_client_ip(_Req("8.8.8.8", {"x-forwarded-for": "1.2.3.4"}))
    assert ip == "8.8.8.8"
    # Trusted loopback — header honoured
    ip = extract_client_ip(_Req("127.0.0.1", {"x-forwarded-for": "1.2.3.4, 9.9.9.9"}))
    assert ip == "1.2.3.4"
    ip = extract_client_ip(_Req("127.0.0.1", {"x-real-ip": "7.7.7.7"}))
    assert ip == "7.7.7.7"


@pytest.mark.asyncio
async def test_login_pin_min_length(client):
    c, _ = client
    resp = await c.post("/api/auth/login", json={"pin": "12"})
    assert resp.status_code == 422  # Pydantic min_length=4


@pytest.mark.asyncio
async def test_backup_import_invalid_json(client):
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.EXPERT, "9999")
    headers = {"Authorization": f"Bearer {token}"}

    # Upload non-JSON file
    resp = await c.post("/api/system/restore", headers=headers,
                        files={"file": ("backup.json", b"not json", "application/json")})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_backup_import_malformed_schema(client):
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.EXPERT, "9999")
    headers = {"Authorization": f"Bearer {token}"}

    import json
    bad_backup = json.dumps({"version": "1", "cards": [{"card_id": "x"}]}).encode()
    resp = await c.post("/api/system/restore", headers=headers,
                        files={"file": ("backup.json", bad_backup, "application/json")})
    assert resp.status_code == 400
    assert "Invalid backup" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_config_sensitive_keys_blocked(client):
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}

    # Cannot read auth secrets
    resp = await c.get("/api/config/auth.jwt_secret", headers=headers)
    assert resp.status_code == 403

    # Cannot write auth secrets
    resp = await c.put("/api/config/", json={"key": "auth.jwt_secret", "value": "hack"}, headers=headers)
    assert resp.status_code == 403
