"""Tonado Core — FastAPI entry point and service wiring."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import Response

from core.database import DatabaseManager
from core.hardware.gyro import detect_gyro
from core.hardware.rfid import detect_reader
from core.playback_dispatcher import PlaybackDispatcher
from core.hardware.gpio_buttons import (
    GpiodButtonListener,
    GpiodButtonScanner,
    MockGpioButtonListener,
    MockGpioButtonScanner,
)
from core.routers import auth, buttons, cards, config, library, player, playlists, setup, streams, system
from core.services.button_service import ButtonService
from core.services.auth_service import AuthService
from core.services.backup_service import BackupService
from core.services.captive_portal import CaptivePortalService
from core.services.card_service import CardService
from core.services.config_service import ConfigService
from core.services.event_bus import EventBus
from core.services.gyro_service import GyroService
from core.services.hardware_detector import HardwareDetector
from core.services.player_service import PlayerService
from core.services.library_service import LibraryService
from core.services.playlist_service import PlaylistService
from core.services.setup_wizard import SetupWizard
from core.services.stream_service import StreamService
from core.services.system_service import SystemService
from core.services.timer_service import TimerService
from core.services.websocket_hub import WebSocketHub
from core.services.wifi_service import WifiService
from core.services.system_service import VERSION
from core.settings import Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def _create_services(settings: Settings, event_bus: EventBus) -> dict:
    """Create and start all services, returning them as a dict.

    Services are started in dependency groups using asyncio.gather()
    to reduce startup time on slow hardware (Pi Zero W: ~30-60s → ~10-15s).

    Dependency graph:
      Group 0: DB + Config (everything depends on these)
      Group 1: HardwareDetector + PlayerService (independent, needed by Group 2)
      Group 2: CardService + GyroService + LibraryService + StreamService
               + PlaylistService + AuthService + WifiService + WebSocketHub
      Group 3: TimerService + SetupWizard (depend on Group 1+2 services)
    """
    # --- Group 0: Foundation (sequential — everything depends on DB + Config) ---
    db_manager = DatabaseManager(settings.db_path)
    await db_manager.start()
    db = db_manager.connection

    config_service = ConfigService(db, event_bus)
    await config_service.start()

    # Read runtime config from DB (overrides env defaults)
    card_cooldown = await config_service.get("card.rescan_cooldown") or settings.card_rescan_cooldown
    card_remove_pauses = await config_service.get("card.remove_pauses")
    if card_remove_pauses is None:
        card_remove_pauses = settings.card_remove_pauses
    gyro_enabled = await config_service.get("gyro.enabled")
    if gyro_enabled is None:
        gyro_enabled = settings.gyro_enabled
    gyro_sensitivity = await config_service.get("gyro.sensitivity") or settings.gyro_sensitivity

    # --- Group 1: Hardware detection + Player (independent, needed by later groups) ---
    hardware_detector = HardwareDetector()
    player_service = PlayerService(
        event_bus=event_bus,
        host=settings.mpd_host,
        port=settings.mpd_port,
    )
    await asyncio.gather(
        hardware_detector.start(),
        player_service.start(),
    )
    hw_profile = hardware_detector.profile

    # Set startup volume from config
    startup_volume = await config_service.get("player.startup_volume")
    if startup_volume is not None:
        await player_service.set_volume(startup_volume)

    # --- Group 2: Independent services (all only need DB/Config/HW profile) ---
    rfid_type = hw_profile.rfid_reader if not hw_profile.is_mock else "mock"
    rfid_reader = detect_reader(reader_type=rfid_type, device=hw_profile.rfid_device)
    reader_connected = rfid_type not in ("none", "mock")
    card_service = CardService(
        reader=rfid_reader,
        event_bus=event_bus,
        db=db,
        config_service=config_service,
        rescan_cooldown=card_cooldown,
        remove_pauses=card_remove_pauses,
        reader_connected=reader_connected,
    )

    gyro_sensor = detect_gyro(settings.hardware_mode)
    gyro_service = GyroService(
        sensor=gyro_sensor,
        event_bus=event_bus,
        config=config_service,
        sensitivity=gyro_sensitivity,
        enabled=gyro_enabled,
    )

    library_service = LibraryService(settings.media_dir)
    stream_service = StreamService(db)
    playlist_service = PlaylistService(db, media_dir=settings.media_dir)
    auth_service = AuthService(config_service)
    wifi_service = WifiService()
    ws_hub = WebSocketHub(event_bus)
    player_service.set_listener_check(lambda: ws_hub.has_connections)

    # GPIO Buttons
    if hw_profile.is_mock or not hw_profile.gpio_available:
        button_scanner = MockGpioButtonScanner()
        button_listener = MockGpioButtonListener()
    else:
        button_scanner = GpiodButtonScanner()
        button_listener = GpiodButtonListener()

    button_service = ButtonService(
        scanner=button_scanner,
        listener=button_listener,
        event_bus=event_bus,
        config_service=config_service,
    )

    # Wire event bus → player actions BEFORE starting services.
    # Card service starts scanning immediately on start(), so the
    # dispatcher must be subscribed before the scan loop begins.
    dispatcher = PlaybackDispatcher(
        event_bus=event_bus,
        player=player_service,
        card_service=card_service,
        stream_service=stream_service,
        playlist_service=playlist_service,
        timer_service=None,  # Not yet created, will be set after Group 3
    )

    # Use return_exceptions=True so a single service failure
    # doesn't prevent the remaining services from starting.
    results = await asyncio.gather(
        card_service.start(),
        gyro_service.start(),
        library_service.start(),
        stream_service.start(),
        playlist_service.start(),
        auth_service.start(),
        wifi_service.start(),
        ws_hub.start(),
        button_service.start(),
        return_exceptions=True,
    )
    _service_names = [
        "card", "gyro", "library", "stream", "playlist",
        "auth", "wifi", "websocket_hub", "button",
    ]
    for name, result in zip(_service_names, results):
        if isinstance(result, Exception):
            logger.error("Service '%s' failed to start: %s", name, result)

    # --- Group 3: Services that depend on Group 2 ---
    timer_service = TimerService(event_bus, player_service, config_service)
    dispatcher._timer_service = timer_service  # Now available for resume saves
    system_service = SystemService()
    backup_service = BackupService(db, config_service)
    captive_portal = CaptivePortalService(config_service=config_service)

    setup_wizard = SetupWizard(
        config_service=config_service,
        wifi_service=wifi_service,
        hardware_detector=hardware_detector,
        auth_service=auth_service,
    )

    await asyncio.gather(
        timer_service.start(),
        setup_wizard.start(),
    )

    # If setup not complete and on Pi, start captive portal
    if not setup_wizard.is_complete and settings.hardware_mode != "mock":
        logger.info("Setup not complete — starting captive portal")
        await captive_portal.start()

    return {
        "db_manager": db_manager,
        "hardware_detector": hardware_detector,
        "player_service": player_service,
        "card_service": card_service,
        "config_service": config_service,
        "library_service": library_service,
        "stream_service": stream_service,
        "playlist_service": playlist_service,
        "auth_service": auth_service,
        "timer_service": timer_service,
        "system_service": system_service,
        "backup_service": backup_service,
        "setup_wizard": setup_wizard,
        "wifi_service": wifi_service,
        "captive_portal": captive_portal,
        "gyro_service": gyro_service,
        "button_service": button_service,
        "ws_hub": ws_hub,
        "settings": settings,
        "_dispatcher": dispatcher,  # prevent GC
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Start and stop all services with the FastAPI app lifecycle."""
    settings = Settings()
    logger.info("Starting Tonado (hardware_mode=%s)", settings.hardware_mode)

    event_bus = EventBus()
    services = await _create_services(settings, event_bus)

    # Store all services on app.state for FastAPI dependency injection
    for key, value in services.items():
        setattr(app.state, key, value)

    logger.info("Tonado ready — listening on %s:%d", settings.host, settings.port)
    yield

    # Shutdown — stop all services in reverse startup order
    logger.info("Shutting down Tonado...")
    shutdown_order = [
        "captive_portal",
        "setup_wizard",
        "wifi_service",
        "ws_hub",
        "backup_service",
        "timer_service",
        "system_service",
        "auth_service",
        "playlist_service",
        "stream_service",
        "library_service",
        "button_service",
        "gyro_service",
        "card_service",
        "player_service",
        "hardware_detector",
        "config_service",
        "db_manager",
    ]
    for name in shutdown_order:
        svc = services.get(name)
        if svc is None:
            continue
        try:
            await svc.stop()
        except Exception:
            logger.exception("Error stopping %s", name)
    logger.info("Tonado stopped")


app = FastAPI(
    title="Tonado",
    description="Open-source kids music box API",
    version=VERSION,
    lifespan=lifespan,
)


# --- Global rate limit ---
# 100 write requests/min/IP, uploads capped at 5/min (500 MB bodies).
# Must be added before route registration so it wraps every handler.
from core.utils.rate_limit import RateLimitMiddleware  # noqa: E402

app.add_middleware(RateLimitMiddleware)


# --- HEAD support middleware ---
# StaticFiles mount at "/" causes HEAD requests to bypass API routes.
# Convert HEAD to GET so API handlers match, then strip the body.

@app.middleware("http")
async def head_method_support(request: Request, call_next) -> Response:
    if request.method == "HEAD" and request.url.path.startswith("/api/"):
        request.scope["method"] = "GET"
        response = await call_next(request)
        response.body = b""
        if hasattr(response, "content_length"):
            response.headers["content-length"] = "0"
        return response
    return await call_next(request)


# --- Security header middleware ---

@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    """Add security headers to every HTTP response."""
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' ws: wss:; media-src 'self' blob: http: https:; font-src 'self'"
    return response


# --- Global exception handler ---

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a generic error for unhandled exceptions, log the details."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Interner Serverfehler"},
    )


# Include routers
app.include_router(player.router)
app.include_router(cards.router)
app.include_router(config.router)
app.include_router(library.router)
app.include_router(streams.router)
app.include_router(playlists.router)
app.include_router(auth.router)
app.include_router(system.router)
app.include_router(setup.router)
app.include_router(buttons.router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": VERSION}


def _is_allowed_origin(origin: str | None) -> bool:
    """Check if WebSocket origin is from localhost or private LAN.

    Allows connections with no Origin header (non-browser clients).
    """
    if origin is None:
        return True
    try:
        from urllib.parse import urlparse
        parsed = urlparse(origin)
        host = parsed.hostname or ""
    except Exception:
        return False

    # Localhost
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    # Private LAN ranges
    if host.endswith(".local"):
        return True
    # 10.x.x.x, 192.168.x.x, 172.16-31.x.x
    parts = host.split(".")
    if len(parts) == 4:
        try:
            a, b = int(parts[0]), int(parts[1])
            if a == 10:
                return True
            if a == 192 and b == 168:
                return True
            if a == 172 and 16 <= b <= 31:
                return True
        except ValueError:
            pass
    return False


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    # Validate origin — reject non-LAN browser connections
    origin = ws.headers.get("origin")
    if not _is_allowed_origin(origin):
        logger.warning("WebSocket rejected: origin=%s", origin)
        await ws.close(code=1008, reason="Origin not allowed")
        return

    hub: WebSocketHub = ws.app.state.ws_hub
    await hub.connect(ws)
    try:
        while True:
            # Keep connection alive, handle incoming messages if needed
            data = await ws.receive_text()
            # Future: handle client commands via WebSocket
            logger.debug("WebSocket received: %s", data)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        await hub.disconnect(ws)


# Serve static frontend (SvelteKit build) — must be after all API routes
_build_dir = Path(__file__).resolve().parent.parent / "web" / "build"
if _build_dir.is_dir():
    _static = StaticFiles(directory=str(_build_dir), html=True)
    _index_html = _build_dir / "index.html"

    @app.middleware("http")
    async def spa_fallback(request, call_next):
        response = await call_next(request)
        # SPA fallback: return index.html for non-API 404s
        path = request.url.path
        if response.status_code == 404 and not path.startswith(("/api/", "/ws", "/_app/")):
            return FileResponse(_index_html)
        return response

    app.mount("/", _static, name="static")
