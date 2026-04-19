"""Library and upload API routes."""

import logging
import os
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from core.dependencies import (
    get_auth_service,
    get_library_service,
    get_player,
    require_tier,
)
from core.services.auth_service import AuthService, AuthTier
from core.services.library_service import (
    DuplicateFolderName,
    FolderNotFound,
    InvalidFolderName,
    LibraryService,
)
from core.services.player_service import PlayerService
from core.utils.audio import AUDIO_EXTENSIONS, cover_etag, detect_image_mime, extract_cover
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
    resolved = (svc.media_dir / folder_name).resolve()
    media_resolved = svc.media_dir.resolve()
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
async def get_cover(
    folder_name: str,
    request: Request,
    svc: LibraryService = Depends(get_library_service),
) -> Response:
    _safe_path(folder_name, svc)
    cover_path = svc.get_cover_path(folder_name)
    if cover_path is None:
        raise HTTPException(404, "No cover available")
    headers = _cover_headers(cover_path)
    if _matches_inm(request, headers.get("ETag")):
        return Response(status_code=304, headers=headers)
    return FileResponse(cover_path, headers=headers)


# Covers are dynamic (users can replace cover.jpg or re-tag tracks), so
# `immutable` would serve stale art for up to an hour. Instead: advertise a
# 1 h freshness window and attach an ETag so browsers can revalidate cheaply
# with a conditional GET (→ 304 when mtime+size unchanged).
_COVER_CACHE_CONTROL = "public, max-age=3600"


def _resolve_library_path(relative: str, svc: LibraryService) -> Path:
    """Validate a relative library path and return the absolute Path.

    Raises HTTPException 400 for traversal attempts or paths outside media_dir.
    """
    if not relative or ".." in Path(relative).parts:
        raise HTTPException(400, "Invalid path")
    # Reject absolute paths and null bytes.
    if "\x00" in relative or Path(relative).is_absolute():
        raise HTTPException(400, "Invalid path")
    resolved = (svc.media_dir / relative).resolve()
    media_resolved = svc.media_dir.resolve()
    try:
        resolved.relative_to(media_resolved)
    except ValueError:
        raise HTTPException(400, "Invalid path")
    return resolved


def _cover_headers(source: Path, request: Request | None = None) -> dict[str, str]:
    """Build response headers for a cover payload derived from `source`."""
    headers = {"Cache-Control": _COVER_CACHE_CONTROL}
    etag = cover_etag(source)
    if etag is not None:
        headers["ETag"] = etag
    return headers


@router.get("/cover")
async def cover_by_path(
    request: Request,
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
            headers = _cover_headers(on_disk)
            if _matches_inm(request, headers.get("ETag")):
                return Response(status_code=304, headers=headers)
            return FileResponse(on_disk, headers=headers)
        # Fallback: embedded art from the first audio track. The ETag is derived
        # from the source track (mtime+size) so the browser can revalidate.
        for entry in sorted(abs_path.iterdir()):
            if entry.suffix.lower() in AUDIO_EXTENSIONS:
                data = extract_cover(entry)
                if data:
                    headers = _cover_headers(entry)
                    if _matches_inm(request, headers.get("ETag")):
                        return Response(status_code=304, headers=headers)
                    return Response(
                        content=data,
                        media_type=detect_image_mime(data),
                        headers=headers,
                    )
        raise HTTPException(404, "No cover available")

    # kind == "track"
    if not abs_path.is_file():
        raise HTTPException(404, "Track not found")
    data = extract_cover(abs_path)
    if not data:
        raise HTTPException(404, "No cover available")
    headers = _cover_headers(abs_path)
    if _matches_inm(request, headers.get("ETag")):
        return Response(status_code=304, headers=headers)
    return Response(
        content=data,
        media_type=detect_image_mime(data),
        headers=headers,
    )


def _matches_inm(request: Request, etag: str | None) -> bool:
    """True when the caller's If-None-Match matches our ETag → 304 response."""
    if not etag:
        return False
    inm = request.headers.get("if-none-match")
    if not inm:
        return False
    # Trivial parse: comma-separated list, accept either W/"..." or "..." forms
    # and match against our weak ETag verbatim or its strong-form stripped.
    candidates = [c.strip() for c in inm.split(",")]
    etag_strong = etag[2:] if etag.startswith("W/") else etag
    for cand in candidates:
        if cand == etag or cand == etag_strong or cand == "*":
            return True
    return False


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


class RenameFolderRequest(BaseModel):
    new_name: str = Field(min_length=1, max_length=200)


async def _update_path_references(
    db: aiosqlite.Connection,
    old_name: str,
    new_name: str,
) -> tuple[int, int]:
    """Update card and playlist-item content_path references.

    Conservative prefix match: rewrite any row where ``content_path`` equals
    ``old_name`` (folder-as-content) or starts with ``old_name + '/'`` (tracks
    within the folder). Returns (cards_updated, playlist_items_updated).

    Caller must manage transaction boundaries.
    """
    old_prefix = f"{old_name}/"
    new_prefix = f"{new_name}/"

    cards_cur = await db.execute(
        "UPDATE cards "
        "SET content_path = CASE "
        "  WHEN content_path = ? THEN ? "
        "  WHEN SUBSTR(content_path, 1, ?) = ? "
        "    THEN ? || SUBSTR(content_path, ?) "
        "  ELSE content_path END "
        "WHERE content_path = ? OR SUBSTR(content_path, 1, ?) = ?",
        (
            old_name, new_name,
            len(old_prefix), old_prefix,
            new_prefix, len(old_prefix) + 1,
            old_name, len(old_prefix), old_prefix,
        ),
    )
    cards_updated = cards_cur.rowcount or 0

    items_cur = await db.execute(
        "UPDATE playlist_items "
        "SET content_path = CASE "
        "  WHEN content_path = ? THEN ? "
        "  WHEN SUBSTR(content_path, 1, ?) = ? "
        "    THEN ? || SUBSTR(content_path, ?) "
        "  ELSE content_path END "
        "WHERE content_path = ? OR SUBSTR(content_path, 1, ?) = ?",
        (
            old_name, new_name,
            len(old_prefix), old_prefix,
            new_prefix, len(old_prefix) + 1,
            old_name, len(old_prefix), old_prefix,
        ),
    )
    items_updated = items_cur.rowcount or 0

    return cards_updated, items_updated


@router.put("/folders/{folder_name}")
async def rename_folder(
    folder_name: str,
    req: RenameFolderRequest,
    request: Request,
    svc: LibraryService = Depends(get_library_service),
    auth: AuthService = Depends(get_auth_service),
    player: PlayerService = Depends(get_player),
) -> dict:
    """Rename a media folder and atomically update all path references.

    Updates ``cards.content_path`` and ``playlist_items.content_path`` for
    both the folder-level references and track-level references (prefix
    match ``<old>/...``). If the filesystem rename fails, SQL is rolled
    back. If SQL fails after the FS rename succeeds, the directory is
    renamed back.

    Returns the new MediaFolder payload on success.
    """
    require_tier(request, AuthTier.PARENT, auth)
    _safe_path(folder_name, svc)

    # Block rename while the player is actively using content from this
    # folder — a running playback would otherwise lose its source.
    state = player.state
    if state.current_uri and (
        state.current_uri == folder_name
        or state.current_uri.startswith(f"{folder_name}/")
    ):
        raise HTTPException(409, "Ordner wird gerade abgespielt")

    db: aiosqlite.Connection = request.app.state.db_manager.connection

    try:
        # Step 1: validate + rename directory (raises on issues).
        folder = svc.rename_folder_checked(folder_name, req.new_name)
    except InvalidFolderName as exc:
        raise HTTPException(400, str(exc))
    except FolderNotFound:
        raise HTTPException(404, "Folder not found")
    except DuplicateFolderName:
        raise HTTPException(409, "Ein Ordner mit diesem Namen existiert bereits")
    except OSError as exc:
        logger.error("Folder rename failed on filesystem: %s", exc)
        raise HTTPException(500, "Rename failed")

    clean_new = folder.name

    # Step 2: update DB references inside a transaction, with FS rollback on
    # failure. aiosqlite's default isolation mode auto-begins a transaction
    # on the first write, so we can just commit or roll back explicitly.
    try:
        cards_updated, items_updated = await _update_path_references(
            db, folder_name, clean_new
        )
        await db.commit()
    except Exception as exc:
        logger.error("Reference update failed, rolling back FS rename: %s", exc)
        try:
            await db.rollback()
        except Exception:
            pass
        # Best-effort FS rollback — reverse the directory move.
        try:
            os.rename(svc.media_dir / clean_new, svc.media_dir / folder_name)
        except OSError as rb_exc:
            logger.critical(
                "FS rollback FAILED after SQL error: %s (folder now at '%s', "
                "DB still pointing to '%s')",
                rb_exc, clean_new, folder_name,
            )
        raise HTTPException(500, "Rename failed")

    logger.info(
        "Folder rename: '%s' -> '%s' (%d card(s), %d playlist item(s) updated)",
        folder_name, clean_new, cards_updated, items_updated,
    )

    # Notify subscribers that the library changed so the frontend refreshes.
    event_bus = getattr(request.app.state, "event_bus", None)
    if event_bus is not None:
        try:
            await event_bus.publish(
                "library_changed",
                reason="folder_renamed",
                old_name=folder_name,
                new_name=clean_new,
            )
        except Exception as exc:
            logger.warning("event_bus publish failed for folder_renamed: %s", exc)

    return folder.to_dict()


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
