"""Tonado Core — FastAPI entry point and service wiring."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.database import DatabaseManager
from core.hardware.gyro import detect_gyro
from core.hardware.rfid import detect_reader
from core.playback_dispatcher import PlaybackDispatcher
from core.routers import auth, cards, config, library, player, playlists, setup, streams, system
from core.services.auth_service import AuthService
from core.services.backup_service import BackupService
from core.services.captive_portal import CaptivePortalService
from core.services.card_service import CardService
from core.services.config_service import ConfigService
from core.services.event_bus import EventBus
from core.services.gyro_service import GyroService
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
    """Create and start all services, returning them as a dict."""
    # Database — single connection for all services
    db_manager = DatabaseManager(settings.db_path)
    await db_manager.start()
    db = db_manager.connection

    # Config service
    config_service = ConfigService(db)
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

    # Player service
    player_service = PlayerService(
        event_bus=event_bus,
        host=settings.mpd_host,
        port=settings.mpd_port,
    )
    await player_service.start()

    # Set startup volume from config
    startup_volume = await config_service.get("player.startup_volume")
    if startup_volume is not None:
        await player_service.set_volume(startup_volume)

    # Card service
    rfid_reader = detect_reader(settings.hardware_mode)
    card_service = CardService(
        reader=rfid_reader,
        event_bus=event_bus,
        db=db,
        config_service=config_service,
        rescan_cooldown=card_cooldown,
        remove_pauses=card_remove_pauses,
    )
    await card_service.start()

    # Gyro service
    gyro_sensor = detect_gyro(settings.hardware_mode)
    gyro_service = GyroService(
        sensor=gyro_sensor,
        event_bus=event_bus,
        sensitivity=gyro_sensitivity,
        enabled=gyro_enabled,
    )
    await gyro_service.start()

    # Library service
    library_service = LibraryService(settings.media_dir)
    await library_service.start()

    # Stream service
    stream_service = StreamService(db)
    await stream_service.start()

    # Playlist service
    playlist_service = PlaylistService(db, media_dir=settings.media_dir)
    await playlist_service.start()

    # Auth service
    auth_service = AuthService(config_service)
    await auth_service.start()

    # Timer service (sleep timer, idle shutdown, volume enforcement, resume)
    timer_service = TimerService(event_bus, player_service, config_service)
    await timer_service.start()

    # System + Backup services
    system_service = SystemService()
    backup_service = BackupService(db, config_service)

    # WebSocket hub
    ws_hub = WebSocketHub(event_bus)
    await ws_hub.start()

    # WiFi + Setup wizard + Captive portal
    wifi_service = WifiService()
    await wifi_service.start()

    captive_portal = CaptivePortalService()

    setup_wizard = SetupWizard(
        config_service=config_service,
        wifi_service=wifi_service,
    )
    await setup_wizard.start()

    # If setup not complete and on Pi, start captive portal
    if not setup_wizard.is_complete and settings.hardware_mode != "mock":
        logger.info("Setup not complete — starting captive portal")
        await captive_portal.start()

    return {
        "db_manager": db_manager,
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
        "ws_hub": ws_hub,
        "settings": settings,
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Start and stop all services with the FastAPI app lifecycle."""
    settings = Settings()
    logger.info("Starting Tonado (hardware_mode=%s)", settings.hardware_mode)

    event_bus = EventBus()
    services = await _create_services(settings, event_bus)

    # Wire event bus → player actions
    _dispatcher = PlaybackDispatcher(  # noqa: F841 — prevent GC
        event_bus=event_bus,
        player=services["player_service"],
        card_service=services["card_service"],
        stream_service=services["stream_service"],
        playlist_service=services["playlist_service"],
        timer_service=services["timer_service"],
    )

    # Store all services on app.state for FastAPI dependency injection
    for key, value in services.items():
        setattr(app.state, key, value)

    logger.info("Tonado ready — listening on %s:%d", settings.host, settings.port)
    yield

    # Shutdown
    logger.info("Shutting down Tonado...")
    if services["captive_portal"].active:
        await services["captive_portal"].stop()
    await services["timer_service"].stop()
    await services["gyro_service"].stop()
    await services["card_service"].stop()
    await services["player_service"].stop()
    await services["config_service"].stop()
    await services["db_manager"].stop()
    logger.info("Tonado stopped")


app = FastAPI(
    title="Tonado",
    description="Open-source kids music box API",
    version=VERSION,
    lifespan=lifespan,
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


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": VERSION}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    hub: WebSocketHub = ws.app.state.ws_hub
    await hub.connect(ws)
    try:
        while True:
            # Keep connection alive, handle incoming messages if needed
            data = await ws.receive_text()
            # Future: handle client commands via WebSocket
            logger.debug("WebSocket received: %s", data)
    except WebSocketDisconnect:
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
        if response.status_code == 404 and not path.startswith(("/api/", "/ws")):
            return FileResponse(_index_html)
        return response

    app.mount("/", _static, name="static")
