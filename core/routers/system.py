"""System management API routes (expert area)."""

import json
import logging
import subprocess

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse

from core.services.auth_service import AuthService, AuthTier
from core.services.backup_service import BackupService
from core.services.system_service import SystemService
from core.hardware.detect import detect_all

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])

_system: SystemService | None = None
_backup: BackupService | None = None
_auth: AuthService | None = None


def init(
    system_service: SystemService,
    backup_service: BackupService,
    auth_service: AuthService | None = None,
) -> None:
    global _system, _backup, _auth
    _system = system_service
    _backup = backup_service
    _auth = auth_service


def _get_system() -> SystemService:
    if _system is None:
        raise HTTPException(503, "System service not available")
    return _system


def _get_backup() -> BackupService:
    if _backup is None:
        raise HTTPException(503, "Backup service not available")
    return _backup


def _get_token(request: Request) -> str | None:
    """Extract JWT token from Authorization header."""
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


def _require_tier(request: Request, tier: AuthTier) -> None:
    """Raise 403 if token doesn't grant access to the required tier."""
    if _auth is None:
        return  # Auth service not initialized — allow (e.g. during setup)
    token = _get_token(request)
    if not _auth.check_access(token, tier):
        raise HTTPException(403, "Zugriff verweigert")


def _detect_wifi() -> dict:
    """Detect current WiFi connection status."""
    result: dict = {"connected": False, "ssid": "", "ip": ""}
    try:
        out = subprocess.run(
            ["nmcli", "-t", "-f", "ACTIVE,SSID,DEVICE", "connection", "show", "--active"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            for line in out.stdout.strip().splitlines():
                parts = line.split(":")
                if len(parts) >= 2 and parts[0] == "yes":
                    result["connected"] = True
                    result["ssid"] = parts[1]
                    break
    except (FileNotFoundError, subprocess.TimeoutExpired):
        try:
            out = subprocess.run(
                ["iwgetid", "-r"], capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0 and out.stdout.strip():
                result["connected"] = True
                result["ssid"] = out.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    try:
        out = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            result["ip"] = out.stdout.strip().split()[0]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return result


# --- System info ---

@router.get("/info")
async def system_info() -> dict:
    info = await _get_system().get_info()
    return info.to_dict()


# --- Hardware status ---

@router.get("/hardware")
async def hardware_status() -> dict:
    """Return detected hardware profile including WiFi status."""
    try:
        profile = detect_all()
        data = profile.to_dict()
        data["wifi"] = _detect_wifi()
        return data
    except Exception as e:
        logger.error("Hardware detection failed: %s", e)
        raise HTTPException(500, "Hardware-Erkennung fehlgeschlagen")


# --- Power ---

@router.post("/restart")
async def restart_service(request: Request) -> dict:
    _require_tier(request, AuthTier.EXPERT)
    await _get_system().restart()
    return {"status": "ok"}


@router.post("/shutdown")
async def shutdown(request: Request) -> dict:
    _require_tier(request, AuthTier.EXPERT)
    await _get_system().shutdown()
    return {"status": "ok"}


@router.post("/reboot")
async def reboot(request: Request) -> dict:
    _require_tier(request, AuthTier.EXPERT)
    await _get_system().reboot()
    return {"status": "ok"}


# --- Updates ---

@router.get("/update/check")
async def check_update() -> dict:
    return await _get_system().check_update()


@router.post("/update/apply")
async def apply_update(request: Request) -> dict:
    _require_tier(request, AuthTier.EXPERT)
    return await _get_system().apply_update()


# --- OverlayFS ---

@router.post("/overlay/enable")
async def enable_overlay(request: Request) -> dict:
    _require_tier(request, AuthTier.EXPERT)
    success = await _get_system().enable_overlay()
    return {"status": "ok" if success else "error"}


@router.post("/overlay/disable")
async def disable_overlay(request: Request) -> dict:
    _require_tier(request, AuthTier.EXPERT)
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
    _require_tier(request, AuthTier.EXPERT)
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(400, "Nur JSON-Dateien erlaubt")

    try:
        content = await file.read()
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Ungültige Backup-Datei")

    if "version" not in data:
        raise HTTPException(400, "Kein gültiges Tonado-Backup")

    counts = await _get_backup().import_backup(data)
    return {"status": "ok", "imported": counts}
