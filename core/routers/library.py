"""Library and upload API routes."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from core.dependencies import get_library_service
from core.services.library_service import LibraryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/library", tags=["library"])

# Maximum upload size per file in bytes (500 MB default)
MAX_UPLOAD_BYTES = 500 * 1024 * 1024


def _safe_path(folder_name: str, svc: LibraryService) -> str:
    """Validate folder_name against path traversal attacks.

    Raises HTTPException 400 if the name contains '..' or resolves outside media_dir.
    Returns the sanitized folder name.
    """
    # Reject any path component that is ".."
    if ".." in Path(folder_name).parts:
        raise HTTPException(400, "Invalid folder name")

    # Resolve and verify the path stays within media_dir
    resolved = (svc._media_dir / folder_name).resolve()
    media_resolved = svc._media_dir.resolve()
    if not str(resolved).startswith(str(media_resolved)):
        raise HTTPException(400, "Invalid folder name")

    return folder_name


@router.get("/folders")
async def list_folders(svc: LibraryService = Depends(get_library_service)) -> list[dict]:
    return [f.to_dict() for f in svc.list_folders()]


@router.get("/folders/{folder_name}")
async def get_folder(folder_name: str, svc: LibraryService = Depends(get_library_service)) -> dict:
    _safe_path(folder_name, svc)
    folder = svc.get_folder(folder_name)
    if folder is None:
        raise HTTPException(404, "Folder not found")
    return folder.to_dict()


@router.get("/folders/{folder_name}/tracks")
async def list_tracks(folder_name: str, svc: LibraryService = Depends(get_library_service)) -> list[dict]:
    _safe_path(folder_name, svc)
    tracks = svc.list_tracks(folder_name)
    if not tracks and svc.get_folder(folder_name) is None:
        raise HTTPException(404, "Folder not found")
    return [t.to_dict() for t in tracks]


@router.get("/{folder_name}/cover")
async def get_cover(folder_name: str, svc: LibraryService = Depends(get_library_service)) -> FileResponse:
    _safe_path(folder_name, svc)
    cover_path = svc.get_cover_path(folder_name)
    if cover_path is None:
        raise HTTPException(404, "No cover available")
    return FileResponse(cover_path)


@router.post("/folders")
async def create_folder(name: str = Form(...), svc: LibraryService = Depends(get_library_service)) -> dict:
    # Sanitize folder name
    safe_name = name.strip().replace("/", "_").replace("\\", "_")
    if not safe_name:
        raise HTTPException(400, "Invalid folder name")
    folder = svc.create_folder(safe_name)
    return folder.to_dict()


@router.delete("/folders/{folder_name}")
async def delete_folder(folder_name: str, svc: LibraryService = Depends(get_library_service)) -> dict:
    _safe_path(folder_name, svc)
    if not svc.delete_folder(folder_name):
        raise HTTPException(404, "Folder not found")
    return {"status": "ok"}


@router.put("/folders/{folder_name}/rename")
async def rename_folder(
    folder_name: str,
    new_name: str = Form(...),
    svc: LibraryService = Depends(get_library_service),
) -> dict:
    _safe_path(folder_name, svc)
    safe_name = new_name.strip().replace("/", "_").replace("\\", "_")
    if not safe_name:
        raise HTTPException(400, "Invalid folder name")
    _safe_path(safe_name, svc)
    if not svc.rename_folder(folder_name, safe_name):
        raise HTTPException(400, "Rename failed")
    return {"status": "ok", "new_name": safe_name}


@router.post("/upload/{folder_name}")
async def upload_file(
    folder_name: str,
    file: UploadFile = File(...),
    svc: LibraryService = Depends(get_library_service),
) -> dict:
    """Upload a file to a media folder.

    Supports audio files and cover images.
    For large files, the frontend should use chunked upload.
    """
    _safe_path(folder_name, svc)

    if not file.filename:
        raise HTTPException(400, "No filename provided")

    # Basic filename sanitization
    safe_filename = file.filename.replace("/", "_").replace("\\", "_")
    suffix = Path(safe_filename).suffix.lower()

    # Validate file type
    allowed = {".mp3", ".ogg", ".flac", ".wav", ".m4a", ".aac", ".opus",
               ".jpg", ".jpeg", ".png", ".webp"}
    if suffix not in allowed:
        raise HTTPException(400, f"File type not allowed: {suffix}")

    target = svc.get_upload_path(folder_name, safe_filename)

    # Stream file to disk with size limit enforcement
    try:
        bytes_written = 0
        with open(target, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1 MB chunks
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_BYTES:
                    f.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(
                        413,
                        f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload failed: %s", e)
        target.unlink(missing_ok=True)
        raise HTTPException(500, "Upload failed")

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
    svc: LibraryService = Depends(get_library_service),
) -> dict:
    """Upload or replace cover art for a folder."""
    _safe_path(folder_name, svc)

    if not file.filename:
        raise HTTPException(400, "No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "Only images allowed (jpg, png, webp)")

    # Cover images: 10 MB limit
    max_cover_bytes = 10 * 1024 * 1024

    # Always save as cover.{ext}
    target = svc.get_upload_path(folder_name, f"cover{suffix}")

    try:
        bytes_written = 0
        with open(target, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > max_cover_bytes:
                    f.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(
                        413,
                        f"Cover too large (max {max_cover_bytes // (1024 * 1024)} MB)",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Cover upload failed: %s", e)
        target.unlink(missing_ok=True)
        raise HTTPException(500, "Upload failed")

    return {"status": "ok", "cover_path": f"/api/library/{folder_name}/cover"}


@router.get("/stats")
async def library_stats(svc: LibraryService = Depends(get_library_service)) -> dict:
    return svc.disk_usage()
