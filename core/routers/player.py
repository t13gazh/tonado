"""Player API routes."""

import asyncio
import logging
from contextlib import AsyncExitStack
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)

from pydantic import BaseModel

from core.dependencies import (
    get_auth_service,
    get_library_service,
    get_playback_dispatcher,
    get_player,
    require_tier,
)
from core.playback_dispatcher import PlaybackDispatcher
from core.schemas.common import ContentType
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
async def stop(
    player: PlayerService = Depends(get_player),
    dispatcher: PlaybackDispatcher | None = Depends(get_playback_dispatcher),
) -> dict:
    await player.stop_playback()
    if dispatcher is not None:
        dispatcher.clear_source()
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


# Icy/streaming headers to pass through from MPD httpd to the browser.
# Lowercased — httpx normalizes header keys to lowercase.
_PASSTHROUGH_HEADERS = (
    "icy-name",
    "icy-description",
    "icy-genre",
    "icy-br",
    "icy-sr",
    "icy-pub",
    "icy-url",
    "icy-metaint",
)


@router.get("/stream")
async def audio_stream():
    """Proxy MPD HTTP stream to browser (avoids CORS issues).

    MPD's httpd output returns an empty reply when playback is stopped
    or during track transitions.  This endpoint retries a few times so
    the browser doesn't immediately receive a 503 on every track change.

    Resource hygiene: the httpx client and the streamed upstream response
    are both registered with an ``AsyncExitStack`` so that a client
    disconnect (``GeneratorExit``/cancellation during iteration) cleanly
    releases the upstream slot on MPD's httpd output.  Previously a
    hastily reloading browser could leave MPD slots dangling, causing
    "empty reply" failures on the next connect.
    """
    max_attempts = 3
    delay = 0.6  # seconds between retries

    for attempt in range(max_attempts):
        stack = AsyncExitStack()
        try:
            client = await stack.enter_async_context(
                httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=None))
            )
            resp = await stack.enter_async_context(
                client.stream("GET", "http://localhost:8090/")
            )
            # MPD returns 200 with data when playing, but may also return
            # 200 with an immediate close when idle.  Read the first chunk
            # to verify we're actually getting audio data.
            # IMPORTANT: aiter_bytes() must only be called once per response —
            # httpx marks the stream as consumed on first iteration.
            byte_iter = resp.aiter_bytes(chunk_size=4096)
            first_chunk = await byte_iter.__anext__()

            # Take MIME from upstream; MPD httpd usually sends
            # audio/ogg for vorbis and audio/mpeg for lame.
            media_type = resp.headers.get("content-type", "audio/mpeg")

            # Forward icy-metadata from the shoutcast-style MPD httpd
            # so clients that understand it can show station info.
            extra_headers: dict[str, str] = {"Cache-Control": "no-store"}
            for name in _PASSTHROUGH_HEADERS:
                value = resp.headers.get(name)
                if value is not None:
                    extra_headers[name] = value

            # Capture the stack in the generator's closure so it closes
            # cleanly even if the client disconnects mid-stream.  The
            # outer `try/except` path no longer owns the stack once we
            # reach here — the generator is the sole owner.
            captured_stack = stack
            stack = AsyncExitStack()  # fresh dummy for the `finally` below

            async def generate():
                try:
                    yield first_chunk
                    async for chunk in byte_iter:
                        yield chunk
                finally:
                    # Runs on normal completion, client disconnect, and
                    # server-side cancellation alike — guaranteeing the
                    # upstream httpx slot is released to MPD httpd.
                    await captured_stack.aclose()

            return StreamingResponse(
                generate(), media_type=media_type, headers=extra_headers
            )
        except (httpx.RemoteProtocolError, httpx.ConnectError, StopAsyncIteration) as e:
            # Empty reply or connection refused — MPD not streaming yet
            await stack.aclose()
            if attempt < max_attempts - 1:
                logger.info(
                    "Stream attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt + 1, max_attempts, e, delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.info(
                    "Stream unavailable after %d attempts: %s", max_attempts, e
                )
                raise HTTPException(
                    503, f"Stream not available after {max_attempts} attempts: {e}"
                )
        except Exception as e:
            await stack.aclose()
            logger.info("Stream proxy failed unexpectedly: %s", e)
            raise HTTPException(503, f"Stream not available: {e}")


class PlayUrlsRequest(BaseModel):
    urls: list[str]
    start_index: int = 0


@router.post("/play-urls")
async def play_urls(
    req: PlayUrlsRequest,
    player: PlayerService = Depends(get_player),
    dispatcher: PlaybackDispatcher | None = Depends(get_playback_dispatcher),
) -> dict:
    """Play multiple URLs as a queue, starting at given index."""
    for url in req.urls:
        try:
            validate_url(url, resolve_dns=False)
        except SSRFError as e:
            raise HTTPException(400, str(e))
    await player.play_urls(req.urls, req.start_index)
    # A raw URL queue has no single logical source — clear any stale one so
    # rename_folder etc. don't falsely block.
    if dispatcher is not None:
        dispatcher.clear_source()
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
        resolved = (library.media_dir / path).resolve()
        media_resolved = library.media_dir.resolve()
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
    dispatcher: PlaybackDispatcher | None = Depends(get_playback_dispatcher),
) -> dict:
    """Play all tracks in a media folder, optionally starting at a specific track."""
    _validate_folder_path(req.path, library)
    logger.info("play_folder called with path: %r, start_index: %d", req.path, req.start_index)
    await player.play_folder(req.path, start_index=req.start_index)
    if dispatcher is not None:
        dispatcher.set_source(ContentType.FOLDER, req.path)
    return {"status": "ok"}


class PlayUrlRequest(BaseModel):
    url: str


@router.post("/play-url")
async def play_url(
    req: PlayUrlRequest,
    player: PlayerService = Depends(get_player),
    dispatcher: PlaybackDispatcher | None = Depends(get_playback_dispatcher),
) -> dict:
    """Play a stream URL (radio, podcast)."""
    try:
        validate_url(req.url, resolve_dns=False)
    except SSRFError as e:
        raise HTTPException(400, str(e))
    await player.play_url(req.url)
    # Treat a bare URL as a generic stream source. This is a best-effort
    # label — radio vs. podcast disambiguation would require matching
    # the URL against the catalog tables, which callers can do explicitly
    # via the dispatcher if needed.
    if dispatcher is not None:
        dispatcher.set_source(ContentType.STREAM, req.url)
    return {"status": "ok"}
