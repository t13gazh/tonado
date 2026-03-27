"""System management API routes (expert area)."""

import json

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from core.services.backup_service import BackupService
from core.services.system_service import SystemService

router = APIRouter(prefix="/api/system", tags=["system"])

_system: SystemService | None = None
_backup: BackupService | None = None


def init(system_service: SystemService, backup_service: BackupService) -> None:
    global _system, _backup
    _system = system_service
    _backup = backup_service


def _get_system() -> SystemService:
    if _system is None:
        raise HTTPException(503, "System service not available")
    return _system


def _get_backup() -> BackupService:
    if _backup is None:
        raise HTTPException(503, "Backup service not available")
    return _backup


# --- System info ---

@router.get("/info")
async def system_info() -> dict:
    info = await _get_system().get_info()
    return info.to_dict()


# --- Power ---

@router.post("/restart")
async def restart_service() -> dict:
    await _get_system().restart()
    return {"status": "ok"}


@router.post("/shutdown")
async def shutdown() -> dict:
    await _get_system().shutdown()
    return {"status": "ok"}


@router.post("/reboot")
async def reboot() -> dict:
    await _get_system().reboot()
    return {"status": "ok"}


# --- Updates ---

@router.get("/update/check")
async def check_update() -> dict:
    return await _get_system().check_update()


@router.post("/update/apply")
async def apply_update() -> dict:
    return await _get_system().apply_update()


# --- OverlayFS ---

@router.post("/overlay/enable")
async def enable_overlay() -> dict:
    success = await _get_system().enable_overlay()
    return {"status": "ok" if success else "error"}


@router.post("/overlay/disable")
async def disable_overlay() -> dict:
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
async def import_backup(file: UploadFile = File(...)) -> dict:
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
