"""Tests for the backup service."""

import aiosqlite
import pytest

from core.services.backup_service import BackupService
from core.services.config_service import ConfigService


@pytest.fixture
async def backup_service(tmp_db: aiosqlite.Connection, config_service: ConfigService):
    service = BackupService(tmp_db, config_service)
    yield service, config_service, tmp_db


@pytest.mark.asyncio
async def test_export_backup(backup_service) -> None:
    service, config, db = backup_service

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

    backup = await service.export_backup()

    await db.execute("DELETE FROM cards")
    await db.execute("DELETE FROM config WHERE key = 'round.trip'")
    await db.commit()

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
    assert await config.get("auth.jwt_secret") == "original_secret"
    assert await config.get("normal.key") == "ok"


@pytest.mark.asyncio
async def test_import_validates_schema(backup_service) -> None:
    service, _, _ = backup_service

    # Missing required fields
    with pytest.raises(ValueError, match="Invalid backup"):
        await service.import_backup({
            "version": "1",
            "cards": [{"card_id": "x"}],  # missing name, content_type, content_path
        })

    # Not a dict
    with pytest.raises(ValueError, match="Invalid backup"):
        await service.import_backup({
            "version": "1",
            "cards": ["not a dict"],
        })


@pytest.mark.asyncio
async def test_import_rejects_unknown_version(backup_service) -> None:
    """M6: future versions must not silently import with undefined behaviour."""
    service, _, _ = backup_service
    with pytest.raises(ValueError, match="not supported"):
        await service.import_backup({
            "version": "99",
            "config": {},
            "cards": [],
            "radio_stations": [],
            "podcasts": [],
        })


@pytest.mark.asyncio
async def test_import_rejects_cover_path_traversal(backup_service) -> None:
    """M6: cover_path must be checked for traversal, not just content_path."""
    service, _, _ = backup_service
    data = {
        "version": "1",
        "config": {},
        "cards": [
            {
                "card_id": "x",
                "name": "x",
                "content_type": "folder",
                "content_path": "safe/path",
                "cover_path": "../../etc/passwd",
            }
        ],
        "radio_stations": [],
        "podcasts": [],
    }
    with pytest.raises(ValueError, match="cover_path"):
        await service.import_backup(data)


@pytest.mark.asyncio
async def test_import_rejects_absolute_content_path(backup_service) -> None:
    """M6: absolute paths are also dangerous, not only .."""
    service, _, _ = backup_service
    data = {
        "version": "1",
        "config": {},
        "cards": [
            {
                "card_id": "x",
                "name": "x",
                "content_type": "folder",
                "content_path": "/etc/shadow",
            }
        ],
        "radio_stations": [],
        "podcasts": [],
    }
    with pytest.raises(ValueError, match="content_path"):
        await service.import_backup(data)


@pytest.mark.asyncio
async def test_import_skips_audio_device(backup_service) -> None:
    """M6: hardware-specific keys (audio.*) must not cross boxes."""
    service, config, _ = backup_service
    await config.set("audio.device", "hw:original")

    data = {
        "version": "1",
        "config": {
            "audio.device": "hw:other-box",
            "player.max_volume": 70,
        },
        "cards": [],
        "radio_stations": [],
        "podcasts": [],
    }
    counts = await service.import_backup(data)
    # audio.device was skipped, player.max_volume was imported
    assert counts["config"] == 1
    assert await config.get("audio.device") == "hw:original"
    assert await config.get("player.max_volume") == 70
