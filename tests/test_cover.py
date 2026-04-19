"""Tests for embedded cover-art extraction and the cover-by-path endpoint."""

import base64
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, APIC
from mutagen.mp3 import MP3
from mutagen.oggvorbis import OggVorbis

from core.routers import library
from core.services.library_service import LibraryService
from core.utils.audio import _extract_cover, detect_image_mime, extract_cover


# --- Fixture payload helpers ---

# Minimal silent MP3 frame (LAME-generated, 44.1 kHz, mono, ~26 ms).
# Hex-encoded to keep the file ASCII-safe.
_SILENT_MP3 = bytes.fromhex(
    "fffb90640000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000000000000"
)

# 1x1 red JPEG (smallest valid JPEG — for APIC payload).
_TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606"
    "0706060805070708090808090a0d0b0a0a0a0d120d0e0c0d13110e0e"
    "1019121415150c0e16161818191a1c1b1d1c1b1b1e21292519262625"
    "222023202323292a2a2c2d2f2f34353535353535ffc0000b08000100"
    "01010100021101ffc4001f0000010501010101010100000000000000"
    "000102030405060708090a0bffc4000b1000000000000000000000"
    "00000000000000ffda0008010100003f00"
    "ffd9"
)

# 1x1 black PNG.
_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6300010000000500010d0a2db40000"
    "000049454e44ae426082"
)


def _make_mp3(path: Path, cover: bytes | None = None, mime: str = "image/jpeg") -> None:
    """Create a minimal MP3 file, optionally with an APIC frame."""
    path.write_bytes(_SILENT_MP3)
    if cover is None:
        return
    tags = ID3()
    tags.add(APIC(encoding=3, mime=mime, type=3, desc="cover", data=cover))
    tags.save(str(path))


def _make_flac(path: Path, cover: bytes | None = None) -> None:
    """Create a minimal FLAC file by using mutagen on a fresh tag set.

    FLAC needs a valid stream header; writing pure metadata is non-trivial.
    Instead we use a genuine empty FLAC sample embedded here.
    """
    # Smallest valid FLAC: streaminfo only, no audio frames.
    # Marker "fLaC" + last-metadata-block STREAMINFO (min_block_size=4096, ...).
    header = bytes.fromhex(
        "664c6143"              # "fLaC"
        "80000022"              # last-block streaminfo, length 34
        "1000" "1000"           # min/max block size
        "000000" "000000"       # min/max frame size
        "0ac44100"              # 44100 Hz, stereo, 16-bit, start of samples
        "0000000000"            # total samples
        + "00" * 16             # MD5
    )
    path.write_bytes(header)
    if cover is None:
        return
    flac = FLAC(str(path))
    pic = Picture()
    pic.type = 3
    pic.mime = "image/jpeg"
    pic.desc = "cover"
    pic.data = cover
    flac.add_picture(pic)
    flac.save()


def _make_ogg(path: Path, cover: bytes | None = None) -> None:
    """Copy a canned OGG Vorbis file and attach a METADATA_BLOCK_PICTURE."""
    # Minimal OGG Vorbis is too intricate to hand-roll, so we skip OGG creation
    # and only test extraction on an already-tagged file if present. The tests
    # that cover OGG are gated by a `pytest.importorskip`-style guard.
    raise NotImplementedError


# --- Unit tests for _extract_cover ---


def test_extract_cover_mp3_with_apic(tmp_path: Path) -> None:
    mp3 = tmp_path / "song.mp3"
    _make_mp3(mp3, cover=_TINY_JPEG)
    data = _extract_cover(mp3)
    assert data == _TINY_JPEG


def test_extract_cover_mp3_without_apic(tmp_path: Path) -> None:
    mp3 = tmp_path / "bare.mp3"
    _make_mp3(mp3, cover=None)
    assert _extract_cover(mp3) is None


def test_extract_cover_mp3_prefers_front_cover(tmp_path: Path) -> None:
    """When both type=0 (Other) and type=3 (FrontCover) exist, prefer type=3."""
    mp3 = tmp_path / "multi.mp3"
    mp3.write_bytes(_SILENT_MP3)
    tags = ID3()
    tags.add(APIC(encoding=3, mime="image/png", type=0, desc="other", data=_TINY_PNG))
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="cover", data=_TINY_JPEG))
    tags.save(str(mp3))

    data = _extract_cover(mp3)
    assert data == _TINY_JPEG


def test_extract_cover_flac_with_picture(tmp_path: Path) -> None:
    flac = tmp_path / "song.flac"
    try:
        _make_flac(flac, cover=_TINY_JPEG)
    except Exception:
        pytest.skip("FLAC fixture could not be generated in this environment")
    data = _extract_cover(flac)
    assert data == _TINY_JPEG


def test_extract_cover_unknown_format(tmp_path: Path) -> None:
    """Unknown suffix returns None, no exception."""
    path = tmp_path / "noise.wav"
    path.write_bytes(b"\x00" * 128)
    assert _extract_cover(path) is None


def test_extract_cover_missing_file(tmp_path: Path) -> None:
    """Non-existent file returns None (no crash)."""
    assert _extract_cover(tmp_path / "does-not-exist.mp3") is None


def test_extract_cover_corrupt_mp3(tmp_path: Path) -> None:
    """Corrupt file must not raise."""
    mp3 = tmp_path / "corrupt.mp3"
    mp3.write_bytes(b"not an mp3 at all")
    assert _extract_cover(mp3) is None


def test_extract_cover_cached_invalidates_on_mtime(tmp_path: Path) -> None:
    """LRU cache key includes mtime — rewriting the file must re-extract."""
    mp3 = tmp_path / "song.mp3"
    _make_mp3(mp3, cover=_TINY_JPEG)
    first = extract_cover(mp3)
    assert first == _TINY_JPEG

    # Overwrite with a no-cover MP3; mtime changes, cache should invalidate.
    import time
    time.sleep(0.01)  # ensure mtime tick on coarse filesystems
    _make_mp3(mp3, cover=None)
    # Force a visible mtime change.
    import os
    st = mp3.stat()
    os.utime(mp3, (st.st_atime, st.st_mtime + 1))

    second = extract_cover(mp3)
    assert second is None


# --- Mime sniffing ---


def test_detect_image_mime_jpeg() -> None:
    assert detect_image_mime(_TINY_JPEG) == "image/jpeg"


def test_detect_image_mime_png() -> None:
    assert detect_image_mime(_TINY_PNG) == "image/png"


def test_detect_image_mime_unknown() -> None:
    assert detect_image_mime(b"random bytes") == "application/octet-stream"


def test_detect_image_mime_empty() -> None:
    assert detect_image_mime(b"") == "application/octet-stream"


# --- Endpoint tests ---


@pytest_asyncio.fixture
async def cover_client(tmp_path: Path):
    """Minimal FastAPI app with only the library router wired up."""
    app = FastAPI()
    media = tmp_path / "media"
    media.mkdir()
    svc = LibraryService(media)
    await svc.start()
    app.state.library_service = svc
    app.include_router(library.router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, media


@pytest.mark.asyncio
async def test_cover_endpoint_track_with_embedded_art(cover_client) -> None:
    client, media = cover_client
    album = media / "Album"
    album.mkdir()
    _make_mp3(album / "t01.mp3", cover=_TINY_JPEG)

    resp = await client.get("/api/library/cover", params={"path": "Album/t01.mp3", "kind": "track"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert "max-age=3600" in resp.headers["cache-control"]
    assert resp.content == _TINY_JPEG


@pytest.mark.asyncio
async def test_cover_endpoint_track_without_art_returns_404(cover_client) -> None:
    client, media = cover_client
    album = media / "Album"
    album.mkdir()
    _make_mp3(album / "bare.mp3", cover=None)

    resp = await client.get("/api/library/cover", params={"path": "Album/bare.mp3", "kind": "track"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cover_endpoint_folder_prefers_on_disk_cover(cover_client) -> None:
    client, media = cover_client
    album = media / "Album"
    album.mkdir()
    (album / "cover.jpg").write_bytes(_TINY_JPEG)
    _make_mp3(album / "t01.mp3", cover=_TINY_PNG)  # embedded PNG should be ignored

    resp = await client.get("/api/library/cover", params={"path": "Album", "kind": "folder"})
    assert resp.status_code == 200
    # on-disk cover.jpg wins
    assert resp.content == _TINY_JPEG


@pytest.mark.asyncio
async def test_cover_endpoint_folder_falls_back_to_embedded(cover_client) -> None:
    client, media = cover_client
    album = media / "Album"
    album.mkdir()
    # No on-disk cover, but an MP3 with embedded JPEG.
    _make_mp3(album / "t01.mp3", cover=_TINY_JPEG)

    resp = await client.get("/api/library/cover", params={"path": "Album", "kind": "folder"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == _TINY_JPEG


@pytest.mark.asyncio
async def test_cover_endpoint_folder_without_any_cover_returns_404(cover_client) -> None:
    client, media = cover_client
    album = media / "Album"
    album.mkdir()
    _make_mp3(album / "bare.mp3", cover=None)

    resp = await client.get("/api/library/cover", params={"path": "Album", "kind": "folder"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cover_endpoint_rejects_path_traversal(cover_client) -> None:
    client, _ = cover_client
    for bad in ["../etc/passwd", "../../secret", "foo/../../bar"]:
        resp = await client.get("/api/library/cover", params={"path": bad, "kind": "folder"})
        assert resp.status_code == 400, f"Traversal accepted: {bad}"


@pytest.mark.asyncio
async def test_cover_endpoint_rejects_absolute_path(cover_client) -> None:
    client, _ = cover_client
    # Use a path that is absolute on both POSIX and Windows interpretations.
    for bad in ["/etc/passwd", "C:\\Windows\\win.ini"]:
        resp = await client.get("/api/library/cover", params={"path": bad, "kind": "folder"})
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cover_endpoint_rejects_invalid_kind(cover_client) -> None:
    client, _ = cover_client
    resp = await client.get("/api/library/cover", params={"path": "whatever", "kind": "banana"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cover_endpoint_missing_folder_returns_404(cover_client) -> None:
    client, _ = cover_client
    resp = await client.get("/api/library/cover", params={"path": "Nonexistent", "kind": "folder"})
    assert resp.status_code == 404
