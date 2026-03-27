"""Playlist service for user-created playlists.

Playlists are ordered collections of tracks (folder paths or stream URLs).
Stored in SQLite alongside other config.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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


@dataclass
class PlaylistItem:
    id: int
    position: int
    content_type: str  # "track", "folder", "stream"
    content_path: str
    title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "position": self.position,
            "content_type": self.content_type,
            "content_path": self.content_path,
            "title": self.title,
        }


@dataclass
class Playlist:
    id: int
    name: str
    items: list[PlaylistItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "item_count": len(self.items),
            "items": [i.to_dict() for i in self.items],
        }

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "item_count": len(self.items),
        }


class PlaylistService:
    """Manages user-created playlists."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def start(self) -> None:
        await self._db.executescript(_INIT_SQL)
        await self._db.commit()
        logger.info("Playlist service started")

    async def list_playlists(self) -> list[Playlist]:
        cursor = await self._db.execute(
            "SELECT id, name FROM playlists ORDER BY name"
        )
        playlists = []
        for row in await cursor.fetchall():
            p = Playlist(id=row[0], name=row[1])
            p.items = await self._get_items(p.id)
            playlists.append(p)
        return playlists

    async def get_playlist(self, playlist_id: int) -> Playlist | None:
        cursor = await self._db.execute(
            "SELECT id, name FROM playlists WHERE id = ?", (playlist_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        p = Playlist(id=row[0], name=row[1])
        p.items = await self._get_items(p.id)
        return p

    async def create_playlist(self, name: str) -> Playlist:
        cursor = await self._db.execute(
            "INSERT INTO playlists (name) VALUES (?)", (name,)
        )
        await self._db.commit()
        return Playlist(id=cursor.lastrowid or 0, name=name)

    async def delete_playlist(self, playlist_id: int) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM playlists WHERE id = ?", (playlist_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def rename_playlist(self, playlist_id: int, name: str) -> bool:
        cursor = await self._db.execute(
            "UPDATE playlists SET name = ? WHERE id = ?", (name, playlist_id)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def add_item(
        self,
        playlist_id: int,
        content_type: str,
        content_path: str,
        title: str | None = None,
    ) -> PlaylistItem | None:
        # Get next position
        cursor = await self._db.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 FROM playlist_items WHERE playlist_id = ?",
            (playlist_id,),
        )
        row = await cursor.fetchone()
        position = row[0] if row else 1

        cursor = await self._db.execute(
            "INSERT INTO playlist_items (playlist_id, position, content_type, content_path, title) "
            "VALUES (?, ?, ?, ?, ?)",
            (playlist_id, position, content_type, content_path, title),
        )
        await self._db.commit()
        return PlaylistItem(
            id=cursor.lastrowid or 0,
            position=position,
            content_type=content_type,
            content_path=content_path,
            title=title,
        )

    async def remove_item(self, item_id: int) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM playlist_items WHERE id = ?", (item_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def _get_items(self, playlist_id: int) -> list[PlaylistItem]:
        cursor = await self._db.execute(
            "SELECT id, position, content_type, content_path, title "
            "FROM playlist_items WHERE playlist_id = ? ORDER BY position",
            (playlist_id,),
        )
        return [
            PlaylistItem(id=row[0], position=row[1], content_type=row[2], content_path=row[3], title=row[4])
            for row in await cursor.fetchall()
        ]
