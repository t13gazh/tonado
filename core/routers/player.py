"""Player API routes."""

import asyncio
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)

from pydantic import BaseModel

from core.dependencies import (
    get_auth_service,
    get_library_service,
    get_player,
    require_tier,
)
from core.schemas.player import PlayerStateResponse, SeekRequest, VolumeRequest
from core.services.auth_service import AuthService, AuthTier
from core.services.library_service import LibraryService
from core.services.player_service import PlayerService
from core.utils.url import SSRFError, validate_url

router = APIRouter(prefix="/api/player", tags=["player"])


@router.get("/state", response_model=PlayerStateResponse)
async def get_state(player: PlayerService = Depends(get_player)) -> dict:
    return player.state.to_dict()


@router.post("/play")
async def play(player: PlayerService = Depends(get_player)) -> dict:
    await player.play()
    return {"status": "ok"}


@router.post("/pause")
async def pause(player: PlayerService = Depends(get_player)) -> dict:
    await player.pause()
    return {"status": "ok"}


@router.post("/toggle")
async def toggle(player: PlayerService = Depends(get_player)) -> dict:
    await player.toggle()
    return {"status": "ok"}


@router.post("/stop")
async def stop(player: PlayerService = Depends(get_player)) -> dict:
    await player.stop_playback()
    return {"status": "ok"}


@router.post("/next")
async def next_track(player: PlayerService = Depends(get_player)) -> dict:
    await player.next_track()
    return {"status": "ok"}


@router.post("/previous")
async def previous_track(player: PlayerService = Depends(get_player)) -> dict:
    await player.previous_track()
    return {"status": "ok"}


@router.post("/volume")
async def set_volume(req: VolumeRequest, player: PlayerService = Depends(get_player)) -> dict:
    await player.set_volume(req.volume)
    return {"status": "ok", "volume": req.volume}


@router.post("/seek")
async def seek(req: SeekRequest, player: PlayerService = Depends(get_player)) -> dict:
    await player.seek(req.position)
    return {"status": "ok"}


@router.post("/shuffle")
async def toggle_random(player: PlayerService = Depends(get_player)) -> dict:
    """Toggle random (shuffle) mode on/off."""
    state = await player.toggle_random()
    return {"status": "ok", "shuffle": state}


@router.post("/repeat")
async def cycle_repeat(player: PlayerService = Depends(get_player)) -> dict:
    """Cycle repeat mode: off → all → single → off."""
    mode = await player.cycle_repeat()
    return {"status": "ok", "repeat_mode": mode.value}


@router.get("/outputs")
async def list_outputs(player: PlayerService = Depends(get_player)) -> list:
    return await player.list_outputs()


class OutputToggle(BaseModel):
    enabled: bool


@router.post("/outputs/{output_id}")
async def toggle_output(
    output_id: int,
    req: OutputToggle,
    request: Request,
    player: PlayerService = Depends(get_player),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    require_tier(request, AuthTier.PARENT, auth)
    await player.toggle_output(output_id, req.enabled)
    return {"status": "ok"}


@router.get("/stream")
async def audio_stream():
    """Proxy MPD HTTP stream to browser (avoids CORS issues).

    MPD's httpd output returns an empty reply when playback is stopped
    or during track transitions.  This endpoint retries a few times so
    the browser doesn't immediately receive a 503 on every track change.
    """
    max_attempts = 5
    delay = 0.6  # seconds between retries

    for attempt in range(max_attempts):
        client = httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=None))
        resp = None
        try:
            resp = await client.send(
                client.build_request("GET", "http://localhost:8090/"),
                stream=True,
            )
            # MPD returns 200 with data when playing, but may also return
            # 200 with an immediate close when idle.  Read the first chunk
            # to verify we're actually getting audio data.
            # IMPORTANT: aiter_bytes() must only be called once per response —
            # httpx marks the stream as consumed on first iteration.
            byte_iter = resp.aiter_bytes(chunk_size=4096)
            first_chunk = await byte_iter.__anext__()

            async def generate():
                try:
                    yield first_chunk
                    async for chunk in byte_iter:
                        yield chunk
                finally:
                    await resp.aclose()
                    await client.aclose()

            return StreamingResponse(generate(), media_type="audio/mpeg")
        except (httpx.RemoteProtocolError, httpx.ConnectError, StopAsyncIteration) as e:
            # Empty reply or connection refused — MPD not streaming yet
            if resp:
                await resp.aclose()
            await client.aclose()
            if attempt < max_attempts - 1:
                logger.debug("Stream attempt %d failed (%s), retrying in %.1fs", attempt + 1, e, delay)
                await asyncio.sleep(delay)
            else:
                raise HTTPException(503, f"Stream not available after {max_attempts} attempts: {e}")
        except Exception as e:
            if resp:
                await resp.aclose()
            await client.aclose()
            raise HTTPException(503, f"Stream not available: {e}")


class PlayUrlsRequest(BaseModel):
    urls: list[str]
    start_index: int = 0


@router.post("/play-urls")
async def play_urls(req: PlayUrlsRequest, player: PlayerService = Depends(get_player)) -> dict:
    """Play multiple URLs as a queue, starting at given index."""
    for url in req.urls:
        try:
            validate_url(url, resolve_dns=False)
        except SSRFError as e:
            raise HTTPException(400, str(e))
    await player.play_urls(req.urls, req.start_index)
    return {"status": "ok"}


class PlayFolderRequest(BaseModel):
    path: str
    start_index: int = 0


def _validate_folder_path(path: str, library: LibraryService) -> None:
    """Reject empty, traversing, absolute or out-of-root folder paths."""
    if not path or "\x00" in path:
        raise HTTPException(400, "Ungültiger Pfad")
    parts = Path(path).parts
    if ".." in parts:
        raise HTTPException(400, "Ungültiger Pfad")
    if Path(path).is_absolute() or path.startswith(("/", "\\")):
        raise HTTPException(400, "Ungültiger Pfad")
    try:
        resolved = (library._media_dir / path).resolve()
        media_resolved = library._media_dir.resolve()
    except (OSError, ValueError):
        raise HTTPException(400, "Ungültiger Pfad")
    try:
        resolved.relative_to(media_resolved)
    except ValueError:
        raise HTTPException(400, "Ungültiger Pfad")


@router.post("/play-folder")
async def play_folder(
    req: PlayFolderRequest,
    player: PlayerService = Depends(get_player),
    library: LibraryService = Depends(get_library_service),
) -> dict:
    """Play all tracks in a media folder, optionally starting at a specific track."""
    _validate_folder_path(req.path, library)
    logger.info("play_folder called with path: %r, start_index: %d", req.path, req.start_index)
    await player.play_folder(req.path, start_index=req.start_index)
    return {"status": "ok"}


class PlayUrlRequest(BaseModel):
    url: str


@router.post("/play-url")
async def play_url(req: PlayUrlRequest, player: PlayerService = Depends(get_player)) -> dict:
    """Play a stream URL (radio, podcast)."""
    try:
        validate_url(req.url, resolve_dns=False)
    except SSRFError as e:
        raise HTTPException(400, str(e))
    await player.play_url(req.url)
    return {"status": "ok"}
