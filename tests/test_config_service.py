"""Tests for the config service."""

import pytest

from core.services.config_service import ConfigService


@pytest.mark.asyncio
async def test_defaults_seeded(config_service: ConfigService) -> None:
    value = await config_service.get("player.startup_volume")
    assert value == 50


@pytest.mark.asyncio
async def test_set_and_get(config_service: ConfigService) -> None:
    await config_service.set("test.key", "hello")
    assert await config_service.get("test.key") == "hello"


@pytest.mark.asyncio
async def test_set_int(config_service: ConfigService) -> None:
    await config_service.set("test.number", 42)
    value = await config_service.get("test.number")
    assert value == 42
    assert isinstance(value, int)


@pytest.mark.asyncio
async def test_set_bool(config_service: ConfigService) -> None:
    await config_service.set("test.flag", True)
    assert await config_service.get("test.flag") is True

    await config_service.set("test.flag", False)
    assert await config_service.get("test.flag") is False


@pytest.mark.asyncio
async def test_set_float(config_service: ConfigService) -> None:
    await config_service.set("test.ratio", 3.14)
    value = await config_service.get("test.ratio")
    assert abs(value - 3.14) < 0.001


@pytest.mark.asyncio
async def test_get_nonexistent(config_service: ConfigService) -> None:
    assert await config_service.get("does.not.exist") is None


@pytest.mark.asyncio
async def test_delete(config_service: ConfigService) -> None:
    await config_service.set("temp.key", "value")
    assert await config_service.delete("temp.key") is True
    assert await config_service.get("temp.key") is None


@pytest.mark.asyncio
async def test_delete_nonexistent(config_service: ConfigService) -> None:
    assert await config_service.delete("nope") is False


@pytest.mark.asyncio
async def test_get_all(config_service: ConfigService) -> None:
    all_config = await config_service.get_all()
    assert "player.startup_volume" in all_config
    assert "gyro.enabled" in all_config


@pytest.mark.asyncio
async def test_overwrite(config_service: ConfigService) -> None:
    await config_service.set("key", "first")
    await config_service.set("key", "second")
    assert await config_service.get("key") == "second"
