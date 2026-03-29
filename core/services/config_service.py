"""Config service backed by SQLite with WAL mode."""

import json
import logging
from typing import Any

import aiosqlite

from core.services.base import BaseService
from core.services.event_bus import EventBus

logger = logging.getLogger(__name__)

# Default configuration values
DEFAULTS: dict[str, tuple[Any, str]] = {
    # (value, type)
    "player.startup_volume": (50, "int"),
    "player.max_volume": (80, "int"),
    "card.rescan_cooldown": (2.0, "float"),
    "card.remove_pauses": (False, "bool"),
    "gyro.enabled": (True, "bool"),
    "gyro.sensitivity": ("normal", "string"),
    "sleep_timer.enabled": (False, "bool"),
    "sleep_timer.minutes": (30, "int"),
    "system.idle_shutdown_minutes": (0, "int"),
}


class ConfigService(BaseService):
    """Key-value config store with typed values and defaults."""

    def __init__(self, db: aiosqlite.Connection, event_bus: EventBus | None = None) -> None:
        super().__init__()
        self._db: aiosqlite.Connection = db
        self._event_bus = event_bus

    async def start(self) -> None:
        """Seed default config values."""
        await self._seed_defaults()
        logger.info("Config service started")

    async def stop(self) -> None:
        """No-op — database lifecycle managed by DatabaseManager."""
        pass

    async def _seed_defaults(self) -> None:
        """Insert default values for keys that don't exist yet."""
        assert self._db is not None
        for key, (value, type_) in DEFAULTS.items():
            existing = await self._db.execute(
                "SELECT 1 FROM config WHERE key = ?", (key,)
            )
            if await existing.fetchone() is None:
                encoded = self._encode(value, type_)
                await self._db.execute(
                    "INSERT INTO config (key, value, type) VALUES (?, ?, ?)",
                    (key, encoded, type_),
                )
        await self._db.commit()

    async def get(self, key: str) -> Any:
        """Get a config value. Returns default if key exists in DEFAULTS."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT value, type FROM config WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        if row is None:
            if key in DEFAULTS:
                return DEFAULTS[key][0]
            return None
        return self._decode(row[0], row[1])

    async def set(self, key: str, value: Any) -> None:
        """Set a config value and notify subscribers."""
        assert self._db is not None
        type_ = self._infer_type(value)
        encoded = self._encode(value, type_)
        await self._db.execute(
            "INSERT OR REPLACE INTO config (key, value, type) VALUES (?, ?, ?)",
            (key, encoded, type_),
        )
        await self._db.commit()
        if self._event_bus:
            await self._event_bus.publish("config_changed", key=key, value=value)

    async def get_all(self) -> dict[str, Any]:
        """Get all config values as a dictionary."""
        assert self._db is not None
        cursor = await self._db.execute("SELECT key, value, type FROM config")
        rows = await cursor.fetchall()
        return {row[0]: self._decode(row[1], row[2]) for row in rows}

    async def delete(self, key: str) -> bool:
        """Delete a config key. Returns True if key existed."""
        assert self._db is not None
        cursor = await self._db.execute("DELETE FROM config WHERE key = ?", (key,))
        await self._db.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _encode(value: Any, type_: str) -> str:
        if type_ == "bool":
            return "1" if value else "0"
        if type_ == "json":
            return json.dumps(value)
        return str(value)

    @staticmethod
    def _decode(value: str, type_: str) -> Any:
        match type_:
            case "int":
                return int(value)
            case "float":
                return float(value)
            case "bool":
                return value == "1"
            case "json":
                return json.loads(value)
            case _:
                return value

    @staticmethod
    def _infer_type(value: Any) -> str:
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, (dict, list)):
            return "json"
        return "string"
