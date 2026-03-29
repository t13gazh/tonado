"""Stream and podcast API routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.services.stream_service import StreamService

router = APIRouter(prefix="/api/streams", tags=["streams"])

_stream: StreamService | None = None


def init(stream_service: StreamService) -> None:
    global _stream
    _stream = stream_service


def _get_service() -> StreamService:
    if _stream is None:
        raise HTTPException(503, "Stream service not available")
    return _stream


# --- Radio ---


@router.get("/radio")
async def list_stations(category: str | None = None) -> list[dict]:
    stations = await _get_service().list_stations(category)
    return [s.to_dict() for s in stations]


class AddStationRequest(BaseModel):
    name: str
    url: str
    category: str = "custom"


@router.post("/radio", status_code=201)
async def add_station(req: AddStationRequest) -> dict:
    station = await _get_service().add_station(req.name, req.url, req.category)
    return station.to_dict()


@router.delete("/radio/{station_id}")
async def delete_station(station_id: int) -> dict:
    if not await _get_service().delete_station(station_id):
        raise HTTPException(404, "Station not found")
    return {"status": "ok"}


# --- Podcasts ---


@router.get("/podcasts")
async def list_podcasts() -> list[dict]:
    podcasts = await _get_service().list_podcasts()
    return [p.to_dict() for p in podcasts]


class AddPodcastRequest(BaseModel):
    name: str
    feed_url: str
    auto_download: bool = True


@router.post("/podcasts", status_code=201)
async def add_podcast(req: AddPodcastRequest) -> dict:
    podcast = await _get_service().add_podcast(req.name, req.feed_url, req.auto_download)
    return podcast.to_dict()


@router.delete("/podcasts/{podcast_id}")
async def delete_podcast(podcast_id: int) -> dict:
    if not await _get_service().delete_podcast(podcast_id):
        raise HTTPException(404, "Podcast not found")
    return {"status": "ok"}


@router.get("/podcasts/{podcast_id}/episodes")
async def list_episodes(podcast_id: int) -> list[dict]:
    episodes = await _get_service().list_episodes(podcast_id)
    return [e.to_dict() for e in episodes]


@router.post("/podcasts/{podcast_id}/refresh")
async def refresh_podcast(podcast_id: int) -> dict:
    new_count = await _get_service().refresh_podcast(podcast_id)
    return {"status": "ok", "new_episodes": new_count}
