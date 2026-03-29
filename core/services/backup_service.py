"""Backup and restore service.

Exports config and card mappings as a single JSON file.
Imports/restores from a backup file.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from core.services.base import BaseService
from core.services.config_service import ConfigService

logger = logging.getLogger(__name__)


class BackupService(BaseService):
    """Manages backup and restore of Tonado configuration."""

    def __init__(self, db: aiosqlite.Connection, config: ConfigService) -> None:
        super().__init__()
        self._db = db
        self._config = config

    async def export_backup(self) -> dict[str, Any]:
        """Export all config and card mappings as a JSON-serializable dict."""
        # Config
        all_config = await self._config.get_all()

        # Cards
        cursor = await self._db.execute(
            "SELECT card_id, name, content_type, content_path, cover_path, resume_position "
            "FROM cards ORDER BY name"
        )
        cards = [
            {
                "card_id": row[0],
                "name": row[1],
                "content_type": row[2],
                "content_path": row[3],
                "cover_path": row[4],
                "resume_position": row[5] or 0,
            }
            for row in await cursor.fetchall()
        ]

        # Radio stations (custom only)
        cursor = await self._db.execute(
            "SELECT name, url, category FROM radio_stations WHERE category = 'custom'"
        )
        stations = [
            {"name": row[0], "url": row[1], "category": row[2]}
            for row in await cursor.fetchall()
        ]

        # Podcasts
        cursor = await self._db.execute(
            "SELECT name, feed_url, auto_download FROM podcasts"
        )
        podcasts = [
            {"name": row[0], "feed_url": row[1], "auto_download": bool(row[2])}
            for row in await cursor.fetchall()
        ]

        backup = {
            "version": "1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tonado_version": "0.1.0",
            "config": all_config,
            "cards": cards,
            "radio_stations": stations,
            "podcasts": podcasts,
        }

        logger.info(
            "Backup created: %d config keys, %d cards, %d stations, %d podcasts",
            len(all_config), len(cards), len(stations), len(podcasts),
        )
        return backup

    async def export_to_file(self, path: Path) -> Path:
        """Export backup to a JSON file."""
        data = await self.export_backup()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Backup written to %s", path)
        return path

    async def import_backup(self, data: dict[str, Any]) -> dict[str, int]:
        """Import a backup, restoring config, cards, stations, and podcasts.

        Returns counts of imported items.
        """
        counts = {"config": 0, "cards": 0, "stations": 0, "podcasts": 0}

        # Restore config (skip auth secrets)
        config_data = data.get("config", {})
        for key, value in config_data.items():
            if key.startswith("auth."):
                continue  # Don't overwrite auth settings
            await self._config.set(key, value)
            counts["config"] += 1

        # Restore cards
        for card in data.get("cards", []):
            await self._db.execute(
                "INSERT OR REPLACE INTO cards "
                "(card_id, name, content_type, content_path, cover_path, resume_position) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    card["card_id"],
                    card["name"],
                    card["content_type"],
                    card["content_path"],
                    card.get("cover_path"),
                    card.get("resume_position", 0),
                ),
            )
            counts["cards"] += 1

        # Restore custom radio stations
        for station in data.get("radio_stations", []):
            await self._db.execute(
                "INSERT OR IGNORE INTO radio_stations (name, url, category) VALUES (?, ?, ?)",
                (station["name"], station["url"], station.get("category", "custom")),
            )
            counts["stations"] += 1

        # Restore podcasts
        for podcast in data.get("podcasts", []):
            await self._db.execute(
                "INSERT OR IGNORE INTO podcasts (name, feed_url, auto_download) VALUES (?, ?, ?)",
                (podcast["name"], podcast["feed_url"], int(podcast.get("auto_download", True))),
            )
            counts["podcasts"] += 1

        await self._db.commit()

        logger.info(
            "Backup imported: %d config, %d cards, %d stations, %d podcasts",
            counts["config"], counts["cards"], counts["stations"], counts["podcasts"],
        )
        return counts

    async def import_from_file(self, path: Path) -> dict[str, int]:
        """Import backup from a JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return await self.import_backup(data)
