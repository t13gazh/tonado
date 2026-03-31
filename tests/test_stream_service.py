"""Tests for the stream service."""

from pathlib import Path

import aiosqlite
import pytest

from core.services.stream_service import StreamService


@pytest.fixture
async def stream_service(tmp_db: aiosqlite.Connection, tmp_path: Path):
    service = StreamService(tmp_db, podcast_dir=tmp_path / "podcasts")
    await service.start()
    yield service


@pytest.mark.asyncio
async def test_default_stations_seeded(stream_service: StreamService) -> None:
    stations = await stream_service.list_stations()
    assert len(stations) > 0
    assert any("Die Maus" in s.name for s in stations)


@pytest.mark.asyncio
async def test_add_and_delete_station(stream_service: StreamService) -> None:
    station = await stream_service.add_station("Test Radio", "http://example.com/stream")
    assert station.name == "Test Radio"
    assert station.id > 0

    assert await stream_service.delete_station(station.id) is True
    stations = await stream_service.list_stations(category="custom")
    assert all(s.id != station.id for s in stations)


@pytest.mark.asyncio
async def test_filter_by_category(stream_service: StreamService) -> None:
    kinder = await stream_service.list_stations(category="kinder")
    assert len(kinder) > 0
    assert all(s.category == "kinder" for s in kinder)


@pytest.mark.asyncio
async def test_add_podcast(stream_service: StreamService) -> None:
    # Add podcast without actually fetching RSS (will fail gracefully)
    podcast = await stream_service.add_podcast("Test Pod", "http://example.com/feed.xml")
    assert podcast.name == "Test Pod"
    assert podcast.id > 0

    podcasts = await stream_service.list_podcasts()
    # Default podcasts are seeded, so count includes those + the new one
    assert any(p.name == "Test Pod" for p in podcasts)


@pytest.mark.asyncio
async def test_delete_podcast(stream_service: StreamService) -> None:
    podcast = await stream_service.add_podcast("To Delete", "http://example.com/delete.xml")
    assert await stream_service.delete_podcast(podcast.id) is True

    podcasts = await stream_service.list_podcasts()
    assert not any(p.name == "To Delete" for p in podcasts)
