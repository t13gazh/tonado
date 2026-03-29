"""Tonado Core — FastAPI entry point and service wiring."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from pathlib import Path

import aiosqlite
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.hardware.gyro import detect_gyro
from core.hardware.rfid import detect_reader
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Start and stop all services with the FastAPI app lifecycle."""
    settings = Settings()
    logger.info("Starting Tonado (hardware_mode=%s)", settings.hardware_mode)

    # Core infrastructure
    event_bus = EventBus()

    # Config service
    config_service = ConfigService(settings.db_path)
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
    db = await aiosqlite.connect(str(settings.db_path))
    await db.execute("PRAGMA journal_mode=WAL")
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

    # Wire event bus: card → player
    async def on_card_scanned(card_id: str, mapping: dict, **_) -> None:
        nonlocal _current_card_id
        # Save resume position of previous card
        if _current_card_id and _current_card_id != card_id:
            await timer_service.save_resume_position(_current_card_id)
        _current_card_id = card_id

        content_type = mapping["content_type"]
        content_path = mapping["content_path"]
        resume = mapping.get("resume_position", 0)

        if content_type == "folder":
            await player_service.play_folder(content_path, resume_position=resume)
        elif content_type == "stream":
            await player_service.play_url(content_path)
        elif content_type == "podcast":
            if content_path.startswith("podcast:"):
                try:
                    podcast_id = int(content_path.split(":")[1])
                    episodes = await stream_service.list_episodes(podcast_id)
                    if episodes:
                        urls = [ep.audio_url for ep in episodes]
                        await player_service.play_urls(urls, resume_position=resume)
                except (ValueError, IndexError):
                    logger.warning("Invalid podcast path: %s", content_path)
            else:
                await player_service.play_url(content_path)
        elif content_type == "playlist":
            try:
                pl_id = int(content_path.split(":")[-1])
                playlist = await playlist_service.get_playlist(pl_id)
                if playlist and playlist.items:
                    urls = [item.content_path for item in playlist.items]
                    await player_service.play_urls(urls, resume_position=resume)
            except (ValueError, IndexError):
                logger.warning("Invalid playlist path: %s", content_path)
        elif content_type == "command":
            await _execute_command(content_path)

    async def _execute_command(cmd: str) -> None:
        """Execute a box-control command triggered by a card."""
        if cmd == "sleep_timer":
            await timer_service.start_sleep_timer(30)
        elif cmd.startswith("volume:"):
            try:
                vol = int(cmd.split(":")[1])
                await player_service.set_volume(vol)
            except (ValueError, IndexError):
                pass
        elif cmd == "shuffle":
            await player_service.toggle_random()
        elif cmd == "next":
            await player_service.next_track()
        elif cmd == "previous":
            await player_service.previous_track()
        elif cmd == "pause":
            await player_service.pause()
        elif cmd == "play":
            await player_service.play()
        else:
            logger.warning("Unknown command: %s", cmd)

    # Track current card for resume position
    _current_card_id: str | None = None

    async def on_card_removed(card_id: str | None = None, should_pause: bool = False, **_) -> None:
        nonlocal _current_card_id
        # Save resume position directly (not via event bus — avoids race condition)
        if _current_card_id:
            elapsed = await player_service.get_elapsed()
            if elapsed > 0:
                await card_service.update_resume_position(_current_card_id, elapsed)
        if should_pause:
            await player_service.pause()
        _current_card_id = None

    async def on_gesture(action: str, **_) -> None:
        match action:
            case "next_track":
                await player_service.next_track()
            case "previous_track":
                await player_service.previous_track()
            case "volume_up":
                await player_service.adjust_volume(5)
            case "volume_down":
                await player_service.adjust_volume(-5)
            case "shuffle":
                await player_service.shuffle()

    async def on_resume_save(card_id: str, position: float, **_) -> None:
        await card_service.update_resume_position(card_id, position)

    event_bus.subscribe("card_scanned", on_card_scanned)
    event_bus.subscribe("card_removed", on_card_removed)
    event_bus.subscribe("gesture_detected", on_gesture)
    event_bus.subscribe("resume_position_save", on_resume_save)

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
    if not setup_wizard.is_complete and not settings.hardware_mode == "mock":
        logger.info("Setup not complete — starting captive portal")
        await captive_portal.start()

    # Initialize routers with service instances
    player.init(player_service)
    cards.init(card_service)
    config.init(config_service)
    library.init(library_service)
    streams.init(stream_service)
    playlists.init(playlist_service, player_service)
    auth.init(auth_service, timer_service)
    system.init(
        system_service, backup_service, auth_service,
        player_service=player_service,
        card_service=card_service,
        gyro_service=gyro_service,
        settings=settings,
    )
    setup.init(setup_wizard, wifi_service, captive_portal, auth_service)

    # Store hub on app state for WebSocket endpoint
    app.state.ws_hub = ws_hub

    logger.info("Tonado ready — listening on %s:%d", settings.host, settings.port)
    yield

    # Shutdown
    logger.info("Shutting down Tonado...")
    if captive_portal.active:
        await captive_portal.stop()
    await timer_service.stop()
    await gyro_service.stop()
    await card_service.stop()
    await player_service.stop()
    await config_service.stop()
    await db.close()
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
