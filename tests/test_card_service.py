"""Tests for the card service."""

import asyncio
import time

import aiosqlite
import pytest

from core.hardware.rfid import MockRfidReader
from core.services.card_service import CardMapping, CardService
from core.services.event_bus import EventBus


@pytest.fixture
def mock_reader() -> MockRfidReader:
    return MockRfidReader()


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.mark.asyncio
async def test_crud_mapping(tmp_path, mock_reader, event_bus) -> None:
    db = await aiosqlite.connect(str(tmp_path / "test.db"))
    service = CardService(mock_reader, event_bus, db)
    await service.start()

    # Create
    mapping = CardMapping(
        card_id="aabbccdd",
        name="Die drei ???",
        content_type="folder",
        content_path="Die drei Fragezeichen/Folge 1",
    )
    await service.set_mapping(mapping)

    # Read
    result = await service.get_mapping("aabbccdd")
    assert result is not None
    assert result.name == "Die drei ???"
    assert result.content_type == "folder"

    # Update
    mapping.name = "Die drei ??? Kids"
    await service.set_mapping(mapping)
    result = await service.get_mapping("aabbccdd")
    assert result.name == "Die drei ??? Kids"

    # List
    all_cards = await service.list_mappings()
    assert len(all_cards) == 1

    # Delete
    assert await service.delete_mapping("aabbccdd") is True
    assert await service.get_mapping("aabbccdd") is None

    service._scan_task.cancel()
    try:
        await service._scan_task
    except asyncio.CancelledError:
        pass
    await db.close()


@pytest.mark.asyncio
async def test_card_scanned_event(tmp_path, mock_reader, event_bus) -> None:
    db = await aiosqlite.connect(str(tmp_path / "test.db"))
    service = CardService(mock_reader, event_bus, db, rescan_cooldown=0.1)
    await service.start()

    # Set up a mapping
    mapping = CardMapping(
        card_id="11223344",
        name="Bibi Blocksberg",
        content_type="folder",
        content_path="Bibi Blocksberg",
    )
    await service.set_mapping(mapping)

    # Track events
    events = []

    async def on_scanned(**kwargs):
        events.append(kwargs)

    event_bus.subscribe("card_scanned", on_scanned)

    # Simulate card placement
    mock_reader.simulate_card("11223344")
    await asyncio.sleep(0.5)

    assert len(events) >= 1
    assert events[0]["card_id"] == "11223344"

    service._scan_task.cancel()
    try:
        await service._scan_task
    except asyncio.CancelledError:
        pass
    await db.close()


@pytest.mark.asyncio
async def test_unknown_card_ignored(tmp_path, mock_reader, event_bus) -> None:
    db = await aiosqlite.connect(str(tmp_path / "test.db"))
    service = CardService(mock_reader, event_bus, db)
    await service.start()

    scanned_events = []
    unknown_events = []

    async def on_scanned(**kwargs):
        scanned_events.append(kwargs)

    async def on_unknown(**kwargs):
        unknown_events.append(kwargs)

    event_bus.subscribe("card_scanned", on_scanned)
    event_bus.subscribe("card_unknown", on_unknown)

    mock_reader.simulate_card("unknown_id")
    await asyncio.sleep(0.5)

    assert len(scanned_events) == 0
    assert len(unknown_events) >= 1

    service._scan_task.cancel()
    try:
        await service._scan_task
    except asyncio.CancelledError:
        pass
    await db.close()


@pytest.mark.asyncio
async def test_resume_position(tmp_path, mock_reader, event_bus) -> None:
    db = await aiosqlite.connect(str(tmp_path / "test.db"))
    service = CardService(mock_reader, event_bus, db)
    await service.start()

    mapping = CardMapping(
        card_id="aabb",
        name="Hörbuch",
        content_type="folder",
        content_path="hoerbuch",
    )
    await service.set_mapping(mapping)
    await service.update_resume_position("aabb", 123.5)

    result = await service.get_mapping("aabb")
    assert result.resume_position == 123.5

    service._scan_task.cancel()
    try:
        await service._scan_task
    except asyncio.CancelledError:
        pass
    await db.close()
