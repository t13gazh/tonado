"""Library and upload API routes."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from core.services.library_service import LibraryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/library", tags=["library"])

_library: LibraryService | None = None


def init(library_service: LibraryService) -> None:
    global _library
    _library = library_service


def _get_service() -> LibraryService:
    if _library is None:
        raise HTTPException(503, "Library service not available")
    return _library


@router.get("/folders")
async def list_folders() -> list[dict]:
    return [f.to_dict() for f in _get_service().list_folders()]


@router.get("/folders/{folder_name}")
async def get_folder(folder_name: str) -> dict:
    folder = _get_service().get_folder(folder_name)
    if folder is None:
        raise HTTPException(404, "Ordner nicht gefunden")
    return folder.to_dict()


@router.get("/folders/{folder_name}/tracks")
async def list_tracks(folder_name: str) -> list[dict]:
    tracks = _get_service().list_tracks(folder_name)
    if not tracks and _get_service().get_folder(folder_name) is None:
        raise HTTPException(404, "Ordner nicht gefunden")
    return [t.to_dict() for t in tracks]


@router.get("/{folder_name}/cover")
async def get_cover(folder_name: str) -> FileResponse:
    cover_path = _get_service().get_cover_path(folder_name)
    if cover_path is None:
        raise HTTPException(404, "Kein Cover vorhanden")
    return FileResponse(cover_path)


@router.post("/folders")
async def create_folder(name: str = Form(...)) -> dict:
    # Sanitize folder name
    safe_name = name.strip().replace("/", "_").replace("\\", "_")
    if not safe_name:
        raise HTTPException(400, "Ungültiger Ordnername")
    folder = _get_service().create_folder(safe_name)
    return folder.to_dict()


@router.delete("/folders/{folder_name}")
async def delete_folder(folder_name: str) -> dict:
    if not _get_service().delete_folder(folder_name):
        raise HTTPException(404, "Ordner nicht gefunden")
    return {"status": "ok"}


@router.put("/folders/{folder_name}/rename")
async def rename_folder(folder_name: str, new_name: str = Form(...)) -> dict:
    safe_name = new_name.strip().replace("/", "_").replace("\\", "_")
    if not safe_name:
        raise HTTPException(400, "Ungültiger Ordnername")
    if not _get_service().rename_folder(folder_name, safe_name):
        raise HTTPException(400, "Umbenennung fehlgeschlagen")
    return {"status": "ok", "new_name": safe_name}


@router.post("/upload/{folder_name}")
async def upload_file(
    folder_name: str,
    file: UploadFile = File(...),
) -> dict:
    """Upload a file to a media folder.

    Supports audio files and cover images.
    For large files, the frontend should use chunked upload.
    """
    if not file.filename:
        raise HTTPException(400, "Kein Dateiname")

    # Basic filename sanitization
    safe_filename = file.filename.replace("/", "_").replace("\\", "_")
    suffix = Path(safe_filename).suffix.lower()

    # Validate file type
    allowed = {".mp3", ".ogg", ".flac", ".wav", ".m4a", ".aac", ".opus",
               ".jpg", ".jpeg", ".png", ".webp"}
    if suffix not in allowed:
        raise HTTPException(400, f"Dateityp nicht erlaubt: {suffix}")

    target = _get_service().get_upload_path(folder_name, safe_filename)

    # Stream file to disk
    try:
        with open(target, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1 MB chunks
                f.write(chunk)
    except Exception as e:
        logger.error("Upload failed: %s", e)
        raise HTTPException(500, "Upload fehlgeschlagen")

    size = target.stat().st_size
    logger.info("Uploaded %s to %s (%d bytes)", safe_filename, folder_name, size)

    return {
        "status": "ok",
        "filename": safe_filename,
        "folder": folder_name,
        "size_bytes": size,
    }


@router.post("/upload/{folder_name}/cover")
async def upload_cover(
    folder_name: str,
    file: UploadFile = File(...),
) -> dict:
    """Upload or replace cover art for a folder."""
    if not file.filename:
        raise HTTPException(400, "Kein Dateiname")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "Nur Bilder erlaubt (jpg, png, webp)")

    # Always save as cover.{ext}
    target = _get_service().get_upload_path(folder_name, f"cover{suffix}")

    try:
        with open(target, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
    except Exception as e:
        logger.error("Cover upload failed: %s", e)
        raise HTTPException(500, "Upload fehlgeschlagen")

    return {"status": "ok", "cover_path": f"/api/library/{folder_name}/cover"}


@router.get("/stats")
async def library_stats() -> dict:
    return _get_service().disk_usage()
