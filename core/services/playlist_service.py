"""Playlist service for user-created playlists.

Playlists are ordered collections of tracks (folder paths or stream URLs).
Stored in SQLite alongside other config.
"""

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite

from core.schemas.common import ContentType
from core.services.base import BaseService

logger = logging.getLogger(__name__)





@dataclass
class PlaylistItem:
    id: int
    position: int
    content_type: ContentType
    content_path: str
    title: str | None = None
    duration_seconds: float = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration_seconds"] = round(self.duration_seconds)
        return d


@dataclass
class Playlist:
    id: int
    name: str
    items: list[PlaylistItem] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        return sum(i.duration_seconds for i in self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "item_count": len(self.items),
            "duration_seconds": round(self.total_duration),
            "items": [i.to_dict() for i in self.items],
        }

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "item_count": len(self.items),
            "duration_seconds": round(self.total_duration),
        }


class PlaylistService(BaseService):
    """Manages user-created playlists."""

    def __init__(self, db: aiosqlite.Connection, media_dir: Path | None = None) -> None:
        super().__init__()
        self._db = db
        self._media_dir = media_dir or Path.home() / "tonado" / "media"

    async def start(self) -> None:
        """Start playlist service (schema managed by DatabaseManager)."""
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
        content_type: ContentType,
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
        items = []
        for row in await cursor.fetchall():
            item = PlaylistItem(
                id=row[0], position=row[1], content_type=row[2],
                content_path=row[3], title=row[4],
            )
            item.duration_seconds = self._resolve_duration(item)
            items.append(item)
        return items

    def _resolve_duration(self, item: PlaylistItem) -> float:
        """Calculate duration for a playlist item based on its content."""
        from core.utils.audio import AUDIO_EXTENSIONS, get_duration

        content_path = self._media_dir / item.content_path

        if item.content_type == "folder" and content_path.is_dir():
            # Sum duration of all audio files in folder
            total = 0.0
            for f in content_path.iterdir():
                if f.suffix.lower() in AUDIO_EXTENSIONS:
                    total += get_duration(f)
            return total
        elif content_path.is_file() and content_path.suffix.lower() in AUDIO_EXTENSIONS:
            return get_duration(content_path)

        return 0
