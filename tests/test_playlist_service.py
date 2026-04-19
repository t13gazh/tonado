"""Tests for the playlist service (H6)."""

from pathlib import Path

import aiosqlite
import pytest

from core.schemas.common import ContentType
from core.services.playlist_service import DuplicatePlaylistName, PlaylistService


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


@pytest.mark.asyncio
async def test_summary_exposes_created_at(service: PlaylistService) -> None:
    """Summary must include created_at so frontend can sort by recency."""
    p = await service.create_playlist("Recent")
    summary = p.to_summary()
    # create_playlist() does not fetch the row back, so created_at is None
    # until the playlist is listed again. Verify list_playlists() populates it.
    listed = await service.list_playlists()
    mine = next(pl for pl in listed if pl.id == p.id)
    assert "created_at" in mine.to_summary()
    assert mine.created_at is not None
    # Default SQLite TIMESTAMP is 'YYYY-MM-DD HH:MM:SS'
    assert len(mine.created_at) >= 10
    assert summary["id"] == p.id


@pytest.mark.asyncio
async def test_get_playlist_includes_created_at(service: PlaylistService) -> None:
    """get_playlist() must populate created_at so single-playlist views can sort/display it.

    Complements test_summary_exposes_created_at which only covers list_playlists().
    Without this, frontends that fetch a playlist by id would see created_at=None.
    """
    p = await service.create_playlist("WithTimestamp")
    fetched = await service.get_playlist(p.id)
    assert fetched is not None
    assert fetched.created_at is not None
    # Default SQLite TIMESTAMP is 'YYYY-MM-DD HH:MM:SS' — at least 10 chars.
    assert len(fetched.created_at) >= 10


@pytest.mark.asyncio
async def test_create_rejects_duplicate_case_insensitive(service: PlaylistService) -> None:
    """F1: creating a second playlist with a case-variant name must raise."""
    await service.create_playlist("Favoriten")
    with pytest.raises(DuplicatePlaylistName):
        await service.create_playlist("favoriten")
    with pytest.raises(DuplicatePlaylistName):
        await service.create_playlist("FAVORITEN")


@pytest.mark.asyncio
async def test_rename_rejects_duplicate_case_insensitive(service: PlaylistService) -> None:
    """F1: renaming onto an existing name (other case) must raise."""
    await service.create_playlist("Alpha")
    b = await service.create_playlist("Beta")
    with pytest.raises(DuplicatePlaylistName):
        await service.rename_playlist(b.id, "alpha")


@pytest.mark.asyncio
async def test_rename_to_own_name_different_case_is_allowed(service: PlaylistService) -> None:
    """Changing only the case of one's own playlist must not collide with itself."""
    p = await service.create_playlist("Mix")
    ok = await service.rename_playlist(p.id, "MIX")
    assert ok is True
    got = await service.get_playlist(p.id)
    assert got is not None and got.name == "MIX"
