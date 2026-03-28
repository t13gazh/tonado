"""Player API routes."""

import logging
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

from pydantic import BaseModel

from core.schemas.player import PlayerStateResponse, SeekRequest, VolumeRequest
from core.services.player_service import PlayerService

router = APIRouter(prefix="/api/player", tags=["player"])

# Service reference set during app startup
_player: PlayerService | None = None


def init(player_service: PlayerService) -> None:
    global _player
    _player = player_service


def _get_player() -> PlayerService:
    if _player is None:
        raise HTTPException(503, "Player service not available")
    return _player


@router.get("/state", response_model=PlayerStateResponse)
async def get_state() -> dict:
    return _get_player().state.to_dict()


@router.post("/play")
async def play() -> dict:
    await _get_player().play()
    return {"status": "ok"}


@router.post("/pause")
async def pause() -> dict:
    await _get_player().pause()
    return {"status": "ok"}


@router.post("/toggle")
async def toggle() -> dict:
    await _get_player().toggle()
    return {"status": "ok"}


@router.post("/stop")
async def stop() -> dict:
    await _get_player().stop_playback()
    return {"status": "ok"}


@router.post("/next")
async def next_track() -> dict:
    await _get_player().next_track()
    return {"status": "ok"}


@router.post("/previous")
async def previous_track() -> dict:
    await _get_player().previous_track()
    return {"status": "ok"}


@router.post("/volume")
async def set_volume(req: VolumeRequest) -> dict:
    await _get_player().set_volume(req.volume)
    return {"status": "ok", "volume": req.volume}


@router.post("/seek")
async def seek(req: SeekRequest) -> dict:
    await _get_player().seek(req.position)
    return {"status": "ok"}


@router.post("/shuffle")
async def shuffle() -> dict:
    await _get_player().shuffle()
    return {"status": "ok"}


@router.post("/repeat")
async def cycle_repeat() -> dict:
    """Cycle repeat mode: off → all → single → off."""
    mode = await _get_player().cycle_repeat()
    return {"status": "ok", "repeat_mode": mode.value}


class PlayFolderRequest(BaseModel):
    path: str


@router.post("/play-folder")
async def play_folder(req: PlayFolderRequest) -> dict:
    """Play all tracks in a media folder."""
    logger.info("play_folder called with path: %r", req.path)
    await _get_player().play_folder(req.path)
    return {"status": "ok"}


class PlayUrlRequest(BaseModel):
    url: str


@router.post("/play-url")
async def play_url(req: PlayUrlRequest) -> dict:
    """Play a stream URL (radio, podcast)."""
    await _get_player().play_url(req.url)
    return {"status": "ok"}
