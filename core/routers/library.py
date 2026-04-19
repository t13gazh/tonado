"""Library and upload API routes."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, Response

from core.dependencies import get_auth_service, get_library_service, require_tier
from core.services.auth_service import AuthService, AuthTier
from core.services.library_service import LibraryService
from core.utils.audio import AUDIO_EXTENSIONS, detect_image_mime, extract_cover
from core.utils.upload import stream_to_disk

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/library", tags=["library"])

# Maximum upload size per file in bytes (500 MB default)
MAX_UPLOAD_BYTES = 500 * 1024 * 1024


def _sanitize_filename(raw: str) -> str:
    """Reduce an uploaded filename to a safe basename.

    Strips null bytes, collapses Windows backslashes so a Linux runtime
    cannot leave them verbatim in the saved path, and applies Path.name
    to drop every parent component.
    """
    cleaned = raw.replace("\x00", "").replace("\\", "/")
    return Path(cleaned).name


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


# Cover cache max-age (1 hour). Clients get fresh art when mtime changes because
# we key the in-memory cache by (path, mtime, size).
_COVER_CACHE_CONTROL = "public, max-age=3600, immutable"


def _resolve_library_path(relative: str, svc: LibraryService) -> Path:
    """Validate a relative library path and return the absolute Path.

    Raises HTTPException 400 for traversal attempts or paths outside media_dir.
    """
    if not relative or ".." in Path(relative).parts:
        raise HTTPException(400, "Invalid path")
    # Reject absolute paths and null bytes.
    if "\x00" in relative or Path(relative).is_absolute():
        raise HTTPException(400, "Invalid path")
    resolved = (svc._media_dir / relative).resolve()
    media_resolved = svc._media_dir.resolve()
    try:
        resolved.relative_to(media_resolved)
    except ValueError:
        raise HTTPException(400, "Invalid path")
    return resolved


@router.get("/cover")
async def cover_by_path(
    path: str = Query(..., description="Folder or track path relative to library root"),
    kind: str = Query("folder", description="folder | track"),
    svc: LibraryService = Depends(get_library_service),
) -> Response:
    """Return cover art for a folder or track.

    For folders: on-disk cover file (cover.jpg/folder.jpg/etc.) takes priority,
    otherwise falls back to the first track's embedded art.
    For tracks: extracts embedded cover art from tags.
    """
    if kind not in ("folder", "track"):
        raise HTTPException(400, "kind must be 'folder' or 'track'")

    abs_path = _resolve_library_path(path, svc)

    if kind == "folder":
        if not abs_path.is_dir():
            raise HTTPException(404, "Folder not found")
        # Priority: on-disk cover file
        on_disk = svc._find_cover(abs_path)
        if on_disk is not None:
            return FileResponse(on_disk, headers={"Cache-Control": _COVER_CACHE_CONTROL})
        # Fallback: embedded art from the first audio track
        for entry in sorted(abs_path.iterdir()):
            if entry.suffix.lower() in AUDIO_EXTENSIONS:
                data = extract_cover(entry)
                if data:
                    return Response(
                        content=data,
                        media_type=detect_image_mime(data),
                        headers={"Cache-Control": _COVER_CACHE_CONTROL},
                    )
        raise HTTPException(404, "No cover available")

    # kind == "track"
    if not abs_path.is_file():
        raise HTTPException(404, "Track not found")
    data = extract_cover(abs_path)
    if not data:
        raise HTTPException(404, "No cover available")
    return Response(
        content=data,
        media_type=detect_image_mime(data),
        headers={"Cache-Control": _COVER_CACHE_CONTROL},
    )


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

    safe_filename = _sanitize_filename(file.filename)
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

    # Reuse the upload sanitiser — even though we write a fixed basename
    # (cover.<ext>), the suffix is derived from the user-controlled name
    # and must not carry null bytes or backslash trickery through.
    safe_filename = _sanitize_filename(file.filename)
    suffix = Path(safe_filename).suffix.lower()
    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    max_cover_bytes = 10 * 1024 * 1024

    # Always save as cover.{ext}
    target = svc.get_upload_path(folder_name, f"cover{suffix}")
    await stream_to_disk(file, target, max_cover_bytes, image_extensions)

    return {"status": "ok", "cover_path": f"/api/library/{folder_name}/cover"}


@router.get("/stats")
async def library_stats(svc: LibraryService = Depends(get_library_service)) -> dict:
    return svc.disk_usage()
