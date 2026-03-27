"""Tests for the backup service."""

from pathlib import Path

import aiosqlite
import pytest

from core.services.backup_service import BackupService
from core.services.config_service import ConfigService


@pytest.fixture
async def backup_service(tmp_path: Path):
    db_path = tmp_path / "test.db"
    config = ConfigService(db_path)
    await config.start()

    db = await aiosqlite.connect(str(db_path))
    await db.execute("PRAGMA journal_mode=WAL")

    # Create cards table
    await db.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            card_id TEXT PRIMARY KEY, name TEXT, content_type TEXT NOT NULL,
            content_path TEXT NOT NULL, cover_path TEXT, resume_position REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS radio_stations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE, category TEXT DEFAULT 'custom', logo_url TEXT
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS podcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            feed_url TEXT NOT NULL UNIQUE, last_checked TIMESTAMP,
            auto_download INTEGER DEFAULT 1, logo_url TEXT
        )
    """)
    await db.commit()

    service = BackupService(db, config)
    yield service, config, db
    await db.close()
    await config.stop()


@pytest.mark.asyncio
async def test_export_backup(backup_service) -> None:
    service, config, db = backup_service

    # Add some data
    await config.set("test.key", "value")
    await db.execute(
        "INSERT INTO cards (card_id, name, content_type, content_path) VALUES (?, ?, ?, ?)",
        ("abc123", "Test Card", "folder", "test/path"),
    )
    await db.commit()

    backup = await service.export_backup()
    assert backup["version"] == "1"
    assert len(backup["cards"]) == 1
    assert backup["cards"][0]["card_id"] == "abc123"
    assert "test.key" in backup["config"]


@pytest.mark.asyncio
async def test_import_backup(backup_service) -> None:
    service, config, db = backup_service

    data = {
        "version": "1",
        "config": {"player.max_volume": 70, "test.imported": "yes"},
        "cards": [
            {"card_id": "imported1", "name": "Imported", "content_type": "folder", "content_path": "path"},
        ],
        "radio_stations": [],
        "podcasts": [],
    }

    counts = await service.import_backup(data)
    assert counts["config"] == 2
    assert counts["cards"] == 1

    # Verify data was imported
    assert await config.get("test.imported") == "yes"
    cursor = await db.execute("SELECT name FROM cards WHERE card_id = 'imported1'")
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "Imported"


@pytest.mark.asyncio
async def test_roundtrip(backup_service) -> None:
    service, config, db = backup_service

    await config.set("round.trip", "test")
    await db.execute(
        "INSERT INTO cards (card_id, name, content_type, content_path) VALUES (?, ?, ?, ?)",
        ("rt1", "Roundtrip", "stream", "http://example.com"),
    )
    await db.commit()

    # Export
    backup = await service.export_backup()

    # Clear
    await db.execute("DELETE FROM cards")
    await db.execute("DELETE FROM config WHERE key = 'round.trip'")
    await db.commit()

    # Import
    counts = await service.import_backup(backup)
    assert counts["cards"] >= 1

    cursor = await db.execute("SELECT name FROM cards WHERE card_id = 'rt1'")
    row = await cursor.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_auth_not_overwritten(backup_service) -> None:
    service, config, db = backup_service

    await config.set("auth.jwt_secret", "original_secret")

    data = {
        "version": "1",
        "config": {"auth.jwt_secret": "malicious_secret", "normal.key": "ok"},
        "cards": [],
        "radio_stations": [],
        "podcasts": [],
    }

    await service.import_backup(data)
    # Auth secret should NOT be overwritten
    assert await config.get("auth.jwt_secret") == "original_secret"
    assert await config.get("normal.key") == "ok"
