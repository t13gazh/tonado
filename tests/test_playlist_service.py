"""Tests for the playlist service (H6)."""

from pathlib import Path

import aiosqlite
import pytest

from core.schemas.common import ContentType
from core.services.playlist_service import PlaylistService


@pytest.fixture
async def service(tmp_db: aiosqlite.Connection, tmp_path: Path) -> PlaylistService:
    svc = PlaylistService(tmp_db, media_dir=tmp_path / "media")
    await svc.start()
    return svc


@pytest.mark.asyncio
async def test_create_and_list(service: PlaylistService) -> None:
    p = await service.create_playlist("Favoriten")
    assert p.id > 0
    assert p.name == "Favoriten"
    playlists = await service.list_playlists()
    assert any(pl.id == p.id for pl in playlists)


@pytest.mark.asyncio
async def test_rename(service: PlaylistService) -> None:
    p = await service.create_playlist("Alt")
    ok = await service.rename_playlist(p.id, "Neu")
    assert ok is True
    got = await service.get_playlist(p.id)
    assert got is not None and got.name == "Neu"


@pytest.mark.asyncio
async def test_rename_nonexistent_returns_false(service: PlaylistService) -> None:
    ok = await service.rename_playlist(99999, "nope")
    assert ok is False


@pytest.mark.asyncio
async def test_delete(service: PlaylistService) -> None:
    p = await service.create_playlist("Weg")
    ok = await service.delete_playlist(p.id)
    assert ok is True
    assert await service.get_playlist(p.id) is None


@pytest.mark.asyncio
async def test_add_item_assigns_sequential_positions(service: PlaylistService) -> None:
    p = await service.create_playlist("Mix")
    a = await service.add_item(p.id, ContentType.FOLDER, "albumA", "A")
    b = await service.add_item(p.id, ContentType.FOLDER, "albumB", "B")
    c = await service.add_item(p.id, ContentType.FOLDER, "albumC", "C")
    assert a is not None and b is not None and c is not None
    assert a.position == 1
    assert b.position == 2
    assert c.position == 3

    got = await service.get_playlist(p.id)
    assert got is not None
    assert [i.position for i in got.items] == [1, 2, 3]
    assert [i.title for i in got.items] == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_remove_item(service: PlaylistService) -> None:
    p = await service.create_playlist("Mix")
    a = await service.add_item(p.id, ContentType.FOLDER, "x", "x")
    assert a is not None
    ok = await service.remove_item(a.id)
    assert ok is True
    got = await service.get_playlist(p.id)
    assert got is not None and got.items == []


@pytest.mark.asyncio
async def test_remove_nonexistent_item(service: PlaylistService) -> None:
    assert await service.remove_item(99999) is False


@pytest.mark.asyncio
async def test_get_nonexistent_playlist(service: PlaylistService) -> None:
    assert await service.get_playlist(99999) is None


@pytest.mark.asyncio
async def test_list_summaries_include_item_count(service: PlaylistService) -> None:
    p = await service.create_playlist("Sum")
    await service.add_item(p.id, ContentType.FOLDER, "a", "a")
    await service.add_item(p.id, ContentType.FOLDER, "b", "b")

    lists = await service.list_playlists()
    mine = next(pl for pl in lists if pl.id == p.id)
    # Summaries must reflect items (list_playlists loads them)
    assert len(mine.items) == 2
