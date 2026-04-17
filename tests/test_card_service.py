"""Tests for the card service."""

import asyncio

import aiosqlite
import pytest

from core.hardware.rfid import MockRfidReader
from core.services.card_service import CardMapping, CardService
from core.services.event_bus import EventBus


@pytest.fixture
def mock_reader() -> MockRfidReader:
    return MockRfidReader()


@pytest.mark.asyncio
async def test_crud_mapping(tmp_db: aiosqlite.Connection, mock_reader, event_bus) -> None:
    service = CardService(mock_reader, event_bus, tmp_db)
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

    await service.stop()


@pytest.mark.asyncio
async def test_card_scanned_event(tmp_db: aiosqlite.Connection, mock_reader, event_bus) -> None:
    service = CardService(mock_reader, event_bus, tmp_db, rescan_cooldown=0.1)
    await service.start()

    mapping = CardMapping(
        card_id="11223344",
        name="Bibi Blocksberg",
        content_type="folder",
        content_path="Bibi Blocksberg",
    )
    await service.set_mapping(mapping)

    events = []

    async def on_scanned(**kwargs):
        events.append(kwargs)

    event_bus.subscribe("card_scanned", on_scanned)

    mock_reader.simulate_card("11223344")
    await asyncio.sleep(0.5)

    assert len(events) >= 1
    assert events[0]["card_id"] == "11223344"

    await service.stop()


@pytest.mark.asyncio
async def test_unknown_card_ignored(tmp_db: aiosqlite.Connection, mock_reader, event_bus) -> None:
    service = CardService(mock_reader, event_bus, tmp_db)
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

    await service.stop()


@pytest.mark.asyncio
async def test_cooldown_blocks_rapid_rescan_at_2s(
    tmp_db: aiosqlite.Connection, mock_reader, event_bus
) -> None:
    """M9: Product spec says 2s cooldown on the same card when it's re-placed.

    The scan loop filters duplicate continuous readings via _active_card_id,
    so the cooldown logic in _handle_card_placed only triggers when a card
    is physically removed and re-placed. We unit-test that branch directly.
    """
    service = CardService(mock_reader, event_bus, tmp_db, rescan_cooldown=2.0)
    await service.set_mapping(CardMapping(
        card_id="deadbeef", name="x", content_type="folder", content_path="x",
    ))
    events: list[dict] = []

    async def on_scanned(**kwargs):
        events.append(kwargs)

    event_bus.subscribe("card_scanned", on_scanned)

    # First placement — event fires
    now = 100.0
    await service._handle_card_placed("deadbeef", now)
    assert len(events) == 1

    # Re-placement 0.5s later — within cooldown → suppressed
    await service._handle_card_placed("deadbeef", now + 0.5)
    assert len(events) == 1, "re-scan within 2s cooldown must be suppressed"

    # Re-placement 2.1s later — past cooldown → event fires again
    await service._handle_card_placed("deadbeef", now + 2.1)
    assert len(events) == 2, "re-scan past 2s cooldown must produce an event"


@pytest.mark.asyncio
async def test_custom_cooldown_is_honoured(
    tmp_db: aiosqlite.Connection, mock_reader, event_bus
) -> None:
    """Cooldown value is picked up from the constructor kwarg (not hard-coded)."""
    service = CardService(mock_reader, event_bus, tmp_db, rescan_cooldown=5.0)
    await service.set_mapping(CardMapping(
        card_id="cafebabe", name="y", content_type="folder", content_path="y",
    ))
    events: list[dict] = []

    async def on_scanned(**kwargs):
        events.append(kwargs)

    event_bus.subscribe("card_scanned", on_scanned)

    now = 200.0
    await service._handle_card_placed("cafebabe", now)
    await service._handle_card_placed("cafebabe", now + 3.0)  # still inside 5s
    assert len(events) == 1


@pytest.mark.asyncio
async def test_resume_position(tmp_db: aiosqlite.Connection, mock_reader, event_bus) -> None:
    service = CardService(mock_reader, event_bus, tmp_db)
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

    await service.stop()
