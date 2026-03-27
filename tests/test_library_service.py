"""Tests for the library service."""

from pathlib import Path

import pytest

from core.services.library_service import LibraryService


@pytest.fixture
def lib_service(tmp_path: Path) -> LibraryService:
    media = tmp_path / "media"
    media.mkdir()
    return LibraryService(media)


def _create_album(media_dir: Path, name: str, tracks: int = 3, cover: bool = True) -> None:
    folder = media_dir / name
    folder.mkdir()
    for i in range(tracks):
        (folder / f"track{i+1:02d}.mp3").write_bytes(b"\x00" * 1024)
    if cover:
        (folder / "cover.jpg").write_bytes(b"\xff\xd8\xff\xe0")


@pytest.mark.asyncio
async def test_list_folders(lib_service: LibraryService) -> None:
    await lib_service.start()
    _create_album(lib_service._media_dir, "Album A", tracks=3)
    _create_album(lib_service._media_dir, "Album B", tracks=5, cover=False)

    folders = lib_service.list_folders()
    assert len(folders) == 2
    assert folders[0].name == "Album A"
    assert folders[0].track_count == 3
    assert folders[0].cover_path is not None
    assert folders[1].name == "Album B"
    assert folders[1].track_count == 5
    assert folders[1].cover_path is None


@pytest.mark.asyncio
async def test_list_tracks(lib_service: LibraryService) -> None:
    await lib_service.start()
    _create_album(lib_service._media_dir, "Test", tracks=2)

    tracks = lib_service.list_tracks("Test")
    assert len(tracks) == 2
    assert tracks[0].filename == "track01.mp3"


@pytest.mark.asyncio
async def test_create_and_delete_folder(lib_service: LibraryService) -> None:
    await lib_service.start()
    folder = lib_service.create_folder("New Album")
    assert folder.name == "New Album"
    assert (lib_service._media_dir / "New Album").is_dir()

    assert lib_service.delete_folder("New Album") is True
    assert not (lib_service._media_dir / "New Album").exists()


@pytest.mark.asyncio
async def test_rename_folder(lib_service: LibraryService) -> None:
    await lib_service.start()
    lib_service.create_folder("Old Name")
    assert lib_service.rename_folder("Old Name", "New Name") is True
    assert (lib_service._media_dir / "New Name").is_dir()
    assert not (lib_service._media_dir / "Old Name").exists()


@pytest.mark.asyncio
async def test_get_cover_path(lib_service: LibraryService) -> None:
    await lib_service.start()
    _create_album(lib_service._media_dir, "WithCover")
    cover = lib_service.get_cover_path("WithCover")
    assert cover is not None
    assert cover.name == "cover.jpg"


@pytest.mark.asyncio
async def test_disk_usage(lib_service: LibraryService) -> None:
    await lib_service.start()
    _create_album(lib_service._media_dir, "A", tracks=2)
    stats = lib_service.disk_usage()
    assert stats["file_count"] == 3  # 2 tracks + 1 cover
    assert stats["folder_count"] == 1
    assert stats["total_bytes"] > 0
