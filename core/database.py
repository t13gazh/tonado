"""Centralized database manager — single SQLite connection for all services."""

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# All table schemas, collected from individual services.
_SCHEMA_SQL = """
-- Card mappings (from card_service)
CREATE TABLE IF NOT EXISTS cards (
    card_id TEXT PRIMARY KEY,
    name TEXT,
    content_type TEXT NOT NULL,
    content_path TEXT NOT NULL,
    cover_path TEXT,
    resume_position REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Key-value config (from config_service)
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    type TEXT DEFAULT 'string'
);

-- Radio stations (from stream_service)
CREATE TABLE IF NOT EXISTS radio_stations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    category TEXT DEFAULT 'custom',
    logo_url TEXT
);

-- Podcasts (from stream_service)
CREATE TABLE IF NOT EXISTS podcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    feed_url TEXT NOT NULL UNIQUE,
    last_checked TIMESTAMP,
    auto_download INTEGER DEFAULT 1,
    logo_url TEXT
);

-- Podcast episodes (from stream_service)
CREATE TABLE IF NOT EXISTS podcast_episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    podcast_id INTEGER NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    audio_url TEXT NOT NULL,
    published TEXT,
    duration TEXT,
    downloaded INTEGER DEFAULT 0,
    local_path TEXT,
    UNIQUE(podcast_id, audio_url)
);

-- Playlists (from playlist_service)
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Playlist items (from playlist_service)
CREATE TABLE IF NOT EXISTS playlist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    content_type TEXT NOT NULL,
    content_path TEXT NOT NULL,
    title TEXT,
    UNIQUE(playlist_id, position)
);
"""


class DatabaseManager:
    """Single database connection shared across all services."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def start(self) -> None:
        """Open database, enable WAL mode, and create all tables."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.executescript(_SCHEMA_SQL)
        await self._db.commit()
        logger.info("DatabaseManager started (db=%s)", self._db_path)

    async def stop(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def connection(self) -> aiosqlite.Connection:
        """Return the shared connection. Raises if not started."""
        if self._db is None:
            raise RuntimeError("DatabaseManager not started")
        return self._db
