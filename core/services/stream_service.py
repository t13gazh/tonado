"""Stream service for internet radio and podcast feeds.

Manages radio stream URLs, podcast RSS feeds, and provides
a pre-configured catalog of German children's radio stations.
"""

import asyncio
import logging
import defusedxml.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite
import httpx

from core.services.base import BaseService
from core.utils.url import SSRFError, validate_url

logger = logging.getLogger(__name__)




# Pre-configured German radio stations.
# Only direct MP3 stream URLs verified on Pi Zero W via MPD.
# CDN-based streams (addradio.de) fail on Pi Zero W due to DNS/TLS limitations.
_DEFAULT_STATIONS = [
    # Children's radio
    ("Die Maus (WDR)", "https://wdr-diemaus-live.icecast.wdr.de/wdr/diemaus/live/mp3/128/stream.mp3", "kinder", None),
    # General / parents
    ("N-JOY", "https://icecast.ndr.de/ndr/njoy/live/mp3/128/stream.mp3", "allgemein", None),
    ("NDR 2", "https://icecast.ndr.de/ndr/ndr2/niedersachsen/mp3/128/stream.mp3", "allgemein", None),
    ("Deutschlandfunk Kultur", "https://st02.sslstream.dlf.de/dlf/02/128/mp3/stream.mp3", "allgemein", None),
    ("SWR2", "https://liveradio.swr.de/sw282p3/swr2/play.mp3", "allgemein", None),
]

# Pre-configured German children's podcasts (verified feed URLs)
_DEFAULT_PODCASTS = [
    ("Betthupferl", "https://feeds.br.de/betthupferl/feed.xml"),
    ("CheckPod — Checker Tobi", "https://feeds.br.de/checkpod-der-podcast-mit-checker-tobi/feed.xml"),
    ("Anna und die wilden Tiere", "https://feeds.br.de/anna-und-die-wilden-tiere/feed.xml"),
    ("Lachlabor", "https://feeds.br.de/lachlabor/feed.xml"),
    ("Do Re Mikro", "https://feeds.br.de/do-re-mikro-die-musiksendung-fuer-kinder/feed.xml"),
    ("Die Maus zum Hören", "https://kinder.wdr.de/radio/diemaus/audio/diemaus-60/diemaus-60-106.podcast"),
]


@dataclass
class RadioStation:
    id: int
    name: str
    url: str
    category: str = "custom"
    logo_url: str | None = None


@dataclass
class Podcast:
    id: int
    name: str
    feed_url: str
    auto_download: bool = True
    logo_url: str | None = None
    episodes: list[dict] = field(default_factory=list)
    _episode_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "feed_url": self.feed_url,
            "auto_download": self.auto_download,
            "logo_url": self.logo_url,
            "episode_count": self._episode_count or len(self.episodes),
        }


@dataclass
class PodcastEpisode:
    id: int
    podcast_id: int
    title: str
    audio_url: str
    published: str | None = None
    duration: str | None = None
    downloaded: bool = False
    local_path: str | None = None


class StreamService(BaseService):
    """Manages internet radio stations and podcast feeds."""

    def __init__(self, db: aiosqlite.Connection, podcast_dir: Path | None = None) -> None:
        super().__init__()
        self._db = db
        self._podcast_dir = podcast_dir or Path.home() / "tonado" / "podcasts"
        self._refresh_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Seed default stations and podcasts (schema managed by DatabaseManager)."""
        await self._seed_stations()
        await self._seed_podcasts_metadata()
        self._podcast_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Stream service started")

        # Fetch podcast episodes in background — avoids blocking startup
        self._refresh_task = asyncio.create_task(self._refresh_seeded_podcasts())

    async def stop(self) -> None:
        """Cancel background refresh if still running."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass

    async def _seed_stations(self) -> None:
        """Insert default radio stations if table is empty."""
        cursor = await self._db.execute("SELECT COUNT(*) FROM radio_stations")
        row = await cursor.fetchone()
        if row and row[0] > 0:
            return

        for name, url, category, logo in _DEFAULT_STATIONS:
            await self._db.execute(
                "INSERT OR IGNORE INTO radio_stations (name, url, category, logo_url) VALUES (?, ?, ?, ?)",
                (name, url, category, logo),
            )
        await self._db.commit()
        logger.info("Seeded %d default radio stations", len(_DEFAULT_STATIONS))

    async def _seed_podcasts_metadata(self) -> None:
        """Insert default podcast metadata if table is empty (no network I/O)."""
        cursor = await self._db.execute("SELECT COUNT(*) FROM podcasts")
        row = await cursor.fetchone()
        if row and row[0] > 0:
            return
        for name, feed_url in _DEFAULT_PODCASTS:
            await self._db.execute(
                "INSERT OR IGNORE INTO podcasts (name, feed_url) VALUES (?, ?)",
                (name, feed_url),
            )
        await self._db.commit()
        logger.info("Seeded %d default podcasts", len(_DEFAULT_PODCASTS))

    async def _refresh_seeded_podcasts(self) -> None:
        """Fetch episodes for all podcasts — runs as background task after startup."""
        cursor = await self._db.execute("SELECT id FROM podcasts")
        rows = await cursor.fetchall()
        if not rows:
            return
        logger.info("Background: refreshing %d podcast feeds...", len(rows))
        for (pid,) in rows:
            try:
                await self.refresh_podcast(pid)
            except Exception as e:
                logger.warning("Failed to refresh podcast %d: %s", pid, e)
        logger.info("Background: podcast refresh complete")

    # --- Radio stations ---

    async def list_stations(self, category: str | None = None) -> list[RadioStation]:
        if category:
            cursor = await self._db.execute(
                "SELECT id, name, url, category, logo_url FROM radio_stations WHERE category = ? ORDER BY name",
                (category,),
            )
        else:
            cursor = await self._db.execute(
                "SELECT id, name, url, category, logo_url FROM radio_stations ORDER BY category, name"
            )
        return [RadioStation(*row) for row in await cursor.fetchall()]

    async def add_station(self, name: str, url: str, category: str = "custom") -> RadioStation:
        validate_url(url, resolve_dns=False)  # Validate scheme + IP; MPD fetches the stream
        cursor = await self._db.execute(
            "INSERT INTO radio_stations (name, url, category) VALUES (?, ?, ?)",
            (name, url, category),
        )
        await self._db.commit()
        return RadioStation(id=cursor.lastrowid or 0, name=name, url=url, category=category)

    async def delete_station(self, station_id: int) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM radio_stations WHERE id = ?", (station_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    # --- Podcasts ---

    async def list_podcasts(self) -> list[Podcast]:
        cursor = await self._db.execute(
            "SELECT p.id, p.name, p.feed_url, p.auto_download, p.logo_url, "
            "COUNT(e.id) as ep_count "
            "FROM podcasts p LEFT JOIN podcast_episodes e ON p.id = e.podcast_id "
            "GROUP BY p.id ORDER BY p.name"
        )
        podcasts = []
        for row in await cursor.fetchall():
            p = Podcast(id=row[0], name=row[1], feed_url=row[2], auto_download=bool(row[3]), logo_url=row[4])
            p._episode_count = row[5]
            podcasts.append(p)
        return podcasts

    async def add_podcast(self, name: str, feed_url: str, auto_download: bool = True) -> Podcast:
        validate_url(feed_url)  # Full validation with DNS check before fetching

        # Validate feed is reachable and parseable BEFORE inserting into DB
        await self._parse_rss(feed_url)

        cursor = await self._db.execute(
            "INSERT INTO podcasts (name, feed_url, auto_download) VALUES (?, ?, ?)",
            (name, feed_url, int(auto_download)),
        )
        await self._db.commit()
        podcast = Podcast(id=cursor.lastrowid or 0, name=name, feed_url=feed_url, auto_download=auto_download)

        # Fetch episodes (feed already validated, this should succeed)
        await self.refresh_podcast(podcast.id)
        return podcast

    async def delete_podcast(self, podcast_id: int) -> bool:
        cursor = await self._db.execute("DELETE FROM podcasts WHERE id = ?", (podcast_id,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def list_episodes(self, podcast_id: int) -> list[PodcastEpisode]:
        cursor = await self._db.execute(
            "SELECT id, podcast_id, title, audio_url, published, duration, downloaded, local_path "
            "FROM podcast_episodes WHERE podcast_id = ? ORDER BY published DESC",
            (podcast_id,),
        )
        return [
            PodcastEpisode(
                id=row[0], podcast_id=row[1], title=row[2], audio_url=row[3],
                published=row[4], duration=row[5], downloaded=bool(row[6]), local_path=row[7],
            )
            for row in await cursor.fetchall()
        ]

    async def refresh_podcast(self, podcast_id: int) -> int:
        """Fetch RSS feed and update episodes. Returns number of new episodes."""
        cursor = await self._db.execute(
            "SELECT feed_url FROM podcasts WHERE id = ?", (podcast_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return 0

        feed_url = row[0]
        try:
            episodes = await self._parse_rss(feed_url)
        except Exception as e:
            logger.error("Failed to fetch RSS feed %s: %s", feed_url, e)
            return 0

        new_count = 0
        for ep in episodes:
            try:
                await self._db.execute(
                    "INSERT OR IGNORE INTO podcast_episodes "
                    "(podcast_id, title, audio_url, published, duration) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (podcast_id, ep["title"], ep["audio_url"], ep.get("published"), ep.get("duration")),
                )
                new_count += 1
            except Exception:
                pass

        await self._db.execute(
            "UPDATE podcasts SET last_checked = CURRENT_TIMESTAMP WHERE id = ?",
            (podcast_id,),
        )
        await self._db.commit()
        logger.info("Refreshed podcast %d: %d episodes", podcast_id, new_count)
        return new_count

    @staticmethod
    async def _parse_rss(feed_url: str) -> list[dict]:
        """Parse an RSS feed and extract audio episodes."""
        validate_url(feed_url)  # SSRF check before fetching
        max_size = 5 * 1024 * 1024  # 5 MB limit to prevent XML bombs

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": "Tonado/0.1"},
            max_redirects=5,
        ) as client:
            resp = await client.get(feed_url)
            resp.raise_for_status()

        if len(resp.content) > max_size:
            raise ValueError(f"RSS feed too large: {len(resp.content)} bytes")

        root = ET.fromstring(resp.content)

        episodes = []
        for item in root.iter("item"):
            title_el = item.find("title")
            enclosure = item.find("enclosure")
            pub_date = item.find("pubDate")

            if title_el is None or enclosure is None:
                continue

            audio_url = enclosure.get("url", "")
            if not audio_url:
                continue

            # Try to get duration from itunes:duration
            duration = None
            for child in item:
                if "duration" in child.tag.lower():
                    duration = child.text
                    break

            episodes.append({
                "title": title_el.text or "Untitled",
                "audio_url": audio_url,
                "published": pub_date.text if pub_date is not None else None,
                "duration": duration,
            })

        return episodes[:50]  # Limit to 50 most recent
