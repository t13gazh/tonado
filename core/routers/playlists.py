"""Playlist API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.dependencies import get_player, get_playlist_service
from core.services.player_service import PlayerService
from core.services.playlist_service import PlaylistService

router = APIRouter(prefix="/api/playlists", tags=["playlists"])


@router.get("/")
async def list_playlists(svc: PlaylistService = Depends(get_playlist_service)) -> list[dict]:
    playlists = await svc.list_playlists()
    return [p.to_summary() for p in playlists]


@router.get("/{playlist_id}")
async def get_playlist(playlist_id: int, svc: PlaylistService = Depends(get_playlist_service)) -> dict:
    p = await svc.get_playlist(playlist_id)
    if p is None:
        raise HTTPException(404, "Playlist not found")
    return p.to_dict()


class CreatePlaylistRequest(BaseModel):
    name: str = Field(min_length=1)


@router.post("/", status_code=201)
async def create_playlist(
    req: CreatePlaylistRequest,
    svc: PlaylistService = Depends(get_playlist_service),
) -> dict:
    p = await svc.create_playlist(req.name)
    return p.to_summary()


@router.delete("/{playlist_id}")
async def delete_playlist(playlist_id: int, svc: PlaylistService = Depends(get_playlist_service)) -> dict:
    if not await svc.delete_playlist(playlist_id):
        raise HTTPException(404, "Playlist not found")
    return {"status": "ok"}


class AddItemRequest(BaseModel):
    content_type: str = Field(pattern=r"^(track|folder|stream)$")
    content_path: str = Field(min_length=1)
    title: str | None = None


@router.post("/{playlist_id}/items", status_code=201)
async def add_item(
    playlist_id: int,
    req: AddItemRequest,
    svc: PlaylistService = Depends(get_playlist_service),
) -> dict:
    item = await svc.add_item(
        playlist_id, req.content_type, req.content_path, req.title,
    )
    if item is None:
        raise HTTPException(404, "Playlist not found")
    return item.to_dict()


@router.delete("/items/{item_id}")
async def remove_item(item_id: int, svc: PlaylistService = Depends(get_playlist_service)) -> dict:
    if not await svc.remove_item(item_id):
        raise HTTPException(404, "Item not found")
    return {"status": "ok"}


@router.post("/{playlist_id}/play")
async def play_playlist(
    playlist_id: int,
    svc: PlaylistService = Depends(get_playlist_service),
    player: PlayerService = Depends(get_player),
) -> dict:
    """Play all items in a playlist sequentially."""
    p = await svc.get_playlist(playlist_id)
    if p is None:
        raise HTTPException(404, "Playlist not found")
    if not p.items:
        raise HTTPException(400, "Playlist is empty")

    # Collect all content paths and play as queue
    paths = [item.content_path for item in p.items]
    if len(paths) == 1 and p.items[0].content_type == "folder":
        await player.play_folder(paths[0])
    else:
        await player.play_urls(paths)

    return {"status": "ok", "items": len(p.items)}
