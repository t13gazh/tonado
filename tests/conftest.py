"""Shared test fixtures."""

import asyncio
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite
import pytest
import pytest_asyncio

from core.services.config_service import ConfigService
from core.services.event_bus import EventBus


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest_asyncio.fixture
async def tmp_db(tmp_path: Path) -> AsyncGenerator[aiosqlite.Connection, None]:
    db_path = tmp_path / "test.db"
    db = await aiosqlite.connect(str(db_path))
    await db.execute("PRAGMA journal_mode=WAL")
    yield db
    await db.close()


@pytest_asyncio.fixture
async def config_service(tmp_path: Path) -> AsyncGenerator[ConfigService, None]:
    db_path = tmp_path / "config.db"
    service = ConfigService(db_path)
    await service.start()
    yield service
    await service.stop()
