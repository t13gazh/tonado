"""System management API routes (expert area)."""

import json
import logging
import shutil
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse

from core.dependencies import require_tier
from core.utils.subprocess import async_run
from core.services.auth_service import AuthService, AuthTier
from core.services.backup_service import BackupService
from core.services.system_service import SystemService
from core.hardware.detect import detect_all

if TYPE_CHECKING:
    from core.services.card_service import CardService
    from core.services.gyro_service import GyroService
    from core.services.player_service import PlayerService
    from core.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])

_system: SystemService | None = None
_backup: BackupService | None = None
_auth: AuthService | None = None
_player: "PlayerService | None" = None
_card: "CardService | None" = None
_gyro: "GyroService | None" = None
_settings: "Settings | None" = None


def init(
    system_service: SystemService,
    backup_service: BackupService,
    auth_service: AuthService | None = None,
    *,
    player_service: "PlayerService | None" = None,
    card_service: "CardService | None" = None,
    gyro_service: "GyroService | None" = None,
    settings: "Settings | None" = None,
) -> None:
    global _system, _backup, _auth, _player, _card, _gyro, _settings
    _system = system_service
    _backup = backup_service
    _auth = auth_service
    _player = player_service
    _card = card_service
    _gyro = gyro_service
    _settings = settings


def _get_system() -> SystemService:
    if _system is None:
        raise HTTPException(503, "System service not available")
    return _system


def _get_backup() -> BackupService:
    if _backup is None:
        raise HTTPException(503, "Backup service not available")
    return _backup



async def _detect_wifi() -> dict:
    """Detect current WiFi connection status."""
    result: dict = {"connected": False, "ssid": "", "ip": ""}

    rc, stdout, _ = await async_run(
        ["nmcli", "-t", "-f", "ACTIVE,SSID,DEVICE", "connection", "show", "--active"],
        timeout=5,
    )
    if rc == 0:
        for line in stdout.strip().splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[0] == "yes":
                result["connected"] = True
                result["ssid"] = parts[1]
                break
    else:
        rc2, stdout2, _ = await async_run(["iwgetid", "-r"], timeout=5)
        if rc2 == 0 and stdout2.strip():
            result["connected"] = True
            result["ssid"] = stdout2.strip()

    rc3, stdout3, _ = await async_run(["hostname", "-I"], timeout=5)
    if rc3 == 0 and stdout3.strip():
        result["ip"] = stdout3.strip().split()[0]

    return result


# --- System info ---

@router.get("/info")
async def system_info() -> dict:
    info = await _get_system().get_info()
    return info.to_dict()


# --- Health status (hardware resilience) ---

@router.get("/health")
async def system_health() -> dict:
    """Return health status of all hardware components for UI degraded-state banners."""
    health: dict = {}

    # MPD
    if _player is not None:
        health["mpd"] = {
            "status": "connected" if _player._connected else "disconnected",
            "detail": f"{_player._host}:{_player._port}" if _player._connected else "MPD nicht erreichbar",
        }
    else:
        health["mpd"] = {"status": "disconnected", "detail": "Player-Service nicht initialisiert"}

    # RFID reader
    if _card is not None:
        from core.hardware.rfid import MockRfidReader
        reader = _card._reader
        if isinstance(reader, MockRfidReader):
            # Mock means no real hardware detected
            is_mock = _settings is not None and _settings.hardware_mode == "mock"
            if is_mock:
                health["rfid"] = {"status": "not_configured", "detail": "Entwicklungsmodus (Mock)"}
            else:
                health["rfid"] = {"status": "not_configured", "detail": "Kein Figuren-Leser erkannt"}
        else:
            reader_type = type(reader).__name__
            health["rfid"] = {"status": "connected", "detail": reader_type}
    else:
        health["rfid"] = {"status": "not_configured", "detail": "Kein Figuren-Leser erkannt"}

    # Gyro sensor
    if _gyro is not None:
        from core.hardware.gyro import MockGyroSensor
        sensor = _gyro._sensor
        if isinstance(sensor, MockGyroSensor):
            is_mock = _settings is not None and _settings.hardware_mode == "mock"
            if is_mock:
                health["gyro"] = {"status": "not_configured", "detail": "Entwicklungsmodus (Mock)"}
            elif not _gyro._enabled:
                health["gyro"] = {"status": "not_configured", "detail": "Deaktiviert"}
            else:
                health["gyro"] = {"status": "not_configured", "detail": "Kein Bewegungssensor erkannt"}
        else:
            health["gyro"] = {
                "status": "connected" if _gyro._enabled else "disconnected",
                "detail": "MPU6050" if _gyro._enabled else "Deaktiviert",
            }
    else:
        health["gyro"] = {"status": "not_configured", "detail": "Kein Bewegungssensor erkannt"}

    # Audio output — delegate to MPD outputs if available
    if _player is not None and _player._connected:
        try:
            outputs = await _player.list_outputs()
            if outputs:
                names = ", ".join(o["name"] for o in outputs if o["enabled"])
                health["audio"] = {"status": "ok", "detail": names or "Kein aktiver Ausgang"}
            else:
                health["audio"] = {"status": "no_output", "detail": "Keine Ausgänge konfiguriert"}
        except Exception:
            health["audio"] = {"status": "no_output", "detail": "Audio-Status unbekannt"}
    else:
        health["audio"] = {"status": "no_output", "detail": "MPD nicht verbunden"}

    # Storage
    try:
        usage = shutil.disk_usage("/")
        free_mb = usage.free // (1024 * 1024)
        if free_mb < 50:
            status = "critical"
        elif free_mb < 200:
            status = "low"
        else:
            status = "ok"
        health["storage"] = {
            "status": status,
            "free_mb": free_mb,
            "detail": f"{free_mb} MB frei",
        }
    except OSError:
        health["storage"] = {"status": "ok", "free_mb": 0, "detail": "Nicht verfügbar"}

    # Network
    wifi = await _detect_wifi()
    if wifi["connected"]:
        health["network"] = {
            "status": "connected",
            "detail": f"{wifi['ssid']} ({wifi['ip']})" if wifi["ip"] else wifi["ssid"],
        }
    else:
        health["network"] = {"status": "disconnected", "detail": "Nicht verbunden"}

    return health


# --- Hardware status ---

@router.get("/hardware")
async def hardware_status() -> dict:
    """Return detected hardware profile including WiFi status."""
    try:
        profile = detect_all()
        data = profile.to_dict()
        data["wifi"] = await _detect_wifi()
        return data
    except Exception as e:
        logger.error("Hardware detection failed: %s", e)
        raise HTTPException(500, "Hardware detection failed")


# --- Power ---

@router.post("/restart")
async def restart_service(request: Request) -> dict:
    require_tier(request, AuthTier.EXPERT, _auth)
    await _get_system().restart()
    return {"status": "ok"}


@router.post("/shutdown")
async def shutdown(request: Request) -> dict:
    require_tier(request, AuthTier.EXPERT, _auth)
    await _get_system().shutdown()
    return {"status": "ok"}


@router.post("/reboot")
async def reboot(request: Request) -> dict:
    require_tier(request, AuthTier.EXPERT, _auth)
    await _get_system().reboot()
    return {"status": "ok"}


# --- Updates ---

@router.get("/update/check")
async def check_update() -> dict:
    return await _get_system().check_update()


@router.post("/update/apply")
async def apply_update(request: Request) -> dict:
    require_tier(request, AuthTier.EXPERT, _auth)
    return await _get_system().apply_update()


# --- OverlayFS ---

@router.post("/overlay/enable")
async def enable_overlay(request: Request) -> dict:
    require_tier(request, AuthTier.EXPERT, _auth)
    success = await _get_system().enable_overlay()
    return {"status": "ok" if success else "error"}


@router.post("/overlay/disable")
async def disable_overlay(request: Request) -> dict:
    require_tier(request, AuthTier.EXPERT, _auth)
    success = await _get_system().disable_overlay()
    return {"status": "ok" if success else "error"}


# --- Backup/Restore ---

@router.get("/backup")
async def export_backup() -> JSONResponse:
    data = await _get_backup().export_backup()
    return JSONResponse(
        content=data,
        headers={
            "Content-Disposition": "attachment; filename=tonado-backup.json",
        },
    )


@router.post("/restore")
async def import_backup(request: Request, file: UploadFile = File(...)) -> dict:
    require_tier(request, AuthTier.EXPERT, _auth)
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(400, "Only JSON files allowed")

    try:
        content = await file.read()
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid backup file")

    if "version" not in data:
        raise HTTPException(400, "Not a valid Tonado backup")

    counts = await _get_backup().import_backup(data)
    return {"status": "ok", "imported": counts}
