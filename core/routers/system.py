"""System management API routes (expert area)."""

import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse

from core.dependencies import (
    get_auth_service,
    get_backup_service,
    get_button_service,
    get_card_service,
    get_gyro_service,
    get_hardware_detector,
    get_player,
    get_system_service,
    get_wifi_service,
    require_tier,
)
from core.services.auth_service import AuthService, AuthTier
from core.services.backup_service import BackupService
from core.services.button_service import ButtonService
from core.services.card_service import CardService
from core.services.gyro_service import GyroService
from core.services.hardware_detector import HardwareDetector
from core.services.player_service import PlayerService
from core.services.system_service import SystemService
from core.services.wifi_service import WifiService
from core.utils.subprocess import async_run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])


async def _wifi_status_dict(wifi: WifiService) -> dict:
    """Get WiFi status via WifiService (handles nmcli/wpa_cli/mock fallback)."""
    status = await wifi.status()
    ip = status.ip_address
    if not ip:
        # Fallback: hostname -I works on all Pi setups
        rc, stdout, _ = await async_run(["hostname", "-I"], timeout=5)
        if rc == 0 and stdout.strip():
            ip = stdout.strip().split()[0]
    return {"connected": status.connected, "ssid": status.ssid, "ip": ip}


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
    buttons: ButtonService = Depends(get_button_service),
    wifi: WifiService = Depends(get_wifi_service),
) -> dict:
    """Return health status of all hardware components for UI degraded-state banners."""
    health: dict = {}

    # MPD / Player
    mpd_health = player.health()
    health["mpd"] = mpd_health

    # RFID reader
    health["rfid"] = card.health()

    # Gyro sensor
    health["gyro"] = gyro.health()

    # Audio output — delegate to MPD outputs if available
    if mpd_health["status"] == "connected":
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
        # MPD offline — check ALSA hardware directly
        try:
            cards_path = Path("/proc/asound/cards")
            if cards_path.exists():
                content = cards_path.read_text()
                if content.strip() and "no soundcards" not in content.lower():
                    health["audio"] = {"status": "ok", "detail": "Audio-Hardware verfügbar (Musikserver offline)"}
                else:
                    health["audio"] = {"status": "no_output", "detail": "Keine Audio-Hardware gefunden"}
            else:
                health["audio"] = {"status": "unknown", "detail": "Audio-Status unbekannt"}
        except Exception:
            health["audio"] = {"status": "unknown", "detail": "Audio-Status unbekannt"}

    # GPIO Buttons
    health["buttons"] = buttons.health()

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
    wifi_info = await _wifi_status_dict(wifi)
    if wifi_info["connected"]:
        health["network"] = {
            "status": "connected",
            "detail": f"{wifi_info['ssid']} ({wifi_info['ip']})" if wifi_info["ip"] else wifi_info["ssid"],
        }
    else:
        health["network"] = {"status": "disconnected", "detail": "Nicht verbunden"}

    return health


# --- Hardware status ---

@router.get("/hardware")
async def hardware_status(
    detector: HardwareDetector = Depends(get_hardware_detector),
    wifi: WifiService = Depends(get_wifi_service),
) -> dict:
    """Return cached hardware profile including WiFi status."""
    data = detector.profile.to_dict()
    data["wifi"] = await _wifi_status_dict(wifi)
    return data


@router.post("/hardware/redetect")
async def hardware_redetect(
    request: Request,
    detector: HardwareDetector = Depends(get_hardware_detector),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    """Re-run hardware detection (expert only)."""
    require_tier(request, AuthTier.EXPERT, auth)
    try:
        profile = await detector.redetect(skip_rfid=True)
        return profile.to_dict()
    except Exception as e:
        logger.error("Hardware re-detection failed: %s", e)
        raise HTTPException(500, "Hardware re-detection failed")


# --- Power ---

@router.post("/restart")
async def restart_service(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    svc: SystemService = Depends(get_system_service),
) -> dict:
    require_tier(request, AuthTier.EXPERT, auth)
    try:
        await svc.restart()
    except RuntimeError:
        logger.exception("System restart failed")
        raise HTTPException(500, "Neustart fehlgeschlagen")
    return {"status": "ok"}


@router.post("/shutdown")
async def shutdown(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    svc: SystemService = Depends(get_system_service),
) -> dict:
    require_tier(request, AuthTier.EXPERT, auth)
    try:
        await svc.shutdown()
    except RuntimeError:
        logger.exception("System shutdown failed")
        raise HTTPException(500, "Ausschalten fehlgeschlagen")
    return {"status": "ok"}


@router.post("/reboot")
async def reboot(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    svc: SystemService = Depends(get_system_service),
) -> dict:
    require_tier(request, AuthTier.EXPERT, auth)
    try:
        await svc.reboot()
    except RuntimeError:
        logger.exception("System reboot failed")
        raise HTTPException(500, "Reboot fehlgeschlagen")
    return {"status": "ok"}


# --- Gyro Calibration ---

@router.get("/gyro/raw")
async def gyro_raw(gyro: GyroService = Depends(get_gyro_service)) -> dict:
    """Read current accelerometer values (bias-corrected)."""
    accel = await gyro.read_raw()
    mapped = await gyro.read_mapped()
    return {
        "raw": {"x": round(accel.x, 3), "y": round(accel.y, 3), "z": round(accel.z, 3)},
        "mapped": {"x": round(mapped.x, 3), "y": round(mapped.y, 3), "z": round(mapped.z, 3)},
        "calibrated": gyro.calibrated,
        "axis_map": gyro.axis_map.to_dict(),
        "gesture": gyro.last_gesture,
    }


@router.post("/gyro/calibrate/start")
async def gyro_calibrate_start(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    gyro: GyroService = Depends(get_gyro_service),
) -> dict:
    require_tier(request, AuthTier.PARENT, auth)
    await gyro.calibrate_start()
    return {"status": "ok"}


@router.post("/gyro/calibrate/rest")
async def gyro_calibrate_rest(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    gyro: GyroService = Depends(get_gyro_service),
) -> dict:
    require_tier(request, AuthTier.PARENT, auth)
    try:
        result = await gyro.calibrate_collect_rest()
        return {"status": "ok", **result}
    except Exception:
        logger.exception("Gyro calibrate rest failed")
        raise HTTPException(400, "Kalibrierung (Ruhelage) fehlgeschlagen")


@router.post("/gyro/calibrate/tilt")
async def gyro_calibrate_tilt(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    gyro: GyroService = Depends(get_gyro_service),
) -> dict:
    require_tier(request, AuthTier.PARENT, auth)
    try:
        result = await gyro.calibrate_collect_tilt()
        return {"status": "ok", **result}
    except Exception:
        logger.exception("Gyro calibrate tilt failed")
        raise HTTPException(400, "Kalibrierung (Kippen) fehlgeschlagen")


@router.post("/gyro/calibrate/save")
async def gyro_calibrate_save(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    gyro: GyroService = Depends(get_gyro_service),
) -> dict:
    require_tier(request, AuthTier.PARENT, auth)
    try:
        result = await gyro.calibrate_save()
        return {"status": "ok", **result}
    except Exception:
        logger.exception("Gyro calibrate save failed")
        raise HTTPException(400, "Kalibrierung konnte nicht gespeichert werden")


@router.post("/gyro/flip-forward")
async def gyro_flip_forward(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    gyro: GyroService = Depends(get_gyro_service),
) -> dict:
    require_tier(request, AuthTier.PARENT, auth)
    axis_map = await gyro.flip_forward()
    return {"status": "ok", "axis_map": axis_map}


@router.post("/gyro/calibrate/cancel")
async def gyro_calibrate_cancel(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    gyro: GyroService = Depends(get_gyro_service),
) -> dict:
    require_tier(request, AuthTier.PARENT, auth)
    await gyro.calibrate_cancel()
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
async def export_backup(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    svc: BackupService = Depends(get_backup_service),
) -> JSONResponse:
    require_tier(request, AuthTier.PARENT, auth)
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

    try:
        counts = await svc.import_backup(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "ok", "imported": counts}
