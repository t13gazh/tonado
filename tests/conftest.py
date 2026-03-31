"""Shared test fixtures."""

from pathlib import Path
from typing import AsyncGenerator

import aiosqlite
import pytest
import pytest_asyncio

from core.database import DatabaseManager
from core.services.config_service import ConfigService
from core.services.event_bus import EventBus


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest_asyncio.fixture
async def db_manager(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Provide a DatabaseManager with all tables created."""
    mgr = DatabaseManager(tmp_path / "test.db")
    await mgr.start()
    yield mgr
    await mgr.stop()


@pytest_asyncio.fixture
async def tmp_db(db_manager: DatabaseManager) -> aiosqlite.Connection:
    """Provide a raw DB connection with schema already applied."""
    return db_manager.connection


@pytest_asyncio.fixture
async def config_service(tmp_db: aiosqlite.Connection) -> AsyncGenerator[ConfigService, None]:
    """Provide a ConfigService backed by the shared test DB."""
    service = ConfigService(tmp_db)
    await service.start()
    yield service
    await service.stop()
