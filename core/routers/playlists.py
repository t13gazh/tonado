"""Playlist API routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.services.playlist_service import PlaylistService

router = APIRouter(prefix="/api/playlists", tags=["playlists"])

_service: PlaylistService | None = None


def init(playlist_service: PlaylistService) -> None:
    global _service
    _service = playlist_service


def _get_service() -> PlaylistService:
    if _service is None:
        raise HTTPException(503, "Playlist service not available")
    return _service


@router.get("/")
async def list_playlists() -> list[dict]:
    playlists = await _get_service().list_playlists()
    return [p.to_summary() for p in playlists]


@router.get("/{playlist_id}")
async def get_playlist(playlist_id: int) -> dict:
    p = await _get_service().get_playlist(playlist_id)
    if p is None:
        raise HTTPException(404, "Playlist nicht gefunden")
    return p.to_dict()


class CreatePlaylistRequest(BaseModel):
    name: str = Field(min_length=1)


@router.post("/", status_code=201)
async def create_playlist(req: CreatePlaylistRequest) -> dict:
    p = await _get_service().create_playlist(req.name)
    return p.to_summary()


@router.delete("/{playlist_id}")
async def delete_playlist(playlist_id: int) -> dict:
    if not await _get_service().delete_playlist(playlist_id):
        raise HTTPException(404, "Playlist nicht gefunden")
    return {"status": "ok"}


class AddItemRequest(BaseModel):
    content_type: str = Field(pattern=r"^(track|folder|stream)$")
    content_path: str = Field(min_length=1)
    title: str | None = None


@router.post("/{playlist_id}/items", status_code=201)
async def add_item(playlist_id: int, req: AddItemRequest) -> dict:
    item = await _get_service().add_item(
        playlist_id, req.content_type, req.content_path, req.title,
    )
    if item is None:
        raise HTTPException(404, "Playlist nicht gefunden")
    return item.to_dict()


@router.delete("/items/{item_id}")
async def remove_item(item_id: int) -> dict:
    if not await _get_service().remove_item(item_id):
        raise HTTPException(404, "Eintrag nicht gefunden")
    return {"status": "ok"}
