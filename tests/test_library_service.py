"""Tests for the library service."""

from pathlib import Path

import pytest

from core.services.library_service import (
    DuplicateFolderName,
    FolderNotFound,
    InvalidFolderName,
    LibraryService,
    validate_folder_name,
)


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

    folders = await lib_service.list_folders()
    assert len(folders) == 2
    assert folders[0].name == "Album A"
    assert folders[0].track_count == 3
    assert folders[0].cover_path is not None
    assert folders[1].name == "Album B"
    assert folders[1].track_count == 5
    assert folders[1].cover_path is None
    # mtime populated so the frontend can sort by "newest first".
    assert folders[0].mtime > 0
    assert folders[1].mtime > 0


@pytest.mark.asyncio
async def test_folder_mtime_in_dict(lib_service: LibraryService) -> None:
    """mtime is serialised via to_dict() — frontend depends on it."""
    await lib_service.start()
    _create_album(lib_service._media_dir, "Album A", tracks=1)

    folders = await lib_service.list_folders()
    d = folders[0].to_dict()
    assert "mtime" in d
    assert isinstance(d["mtime"], (int, float))
    assert d["mtime"] > 0


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


# --- validate_folder_name ---------------------------------------------------


@pytest.mark.parametrize("bad_name", ["", "   ", "..", ".", "foo/bar", "a\\b",
                                       "a\x00b", "a<b", "a|b", "con", "PRN"])
def test_validate_folder_name_rejects(bad_name: str) -> None:
    with pytest.raises(InvalidFolderName):
        validate_folder_name(bad_name)


def test_validate_folder_name_trims() -> None:
    assert validate_folder_name("  Album  ") == "Album"


# --- rename_folder_checked --------------------------------------------------


@pytest.mark.asyncio
async def test_rename_folder_checked_happy(lib_service: LibraryService) -> None:
    await lib_service.start()
    _create_album(lib_service._media_dir, "Old Name", tracks=2)

    folder = lib_service.rename_folder_checked("Old Name", "New Name")
    assert folder.name == "New Name"
    assert (lib_service._media_dir / "New Name").is_dir()
    assert not (lib_service._media_dir / "Old Name").exists()


@pytest.mark.asyncio
async def test_rename_folder_checked_unknown(lib_service: LibraryService) -> None:
    await lib_service.start()
    with pytest.raises(FolderNotFound):
        lib_service.rename_folder_checked("missing", "whatever")


@pytest.mark.asyncio
async def test_rename_folder_checked_duplicate(lib_service: LibraryService) -> None:
    await lib_service.start()
    _create_album(lib_service._media_dir, "Alpha", tracks=1)
    _create_album(lib_service._media_dir, "Beta", tracks=1)
    with pytest.raises(DuplicateFolderName):
        lib_service.rename_folder_checked("Alpha", "Beta")


@pytest.mark.asyncio
async def test_rename_folder_checked_duplicate_case_insensitive(
    lib_service: LibraryService,
) -> None:
    await lib_service.start()
    _create_album(lib_service._media_dir, "Alpha", tracks=1)
    _create_album(lib_service._media_dir, "Beta", tracks=1)
    with pytest.raises(DuplicateFolderName):
        lib_service.rename_folder_checked("Alpha", "BETA")


@pytest.mark.asyncio
async def test_rename_folder_checked_invalid_name(lib_service: LibraryService) -> None:
    await lib_service.start()
    _create_album(lib_service._media_dir, "Alpha", tracks=1)
    for bad in ["", "   ", "..", "a/b", "a\\b", "a\x00b"]:
        with pytest.raises(InvalidFolderName):
            lib_service.rename_folder_checked("Alpha", bad)


@pytest.mark.asyncio
async def test_rename_folder_checked_case_only_self(
    lib_service: LibraryService,
) -> None:
    """Case-only rename is allowed even on case-insensitive filesystems."""
    await lib_service.start()
    _create_album(lib_service._media_dir, "Hoerspiele", tracks=1)
    folder = lib_service.rename_folder_checked("Hoerspiele", "hoerspiele")
    assert folder.name == "hoerspiele"
    # Directory now exists under the new casing. On case-insensitive FS the
    # "Hoerspiele" lookup would still succeed — that's expected semantics.
    assert (lib_service._media_dir / "hoerspiele").is_dir()
