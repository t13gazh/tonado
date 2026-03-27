"""Tests for the event bus."""

import pytest

from core.services.event_bus import EventBus


@pytest.mark.asyncio
async def test_publish_calls_handler(event_bus: EventBus) -> None:
    received = []

    async def handler(**kwargs):
        received.append(kwargs)

    event_bus.subscribe("test_event", handler)
    await event_bus.publish("test_event", foo="bar", num=42)

    assert len(received) == 1
    assert received[0] == {"foo": "bar", "num": 42}


@pytest.mark.asyncio
async def test_multiple_handlers(event_bus: EventBus) -> None:
    results = []

    async def handler_a(**kwargs):
        results.append("a")

    async def handler_b(**kwargs):
        results.append("b")

    event_bus.subscribe("evt", handler_a)
    event_bus.subscribe("evt", handler_b)
    await event_bus.publish("evt")

    assert sorted(results) == ["a", "b"]


@pytest.mark.asyncio
async def test_no_handlers(event_bus: EventBus) -> None:
    # Should not raise
    await event_bus.publish("nonexistent_event")


@pytest.mark.asyncio
async def test_unsubscribe(event_bus: EventBus) -> None:
    called = False

    async def handler(**kwargs):
        nonlocal called
        called = True

    event_bus.subscribe("evt", handler)
    event_bus.unsubscribe("evt", handler)
    await event_bus.publish("evt")

    assert not called


@pytest.mark.asyncio
async def test_handler_error_does_not_break_others(event_bus: EventBus) -> None:
    results = []

    async def bad_handler(**kwargs):
        raise ValueError("boom")

    async def good_handler(**kwargs):
        results.append("ok")

    event_bus.subscribe("evt", bad_handler)
    event_bus.subscribe("evt", good_handler)
    await event_bus.publish("evt")

    assert results == ["ok"]
