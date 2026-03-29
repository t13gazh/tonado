"""Stream and podcast API routes."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.dependencies import get_stream_service
from core.services.stream_service import StreamService

router = APIRouter(prefix="/api/streams", tags=["streams"])


# --- Radio ---


@router.get("/radio")
async def list_stations(
    category: str | None = None,
    svc: StreamService = Depends(get_stream_service),
) -> list[dict]:
    stations = await svc.list_stations(category)
    return [asdict(s) for s in stations]


class AddStationRequest(BaseModel):
    name: str
    url: str
    category: str = "custom"


@router.post("/radio", status_code=201)
async def add_station(req: AddStationRequest, svc: StreamService = Depends(get_stream_service)) -> dict:
    station = await svc.add_station(req.name, req.url, req.category)
    return asdict(station)


@router.delete("/radio/{station_id}")
async def delete_station(station_id: int, svc: StreamService = Depends(get_stream_service)) -> dict:
    if not await svc.delete_station(station_id):
        raise HTTPException(404, "Station not found")
    return {"status": "ok"}


# --- Podcasts ---


@router.get("/podcasts")
async def list_podcasts(svc: StreamService = Depends(get_stream_service)) -> list[dict]:
    podcasts = await svc.list_podcasts()
    return [p.to_dict() for p in podcasts]


class AddPodcastRequest(BaseModel):
    name: str
    feed_url: str
    auto_download: bool = True


@router.post("/podcasts", status_code=201)
async def add_podcast(req: AddPodcastRequest, svc: StreamService = Depends(get_stream_service)) -> dict:
    podcast = await svc.add_podcast(req.name, req.feed_url, req.auto_download)
    return podcast.to_dict()


@router.delete("/podcasts/{podcast_id}")
async def delete_podcast(podcast_id: int, svc: StreamService = Depends(get_stream_service)) -> dict:
    if not await svc.delete_podcast(podcast_id):
        raise HTTPException(404, "Podcast not found")
    return {"status": "ok"}


@router.get("/podcasts/{podcast_id}/episodes")
async def list_episodes(podcast_id: int, svc: StreamService = Depends(get_stream_service)) -> list[dict]:
    episodes = await svc.list_episodes(podcast_id)
    return [asdict(e) for e in episodes]


@router.post("/podcasts/{podcast_id}/refresh")
async def refresh_podcast(podcast_id: int, svc: StreamService = Depends(get_stream_service)) -> dict:
    new_count = await svc.refresh_podcast(podcast_id)
    return {"status": "ok", "new_episodes": new_count}
