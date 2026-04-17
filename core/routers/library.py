"""Library and upload API routes."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse

from core.dependencies import get_auth_service, get_library_service, require_tier
from core.services.auth_service import AuthService, AuthTier
from core.services.library_service import LibraryService
from core.utils.upload import stream_to_disk

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
    return [f.to_dict() for f in await svc.list_folders()]


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
async def create_folder(
    request: Request,
    name: str = Form(...),
    svc: LibraryService = Depends(get_library_service),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    require_tier(request, AuthTier.PARENT, auth)
    # Sanitize folder name
    safe_name = name.strip().replace("/", "_").replace("\\", "_")
    if not safe_name:
        raise HTTPException(400, "Invalid folder name")
    folder = svc.create_folder(safe_name)
    return folder.to_dict()


@router.delete("/folders/{folder_name}")
async def delete_folder(
    folder_name: str,
    request: Request,
    svc: LibraryService = Depends(get_library_service),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    require_tier(request, AuthTier.PARENT, auth)
    _safe_path(folder_name, svc)
    if not svc.delete_folder(folder_name):
        raise HTTPException(404, "Folder not found")
    return {"status": "ok"}


@router.put("/folders/{folder_name}/rename")
async def rename_folder(
    folder_name: str,
    request: Request,
    new_name: str = Form(...),
    svc: LibraryService = Depends(get_library_service),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    require_tier(request, AuthTier.PARENT, auth)
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
    request: Request,
    file: UploadFile = File(...),
    svc: LibraryService = Depends(get_library_service),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    """Upload a file to a media folder.

    Supports audio files and cover images.
    For large files, the frontend should use chunked upload.
    """
    require_tier(request, AuthTier.PARENT, auth)
    _safe_path(folder_name, svc)

    if not file.filename:
        raise HTTPException(400, "No filename provided")

    # Path(..).name only strips the runtime's own separator; we also need
    # to collapse Windows backslashes and null bytes that a Linux runtime
    # would otherwise keep verbatim.
    raw = file.filename.replace("\x00", "").replace("\\", "/")
    safe_filename = Path(raw).name
    if not safe_filename or safe_filename in (".", ".."):
        raise HTTPException(400, "Invalid filename")
    target = svc.get_upload_path(folder_name, safe_filename)

    allowed = {".mp3", ".ogg", ".flac", ".wav", ".m4a", ".aac", ".opus",
               ".jpg", ".jpeg", ".png", ".webp"}
    size = await stream_to_disk(file, target, MAX_UPLOAD_BYTES, allowed)

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
    request: Request,
    file: UploadFile = File(...),
    svc: LibraryService = Depends(get_library_service),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    """Upload or replace cover art for a folder."""
    require_tier(request, AuthTier.PARENT, auth)
    _safe_path(folder_name, svc)

    if not file.filename:
        raise HTTPException(400, "No filename provided")

    suffix = Path(file.filename).suffix.lower()
    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    max_cover_bytes = 10 * 1024 * 1024

    # Always save as cover.{ext}
    target = svc.get_upload_path(folder_name, f"cover{suffix}")
    await stream_to_disk(file, target, max_cover_bytes, image_extensions)

    return {"status": "ok", "cover_path": f"/api/library/{folder_name}/cover"}


@router.get("/stats")
async def library_stats(svc: LibraryService = Depends(get_library_service)) -> dict:
    return svc.disk_usage()
