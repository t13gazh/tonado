"""Integration tests for API routers — auth middleware, path traversal, input validation.

Uses a real FastAPI app with in-memory services (no mocking of app internals).
"""

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from core.database import DatabaseManager
from core.hardware.gpio_buttons import MockGpioButtonListener, MockGpioButtonScanner
from core.hardware.rfid import MockRfidReader
from core.routers import auth, buttons, cards, config, library, player, playlists, setup, streams, system
from core.services.auth_service import AuthService, AuthTier
from core.services.backup_service import BackupService
from core.services.button_service import ButtonService
from core.services.captive_portal import CaptivePortalService
from core.services.card_service import CardService
from core.services.connectivity_monitor import ConnectivityMonitor
from core.services.config_service import ConfigService
from core.services.event_bus import EventBus
from core.services.gyro_service import GyroService
from core.services.hardware_detector import HardwareDetector
from core.services.library_service import LibraryService
from core.services.player_service import PlayerService
from core.services.playlist_service import PlaylistService
from core.services.setup_wizard import SetupWizard
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
    setup_wizard = SetupWizard(config_svc, wifi_svc, auth_service=auth_svc)
    await setup_wizard.start()
    captive_portal = CaptivePortalService(config_service=config_svc)
    connectivity_monitor = ConnectivityMonitor(
        wifi=wifi_svc,
        portal=captive_portal,
        config=config_svc,
        event_bus=event_bus,
        mock=True,
    )
    button_svc = ButtonService(
        MockGpioButtonScanner(), MockGpioButtonListener(), event_bus, config_svc
    )
    await button_svc.start()

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
    app.state.setup_wizard = setup_wizard
    app.state.captive_portal = captive_portal
    app.state.connectivity_monitor = connectivity_monitor
    app.state.button_service = button_svc
    app.state.db_manager = db_mgr
    app.state.event_bus = event_bus

    # Include routers
    app.include_router(auth.router)
    app.include_router(cards.router)
    app.include_router(config.router)
    app.include_router(library.router)
    app.include_router(streams.router)
    app.include_router(playlists.router)
    app.include_router(system.router)
    app.include_router(player.router)
    app.include_router(setup.router)
    app.include_router(buttons.router)

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

    # Config set should work with valid parent token (whitelisted key + valid value)
    resp = await c.put("/api/config/", json={"key": "player.max_volume", "value": 80}, headers=headers)
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
    resp = await c.put("/api/config/", json={"key": "player.max_volume", "value": 80})
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


# --- Auth-Matrix ---
#
# Each entry is (method, path, required_tier, body_kwargs). Endpoints
# that require a body-validated payload include a minimally-valid one so
# we exercise the tier check (422 validation would otherwise mask 403).
_PROTECTED: list[tuple[str, str, AuthTier, dict]] = [
    # Auth / timer
    ("POST", "/api/auth/sleep-timer", AuthTier.PARENT, {"json": {"minutes": 10}}),
    ("DELETE", "/api/auth/sleep-timer", AuthTier.PARENT, {}),
    ("POST", "/api/auth/sleep-timer/extend", AuthTier.PARENT, {"json": {"minutes": 5}}),

    # Cards
    ("DELETE", "/api/cards/does-not-exist", AuthTier.PARENT, {}),

    # Config
    ("PUT", "/api/config/", AuthTier.PARENT, {"json": {"key": "x.y", "value": "v"}}),

    # Library
    ("DELETE", "/api/library/folders/nope", AuthTier.PARENT, {}),
    ("PUT", "/api/library/folders/nope", AuthTier.PARENT, {"json": {"new_name": "x"}}),

    # Player outputs
    ("POST", "/api/player/outputs/1", AuthTier.PARENT, {"json": {"enabled": True}}),

    # Playlists
    ("POST", "/api/playlists/", AuthTier.PARENT, {"json": {"name": "test"}}),
    ("PUT", "/api/playlists/1", AuthTier.PARENT, {"json": {"name": "renamed"}}),

    # Streams
    ("POST", "/api/streams/radio", AuthTier.PARENT, {"json": {"name": "x", "url": "http://x.com"}}),

    # Buttons
    ("POST", "/api/buttons/scan/start", AuthTier.PARENT, {}),
    ("POST", "/api/buttons/scan/stop", AuthTier.PARENT, {}),
    ("POST", "/api/buttons/test/stop", AuthTier.PARENT, {}),

    # System — expert
    ("POST", "/api/system/restart", AuthTier.EXPERT, {}),
    ("POST", "/api/system/shutdown", AuthTier.EXPERT, {}),
    ("POST", "/api/system/reboot", AuthTier.EXPERT, {}),

    # System update
    ("GET", "/api/system/update/check", AuthTier.PARENT, {}),

    # Setup reset / portal
    ("POST", "/api/setup/reset", AuthTier.EXPERT, {}),
]


@pytest.mark.parametrize("method,path,required,body", _PROTECTED)
@pytest.mark.asyncio
async def test_protected_without_token_denied(client, method, path, required, body):
    """H7 auth-matrix: every protected endpoint returns 403 once a PIN is set and no token is sent."""
    c, auth_svc = client
    # Ensure both tiers have PINs so check_access actually enforces the seal
    await auth_svc.set_pin(AuthTier.PARENT, "1234")
    await auth_svc.set_pin(AuthTier.EXPERT, "9999")
    resp = await c.request(method, path, **body)
    assert resp.status_code == 403, (
        f"{method} {path} should deny without token, got {resp.status_code}"
    )


@pytest.mark.parametrize("method,path,required,body", _PROTECTED)
@pytest.mark.asyncio
async def test_protected_with_expert_token_accepted(client, method, path, required, body):
    """An expert token must be accepted for any PARENT or EXPERT route (not 403)."""
    c, auth_svc = client
    await auth_svc.set_pin(AuthTier.EXPERT, "9999")
    result = await auth_svc.login("9999")
    headers = {"Authorization": f"Bearer {result['token']}"}
    resp = await c.request(method, path, headers=headers, **body)
    # Don't care if the handler 404s/400s for a missing resource — only that
    # it did NOT reject us with 403.
    assert resp.status_code != 403, (
        f"{method} {path} rejected expert token: {resp.status_code}"
    )


@pytest.mark.parametrize(
    "method,path,required,body",
    [t for t in _PROTECTED if t[2] == AuthTier.EXPERT],
)
@pytest.mark.asyncio
async def test_expert_routes_reject_parent_token(client, method, path, required, body):
    """Parent token must NOT unlock expert-only endpoints."""
    c, auth_svc = client
    await auth_svc.set_pin(AuthTier.PARENT, "1234")
    await auth_svc.set_pin(AuthTier.EXPERT, "9999")
    result = await auth_svc.login("1234")
    headers = {"Authorization": f"Bearer {result['token']}"}
    resp = await c.request(method, path, headers=headers, **body)
    assert resp.status_code == 403, (
        f"{method} {path} accepted parent token for expert-only route"
    )


@pytest.mark.asyncio
async def test_setup_complete_requires_parent_pin(client):
    """K1 router integration: /api/setup/complete must return 400 if no PIN is set."""
    c, _ = client
    resp = await c.post("/api/setup/complete")
    assert resp.status_code == 400
    assert "Eltern-PIN" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_setup_complete_succeeds_with_parent_pin(client):
    """K1 router integration: /api/setup/complete succeeds when a PIN is set."""
    c, auth_svc = client
    await auth_svc.set_pin(AuthTier.PARENT, "1234")
    resp = await c.post("/api/setup/complete")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


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


@pytest.mark.asyncio
async def test_config_whitelist_rejects_unknown_key(client):
    """M1: only whitelisted keys are writeable via the public API."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await c.put(
        "/api/config/",
        json={"key": "player.mpd_host", "value": "evil.example.com"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "not writeable" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_config_whitelist_rejects_wrong_type(client):
    """M1: whitelisted keys still validate types and ranges."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}

    # max_volume expects int 10-100
    for bad in ["loud", True, 5, 200, 50.5]:
        resp = await c.put(
            "/api/config/",
            json={"key": "player.max_volume", "value": bad},
            headers=headers,
        )
        assert resp.status_code == 400, f"{bad!r} should be rejected"


@pytest.mark.asyncio
async def test_config_whitelist_accepts_enum(client):
    """M1: enum keys accept known values and reject others."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await c.put(
        "/api/config/",
        json={"key": "gyro.sensitivity", "value": "normal"},
        headers=headers,
    )
    assert resp.status_code == 200

    resp = await c.put(
        "/api/config/",
        json={"key": "gyro.sensitivity", "value": "extreme"},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_system_info_masks_lan_metadata_when_sealed(client):
    """M5: after setup completion, anonymous /system/info must drop hostname/IP."""
    c, auth_svc = client
    await auth_svc.set_pin(AuthTier.PARENT, "1234")
    auth_svc.set_setup_complete(True)

    resp = await c.get("/api/system/info")
    assert resp.status_code == 200
    body = resp.json()
    # Non-sensitive fields still present
    assert "tonado_version" in body
    # LAN-identifying fields wiped
    assert body["hostname"] == ""
    assert body["ip_address"] == ""


@pytest.mark.asyncio
async def test_system_info_full_for_parent(client):
    """M5: PARENT tokens see the full /system/info response."""
    c, auth_svc = client
    await auth_svc.set_pin(AuthTier.PARENT, "1234")
    auth_svc.set_setup_complete(True)
    result = await auth_svc.login("1234")
    headers = {"Authorization": f"Bearer {result['token']}"}

    resp = await c.get("/api/system/info", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    # hostname/ip come from platform.node / runtime; they may be empty on a
    # test host, so only assert that the keys are present and untouched by
    # the masking branch.
    assert "hostname" in body
    assert "ip_address" in body


@pytest.mark.asyncio
async def test_system_info_bootstrap_returns_full(client):
    """M5: before setup completion, anonymous callers still see full info
    so the wizard's waitForServer/HardwareStep can work."""
    c, _ = client
    # No PIN set → bootstrap phase
    resp = await c.get("/api/system/info")
    assert resp.status_code == 200
    body = resp.json()
    assert "hostname" in body
    assert "ip_address" in body


@pytest.mark.asyncio
async def test_backup_restore_rejects_oversize_upload(client):
    """M6: reject a backup file that's obviously too big before parsing it."""
    c, auth_svc = client
    await auth_svc.set_pin(AuthTier.EXPERT, "9999")
    result = await auth_svc.login("9999")
    headers = {"Authorization": f"Bearer {result['token']}"}

    # 11 MB of bytes — above the 10 MB cap
    payload = b"{" + b"x" * (11 * 1024 * 1024) + b"}"
    files = {"file": ("backup.json", payload, "application/json")}
    resp = await c.post("/api/system/restore", headers=headers, files=files)
    assert resp.status_code == 413
    assert "max" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_system_health_generic_network_detail_when_sealed(client):
    """M5: sealed & anonymous callers must not see SSID/IP in health.network.detail."""
    c, auth_svc = client
    await auth_svc.set_pin(AuthTier.PARENT, "1234")
    auth_svc.set_setup_complete(True)

    resp = await c.get("/api/system/health")
    assert resp.status_code == 200
    net = resp.json().get("network", {})
    # Whatever the mock wifi reports, the anonymous-caller detail must be
    # either the generic "Verbunden" or the generic "Nicht verbunden".
    assert net.get("detail") in {"Verbunden", "Nicht verbunden"}


@pytest.mark.asyncio
async def test_playlist_rename_happy_path(client):
    """Playlist rename: PUT /api/playlists/{id} returns updated summary."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}

    # Create
    resp = await c.post("/api/playlists/", json={"name": "Alt"}, headers=headers)
    assert resp.status_code == 201
    pid = resp.json()["id"]

    # Rename
    resp = await c.put(f"/api/playlists/{pid}", json={"name": "Neu"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Neu"

    # Verify persisted
    resp = await c.get(f"/api/playlists/{pid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Neu"


@pytest.mark.asyncio
async def test_playlist_rename_empty_name_rejected(client):
    """Playlist rename: empty name → 422 (pydantic min_length)."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await c.post("/api/playlists/", json={"name": "Alt"}, headers=headers)
    pid = resp.json()["id"]

    resp = await c.put(f"/api/playlists/{pid}", json={"name": ""}, headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_playlist_rename_whitespace_only_rejected(client):
    """Playlist rename: whitespace-only name → 400 after strip."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await c.post("/api/playlists/", json={"name": "Alt"}, headers=headers)
    pid = resp.json()["id"]

    resp = await c.put(f"/api/playlists/{pid}", json={"name": "   "}, headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_playlist_rename_nonexistent_returns_404(client):
    """Playlist rename: missing ID → 404."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await c.put("/api/playlists/99999", json={"name": "x"}, headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_playlist_duplicate_case_insensitive(client):
    """F1: POST with a case-variant of an existing name → 409 with kid-friendly message."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await c.post("/api/playlists/", json={"name": "Favoriten"}, headers=headers)
    assert resp.status_code == 201

    resp = await c.post("/api/playlists/", json={"name": "favoriten"}, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Diese Playlist gibt es schon"


@pytest.mark.asyncio
async def test_rename_playlist_duplicate_case_insensitive(client):
    """F1: PUT renaming onto an existing name (other case) → 409."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await c.post("/api/playlists/", json={"name": "Alpha"}, headers=headers)
    assert resp.status_code == 201
    resp = await c.post("/api/playlists/", json={"name": "Beta"}, headers=headers)
    assert resp.status_code == 201
    beta_id = resp.json()["id"]

    resp = await c.put(f"/api/playlists/{beta_id}", json={"name": "ALPHA"}, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Diese Playlist gibt es schon"


# --- Folder rename (atomic reference update) -------------------------------


def _seed_folder(media_root: Path, name: str, tracks: int = 2) -> None:
    folder = media_root / name
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(tracks):
        (folder / f"track{i+1:02d}.mp3").write_bytes(b"\x00" * 64)


@pytest.mark.asyncio
async def test_rename_folder_happy(client, tmp_path: Path):
    """PUT /folders/{name} renames dir and returns new MediaFolder."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}
    media_root = tmp_path / "media"
    _seed_folder(media_root, "Hoerspiele", tracks=2)

    resp = await c.put(
        "/api/library/folders/Hoerspiele",
        json={"new_name": "Maerchen"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Maerchen"
    assert body["path"] == "Maerchen"

    assert (media_root / "Maerchen").is_dir()
    assert not (media_root / "Hoerspiele").exists()


@pytest.mark.asyncio
async def test_rename_folder_unknown(client, tmp_path: Path):
    """Nonexistent folder → 404."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await c.put(
        "/api/library/folders/nothing",
        json={"new_name": "whatever"},
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rename_folder_duplicate(client, tmp_path: Path):
    """Existing target name → 409."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}
    media_root = tmp_path / "media"
    _seed_folder(media_root, "Alpha", tracks=1)
    _seed_folder(media_root, "Beta", tracks=1)

    resp = await c.put(
        "/api/library/folders/Alpha",
        json={"new_name": "Beta"},
        headers=headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_rename_folder_invalid_name(client, tmp_path: Path):
    """Slash/backslash/empty/.. → 400."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}
    media_root = tmp_path / "media"
    _seed_folder(media_root, "Alpha", tracks=1)

    for bad in ["a/b", "a\\b", ".."]:
        resp = await c.put(
            "/api/library/folders/Alpha",
            json={"new_name": bad},
            headers=headers,
        )
        assert resp.status_code == 400, f"accepted bad name {bad!r}"

    # Empty/whitespace-only — pydantic rejects empty (422); whitespace trims to
    # empty which raises InvalidFolderName → 400.
    resp = await c.put(
        "/api/library/folders/Alpha",
        json={"new_name": ""},
        headers=headers,
    )
    assert resp.status_code == 422
    resp = await c.put(
        "/api/library/folders/Alpha",
        json={"new_name": "   "},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_rename_folder_updates_card_reference(client, tmp_path: Path):
    """cards.content_path pointing at the old name is rewritten."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}
    media_root = tmp_path / "media"
    _seed_folder(media_root, "Hoerspiele", tracks=2)

    # Create a card that points at the folder
    resp = await c.post(
        "/api/cards/",
        json={
            "card_id": "card-folder",
            "name": "Hoerspiele",
            "content_type": "folder",
            "content_path": "Hoerspiele",
        },
        headers=headers,
    )
    assert resp.status_code in (200, 201)

    # And a second card pointing at a track inside the folder
    resp = await c.post(
        "/api/cards/",
        json={
            "card_id": "card-track",
            "name": "Track",
            "content_type": "folder",
            "content_path": "Hoerspiele/track01.mp3",
        },
        headers=headers,
    )
    assert resp.status_code in (200, 201)

    # Rename
    resp = await c.put(
        "/api/library/folders/Hoerspiele",
        json={"new_name": "Maerchen"},
        headers=headers,
    )
    assert resp.status_code == 200

    # Verify both card paths were rewritten
    resp = await c.get("/api/cards/")
    assert resp.status_code == 200
    cards_by_id = {c_["card_id"]: c_ for c_ in resp.json()}
    assert cards_by_id["card-folder"]["content_path"] == "Maerchen"
    assert cards_by_id["card-track"]["content_path"] == "Maerchen/track01.mp3"


@pytest.mark.asyncio
async def test_rename_folder_updates_playlist_items(client, tmp_path: Path):
    """playlist_items.content_path pointing into the folder is rewritten."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}
    media_root = tmp_path / "media"
    _seed_folder(media_root, "Hoerspiele", tracks=2)

    # Create playlist + items
    resp = await c.post("/api/playlists/", json={"name": "Mix"}, headers=headers)
    assert resp.status_code == 201
    pid = resp.json()["id"]

    resp = await c.post(
        f"/api/playlists/{pid}/items",
        json={"content_type": "folder", "content_path": "Hoerspiele"},
        headers=headers,
    )
    assert resp.status_code in (200, 201)
    resp = await c.post(
        f"/api/playlists/{pid}/items",
        json={"content_type": "folder", "content_path": "Hoerspiele/track01.mp3"},
        headers=headers,
    )
    assert resp.status_code in (200, 201)

    # Rename
    resp = await c.put(
        "/api/library/folders/Hoerspiele",
        json={"new_name": "Maerchen"},
        headers=headers,
    )
    assert resp.status_code == 200

    # Verify playlist items rewritten
    resp = await c.get(f"/api/playlists/{pid}")
    assert resp.status_code == 200
    paths = [it["content_path"] for it in resp.json()["items"]]
    assert "Maerchen" in paths
    assert "Maerchen/track01.mp3" in paths


@pytest.mark.asyncio
async def test_rename_folder_rollback_on_sql_failure(client, tmp_path: Path, monkeypatch):
    """When the DB update raises, the filesystem rename must be rolled back."""
    from core.routers import library as lib_router

    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}
    media_root = tmp_path / "media"
    _seed_folder(media_root, "Hoerspiele", tracks=1)

    async def boom(*_args, **_kwargs):
        raise RuntimeError("simulated sql failure")

    monkeypatch.setattr(lib_router, "_update_path_references", boom)

    resp = await c.put(
        "/api/library/folders/Hoerspiele",
        json={"new_name": "Maerchen"},
        headers=headers,
    )
    assert resp.status_code == 500
    # Filesystem must still show the old folder (rollback).
    assert (media_root / "Hoerspiele").is_dir()
    assert not (media_root / "Maerchen").exists()


@pytest.mark.asyncio
async def test_rename_folder_blocked_while_playing(client, tmp_path: Path):
    """Rename is refused while the player is using content from this folder."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}
    media_root = tmp_path / "media"
    _seed_folder(media_root, "Hoerspiele", tracks=1)

    # Simulate active playback from the folder
    player = c._transport.app.state.player_service
    player._state.current_uri = "Hoerspiele/track01.mp3"

    try:
        resp = await c.put(
            "/api/library/folders/Hoerspiele",
            json={"new_name": "Maerchen"},
            headers=headers,
        )
        assert resp.status_code == 409
        assert "abgespielt" in resp.json()["detail"].lower()
        # Dir untouched
        assert (media_root / "Hoerspiele").is_dir()
        assert not (media_root / "Maerchen").exists()
    finally:
        player._state.current_uri = ""


# --- Post-review regression tests (K-1, K-3, M6 proper OOM check) ---

@pytest.mark.asyncio
async def test_system_hardware_masks_ssid_when_sealed(client):
    """K-1: /system/hardware must also drop LAN-identifying wifi fields."""
    c, auth_svc = client
    await auth_svc.set_pin(AuthTier.PARENT, "1234")
    auth_svc.set_setup_complete(True)

    resp = await c.get("/api/system/hardware")
    assert resp.status_code == 200
    wifi = resp.json().get("wifi", {})
    # Whatever the mock reports, SSID/IP must be wiped for anonymous callers
    assert wifi.get("ssid") == ""
    assert wifi.get("ip") == ""


@pytest.mark.asyncio
async def test_system_hardware_full_wifi_for_parent(client):
    """K-1: PARENT token still gets the full wifi payload."""
    c, auth_svc = client
    await auth_svc.set_pin(AuthTier.PARENT, "1234")
    auth_svc.set_setup_complete(True)
    result = await auth_svc.login("1234")
    headers = {"Authorization": f"Bearer {result['token']}"}

    resp = await c.get("/api/system/hardware", headers=headers)
    assert resp.status_code == 200
    wifi = resp.json().get("wifi", {})
    # Keys present — values depend on the mock
    assert "ssid" in wifi
    assert "ip" in wifi


@pytest.mark.asyncio
async def test_config_delete_rejects_non_whitelisted_keys(client):
    """K-3: DELETE must respect the same whitelist as PUT."""
    c, auth_svc = client
    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}

    # Non-whitelisted backend key — parent token must NOT be able to delete it
    resp = await c.delete("/api/config/audio.device", headers=headers)
    assert resp.status_code == 400
    assert "not writeable" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_config_delete_allows_whitelisted_keys(client):
    """K-3: legitimate config deletes still work."""
    c, auth_svc = client
    # Seed a whitelisted key so DELETE has something to find
    app_config = c._transport.app.state.config_service  # type: ignore[attr-defined]
    await app_config.set("player.max_volume", 80)

    token = await _get_token(auth_svc, AuthTier.PARENT)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await c.delete("/api/config/player.max_volume", headers=headers)
    assert resp.status_code == 200


def test_sanitize_filename_strips_backslashes_and_nulls() -> None:
    """W-4: both upload endpoints must use the same sanitiser."""
    from core.routers.library import _sanitize_filename

    # Windows-style path on a Linux runtime
    assert _sanitize_filename(r"C:\Users\attacker\evil.mp3") == "evil.mp3"
    # Null byte injection
    assert _sanitize_filename("clean\x00suffix.mp3") == "cleansuffix.mp3"
    # Forward-slash parent traversal
    assert _sanitize_filename("../../etc/passwd") == "passwd"
    # Harmless name passes through
    assert _sanitize_filename("Track 01.mp3") == "Track 01.mp3"
