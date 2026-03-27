"""Tonado Core — FastAPI entry point and service wiring."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from core.hardware.gyro import detect_gyro
from core.hardware.rfid import detect_reader
from core.routers import cards, config, library, player, setup, streams
from core.services.captive_portal import CaptivePortalService
from core.services.card_service import CardService
from core.services.config_service import ConfigService
from core.services.event_bus import EventBus
from core.services.gyro_service import GyroService
from core.services.player_service import PlayerService
from core.services.library_service import LibraryService
from core.services.setup_wizard import SetupWizard
from core.services.stream_service import StreamService
from core.services.websocket_hub import WebSocketHub
from core.services.wifi_service import WifiService
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

    # WebSocket hub
    ws_hub = WebSocketHub(event_bus)
    await ws_hub.start()

    # Wire event bus: card → player
    async def on_card_scanned(card_id: str, mapping: dict, **_) -> None:
        content_type = mapping["content_type"]
        content_path = mapping["content_path"]
        resume = mapping.get("resume_position", 0)

        if content_type == "folder":
            await player_service.play_folder(content_path, resume_position=resume)
        elif content_type in ("stream", "podcast"):
            await player_service.play_url(content_path)

    async def on_card_removed(should_pause: bool, **_) -> None:
        if should_pause:
            await player_service.pause()

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

    event_bus.subscribe("card_scanned", on_card_scanned)
    event_bus.subscribe("card_removed", on_card_removed)
    event_bus.subscribe("gesture_detected", on_gesture)

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
    setup.init(setup_wizard, wifi_service, captive_portal)

    # Store hub on app state for WebSocket endpoint
    app.state.ws_hub = ws_hub

    logger.info("Tonado ready — listening on %s:%d", settings.host, settings.port)
    yield

    # Shutdown
    logger.info("Shutting down Tonado...")
    if captive_portal.active:
        await captive_portal.stop()
    await gyro_service.stop()
    await card_service.stop()
    await player_service.stop()
    await config_service.stop()
    await db.close()
    logger.info("Tonado stopped")


app = FastAPI(
    title="Tonado",
    description="Open-source kids music box API",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(player.router)
app.include_router(cards.router)
app.include_router(config.router)
app.include_router(library.router)
app.include_router(streams.router)
app.include_router(setup.router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


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
