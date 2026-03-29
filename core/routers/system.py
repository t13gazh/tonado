"""System management API routes (expert area)."""

import json
import logging
import shutil

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse

from core.dependencies import (
    get_auth_service,
    get_backup_service,
    get_card_service,
    get_gyro_service,
    get_player,
    get_system_service,
    require_tier,
)
from core.utils.subprocess import async_run
from core.services.auth_service import AuthService, AuthTier
from core.services.backup_service import BackupService
from core.services.card_service import CardService
from core.services.gyro_service import GyroService
from core.services.player_service import PlayerService
from core.services.system_service import SystemService
from core.hardware.detect import detect_all

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])


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
async def system_info(svc: SystemService = Depends(get_system_service)) -> dict:
    info = await svc.get_info()
    return info.to_dict()


# --- Health status (hardware resilience) ---

@router.get("/health")
async def system_health(
    player: PlayerService = Depends(get_player),
    card: CardService = Depends(get_card_service),
    gyro: GyroService = Depends(get_gyro_service),
) -> dict:
    """Return health status of all hardware components for UI degraded-state banners."""
    health: dict = {}

    # MPD / Player
    health["mpd"] = player.health()

    # RFID reader
    health["rfid"] = card.health()

    # Gyro sensor
    health["gyro"] = gyro.health()

    # Audio output — delegate to MPD outputs if available
    if player.health()["status"] == "connected":
        try:
            outputs = await player.list_outputs()
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
async def restart_service(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    svc: SystemService = Depends(get_system_service),
) -> dict:
    require_tier(request, AuthTier.EXPERT, auth)
    await svc.restart()
    return {"status": "ok"}


@router.post("/shutdown")
async def shutdown(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    svc: SystemService = Depends(get_system_service),
) -> dict:
    require_tier(request, AuthTier.EXPERT, auth)
    await svc.shutdown()
    return {"status": "ok"}


@router.post("/reboot")
async def reboot(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    svc: SystemService = Depends(get_system_service),
) -> dict:
    require_tier(request, AuthTier.EXPERT, auth)
    await svc.reboot()
    return {"status": "ok"}


# --- Updates ---

@router.get("/update/check")
async def check_update(svc: SystemService = Depends(get_system_service)) -> dict:
    return await svc.check_update()


@router.post("/update/apply")
async def apply_update(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    svc: SystemService = Depends(get_system_service),
) -> dict:
    require_tier(request, AuthTier.EXPERT, auth)
    return await svc.apply_update()


# --- OverlayFS ---

@router.post("/overlay/enable")
async def enable_overlay(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    svc: SystemService = Depends(get_system_service),
) -> dict:
    require_tier(request, AuthTier.EXPERT, auth)
    success = await svc.enable_overlay()
    return {"status": "ok" if success else "error"}


@router.post("/overlay/disable")
async def disable_overlay(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    svc: SystemService = Depends(get_system_service),
) -> dict:
    require_tier(request, AuthTier.EXPERT, auth)
    success = await svc.disable_overlay()
    return {"status": "ok" if success else "error"}


# --- Backup/Restore ---

@router.get("/backup")
async def export_backup(svc: BackupService = Depends(get_backup_service)) -> JSONResponse:
    data = await svc.export_backup()
    return JSONResponse(
        content=data,
        headers={
            "Content-Disposition": "attachment; filename=tonado-backup.json",
        },
    )


@router.post("/restore")
async def import_backup(
    request: Request,
    file: UploadFile = File(...),
    auth: AuthService = Depends(get_auth_service),
    svc: BackupService = Depends(get_backup_service),
) -> dict:
    require_tier(request, AuthTier.EXPERT, auth)
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(400, "Only JSON files allowed")

    try:
        content = await file.read()
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid backup file")

    if "version" not in data:
        raise HTTPException(400, "Not a valid Tonado backup")

    counts = await svc.import_backup(data)
    return {"status": "ok", "imported": counts}
