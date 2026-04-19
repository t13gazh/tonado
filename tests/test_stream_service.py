"""Tests for the stream service."""

from pathlib import Path
from unittest.mock import AsyncMock

import aiosqlite
import httpx
import pytest

from core.services.stream_service import StreamService


@pytest.fixture
async def stream_service(tmp_db: aiosqlite.Connection, tmp_path: Path):
    service = StreamService(tmp_db, podcast_dir=tmp_path / "podcasts")
    # Don't hit the network for RSS parsing — tests don't care about feed content
    service._parse_rss = AsyncMock(return_value=[])
    service.refresh_podcast = AsyncMock(return_value=None)
    # validate_url does DNS resolution; also skip it for the synthetic URLs
    import core.services.stream_service as mod
    service._patched_validate = mod.validate_url
    mod.validate_url = lambda url, *a, **kw: None
    await service.start()
    try:
        yield service
    finally:
        mod.validate_url = service._patched_validate


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


# --- RSS parser tests (itunes:image per episode) ---


_RSS_WITH_ITUNES_IMAGE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Test Show</title>
    <itunes:image href="https://example.com/show.jpg"/>
    <item>
      <title>Episode with image</title>
      <pubDate>Mon, 01 Jan 2024 00:00:00 +0000</pubDate>
      <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="1000"/>
      <itunes:image href="https://example.com/ep1.jpg"/>
      <itunes:duration>600</itunes:duration>
    </item>
    <item>
      <title>Episode without image</title>
      <pubDate>Mon, 02 Jan 2024 00:00:00 +0000</pubDate>
      <enclosure url="https://example.com/ep2.mp3" type="audio/mpeg" length="1000"/>
    </item>
    <item>
      <title>Episode with javascript url</title>
      <pubDate>Mon, 03 Jan 2024 00:00:00 +0000</pubDate>
      <enclosure url="https://example.com/ep3.mp3" type="audio/mpeg" length="1000"/>
      <itunes:image href="javascript:alert(1)"/>
    </item>
    <item>
      <title>Episode with empty href</title>
      <pubDate>Mon, 04 Jan 2024 00:00:00 +0000</pubDate>
      <enclosure url="https://example.com/ep4.mp3" type="audio/mpeg" length="1000"/>
      <itunes:image href=""/>
    </item>
  </channel>
</rss>
"""


_RSS_PLAIN_NO_ITUNES = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Plain Show</title>
    <item>
      <title>Plain Episode</title>
      <enclosure url="https://example.com/p1.mp3" type="audio/mpeg" length="1000"/>
    </item>
  </channel>
</rss>
"""


class _MockResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class _MockClient:
    def __init__(self, content: bytes) -> None:
        self._content = content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url: str) -> _MockResponse:
        return _MockResponse(self._content)


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, content: bytes) -> None:
    import core.services.stream_service as mod

    def _factory(*a, **kw) -> _MockClient:
        return _MockClient(content)

    monkeypatch.setattr(mod.httpx, "AsyncClient", _factory)
    monkeypatch.setattr(mod, "validate_url", lambda url, *a, **kw: None)


@pytest.mark.asyncio
async def test_parse_rss_extracts_itunes_image(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_httpx(monkeypatch, _RSS_WITH_ITUNES_IMAGE)
    episodes = await StreamService._parse_rss("http://example.com/feed.xml")

    assert len(episodes) == 4
    assert episodes[0]["title"] == "Episode with image"
    assert episodes[0]["image_url"] == "https://example.com/ep1.jpg"


@pytest.mark.asyncio
async def test_parse_rss_missing_image_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_httpx(monkeypatch, _RSS_WITH_ITUNES_IMAGE)
    episodes = await StreamService._parse_rss("http://example.com/feed.xml")

    no_image = next(e for e in episodes if e["title"] == "Episode without image")
    assert no_image["image_url"] is None


@pytest.mark.asyncio
async def test_parse_rss_rejects_non_http_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_httpx(monkeypatch, _RSS_WITH_ITUNES_IMAGE)
    episodes = await StreamService._parse_rss("http://example.com/feed.xml")

    js_ep = next(e for e in episodes if e["title"] == "Episode with javascript url")
    assert js_ep["image_url"] is None


@pytest.mark.asyncio
async def test_parse_rss_empty_href_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_httpx(monkeypatch, _RSS_WITH_ITUNES_IMAGE)
    episodes = await StreamService._parse_rss("http://example.com/feed.xml")

    empty_ep = next(e for e in episodes if e["title"] == "Episode with empty href")
    assert empty_ep["image_url"] is None


@pytest.mark.asyncio
async def test_parse_rss_without_itunes_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plain RSS without itunes namespace must still parse — image_url None."""
    _patch_httpx(monkeypatch, _RSS_PLAIN_NO_ITUNES)
    episodes = await StreamService._parse_rss("http://example.com/plain.xml")

    assert len(episodes) == 1
    assert episodes[0]["title"] == "Plain Episode"
    assert episodes[0]["image_url"] is None


@pytest.mark.asyncio
async def test_list_episodes_returns_image_url(
    stream_service: StreamService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: store an episode with image_url, list it back."""
    podcast = await stream_service.add_podcast("Img Pod", "http://example.com/img.xml")

    # Directly insert an episode with image_url (bypassing the mocked refresh)
    await stream_service._db.execute(
        "INSERT INTO podcast_episodes (podcast_id, title, audio_url, published, duration, image_url) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (podcast.id, "Ep1", "https://example.com/a.mp3", "2024-01-01", "600", "https://example.com/cover.jpg"),
    )
    await stream_service._db.commit()

    episodes = await stream_service.list_episodes(podcast.id)
    assert len(episodes) == 1
    assert episodes[0].image_url == "https://example.com/cover.jpg"
