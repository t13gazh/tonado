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
from core.services.system_service import VERSION

logger = logging.getLogger(__name__)


_SENSITIVE_KEY_EXACT = {"auth.jwt_secret", "auth.pin_hash.parent", "auth.pin_hash.expert"}

# Backup schema versions this service knows how to restore. A backup tagged
# with anything else is likely from a future Tonado build and importing it
# blindly would drop fields silently.
_KNOWN_BACKUP_VERSIONS = {"1"}

# Config keys that must not be overwritten during restore:
# - auth.*: secrets and PIN hashes — exported filtered, re-importing empty
#   would brick login
# - audio.*: tied to the hardware of the originating box (e.g. hw:1 =
#   HifiBerry). Restoring on a different Pi silences audio.
_RESTORE_CONFIG_SKIP_PREFIXES: tuple[str, ...] = ("auth.", "audio.")


class BackupService(BaseService):
    """Manages backup and restore of Tonado configuration."""

    def __init__(self, db: aiosqlite.Connection, config: ConfigService) -> None:
        super().__init__()
        self._db = db
        self._config = config

    @staticmethod
    def _is_sensitive(key: str) -> bool:
        """Check if a config key contains sensitive data."""
        if key in _SENSITIVE_KEY_EXACT:
            return True
        k = key.lower()
        return any(
            word in k
            for word in ("secret", "pin_hash", "password", "token", "private_key")
        )

    async def export_backup(self) -> dict[str, Any]:
        """Export all config and card mappings as a JSON-serializable dict.

        Sensitive keys (JWT secrets, PIN hashes, etc.) are excluded.
        """
        # Config — filter out secrets
        raw_config = await self._config.get_all()
        all_config = {k: v for k, v in raw_config.items() if not self._is_sensitive(k)}

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
            "tonado_version": VERSION,
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

    @staticmethod
    def _path_looks_unsafe(path: str) -> bool:
        """Reject parent-directory traversal, absolute paths, and Windows-style paths."""
        if not path:
            return False
        if ".." in path or path.startswith(("/", "~")) or "\\" in path:
            return True
        return False

    @staticmethod
    def _validate_backup(data: dict[str, Any]) -> list[str]:
        """Validate backup structure. Returns list of errors (empty = valid)."""
        errors: list[str] = []
        version = data.get("version")
        if not isinstance(version, str):
            errors.append("Missing or invalid 'version' field")
        elif version not in _KNOWN_BACKUP_VERSIONS:
            errors.append(
                f"Backup version '{version}' is not supported — "
                "maybe from a newer Tonado build"
            )
        for i, card in enumerate(data.get("cards", [])):
            if not isinstance(card, dict):
                errors.append(f"cards[{i}]: not a dict")
                continue
            for field in ("card_id", "name", "content_type", "content_path"):
                if not isinstance(card.get(field), str) or not card[field].strip():
                    errors.append(f"cards[{i}]: missing or empty '{field}'")
            for path_field in ("content_path", "cover_path"):
                path = card.get(path_field)
                if isinstance(path, str) and BackupService._path_looks_unsafe(path):
                    errors.append(
                        f"cards[{i}]: {path_field} contains path traversal or absolute path"
                    )
        for i, station in enumerate(data.get("radio_stations", [])):
            if not isinstance(station, dict):
                errors.append(f"radio_stations[{i}]: not a dict")
                continue
            for field in ("name", "url"):
                if not isinstance(station.get(field), str) or not station[field].strip():
                    errors.append(f"radio_stations[{i}]: missing or empty '{field}'")
        for i, podcast in enumerate(data.get("podcasts", [])):
            if not isinstance(podcast, dict):
                errors.append(f"podcasts[{i}]: not a dict")
                continue
            for field in ("name", "feed_url"):
                if not isinstance(podcast.get(field), str) or not podcast[field].strip():
                    errors.append(f"podcasts[{i}]: missing or empty '{field}'")
        if not isinstance(data.get("config", {}), dict):
            errors.append("'config' must be a dict")
        return errors

    async def import_backup(self, data: dict[str, Any]) -> dict[str, int]:
        """Import a backup, restoring config, cards, stations, and podcasts.

        Validates structure before importing. Returns counts of imported items.
        Raises ValueError if backup is malformed.
        """
        errors = self._validate_backup(data)
        if errors:
            raise ValueError(f"Invalid backup: {'; '.join(errors[:5])}")

        counts = {"config": 0, "cards": 0, "stations": 0, "podcasts": 0}

        # Restore config (skip auth secrets and hardware-specific keys)
        config_data = data.get("config", {})
        for key, value in config_data.items():
            if not isinstance(key, str):
                continue
            if any(key.startswith(prefix) for prefix in _RESTORE_CONFIG_SKIP_PREFIXES):
                # auth.*: never overwrite secrets / PIN hashes.
                # audio.*: originating box's hw:id likely doesn't exist on
                # this Pi, would silence playback.
                continue
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
