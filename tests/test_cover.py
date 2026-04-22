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
from core.utils.audio import (
    _extract_cover,
    cover_cache_clear,
    cover_cache_stats,
    detect_image_mime,
    extract_cover,
)


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
    path = tmp_path / "noise.xyz"
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
    # Covers use a short max-age so that re-uploading a folder cover is visible
    # quickly; the ETag is the freshness signal, not a long cache window.
    assert "max-age=60" in resp.headers["cache-control"]
    assert resp.content == _TINY_JPEG


@pytest.mark.asyncio
async def test_cover_endpoint_track_prefers_folder_cover_over_embedded(cover_client) -> None:
    """An on-disk `cover.jpg` in the track's folder must win over ID3 embedded art.

    Rationale: re-uploading a folder cover should be visible on the player hero
    even when the MP3 itself carries a (possibly stale) APIC frame. This mirrors
    the folder-endpoint behaviour for the `kind=track` path.
    """
    client, media = cover_client
    album = media / "Album"
    album.mkdir()
    # Embedded PNG in the MP3, but a user-uploaded JPEG cover.jpg sits next to it.
    _make_mp3(album / "t01.mp3", cover=_TINY_PNG)
    (album / "cover.jpg").write_bytes(_TINY_JPEG)

    resp = await client.get("/api/library/cover", params={"path": "Album/t01.mp3", "kind": "track"})
    assert resp.status_code == 200
    # On-disk cover.jpg wins — the response must be the JPEG, not the embedded PNG.
    assert resp.content == _TINY_JPEG
    assert resp.headers["content-type"] == "image/jpeg"


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


# --- Byte-budgeted cache ---


def test_cover_cache_skips_oversized_covers(tmp_path: Path) -> None:
    """Covers above the per-item cap must not land in the cache (passthrough)."""
    cover_cache_clear()
    # Build three MP3s with >2 MB embedded JPEG payloads (one per track).
    big = _TINY_JPEG + b"\xff" * (3 * 1024 * 1024)  # 3 MB pseudo-jpeg body
    tracks = []
    for i in range(3):
        mp3 = tmp_path / f"big{i}.mp3"
        _make_mp3(mp3, cover=big)
        tracks.append(mp3)

    # Prime cache with each track.
    for mp3 in tracks:
        data = extract_cover(mp3)
        assert data is not None
        assert data.startswith(b"\xff\xd8\xff"), "payload must still round-trip"

    stats = cover_cache_stats()
    # Nothing over the per-item cap may be retained.
    assert stats["entries"] == 0
    assert stats["bytes"] == 0


def test_cover_cache_total_budget_evicts_lru(tmp_path: Path) -> None:
    """Total byte budget triggers LRU eviction when the next entry would overflow."""
    cover_cache_clear()
    # Each cover ~1.2 MB — cacheable individually, but three of them exceed
    # the 30 MB total *only* if we push beyond that. Shrink the cache for the
    # test instead of producing 100 MB fixtures: we use the public API but
    # monkey-patch the module-level caps.
    from core.utils import audio as audio_mod

    saved = audio_mod._cover_cache
    try:
        audio_mod._cover_cache = audio_mod._CoverCache(
            per_item_max=2 * 1024 * 1024,
            total_max=3 * 1024 * 1024,  # room for ~2 covers of 1.2 MB
            max_entries=100,
        )
        payload = _TINY_JPEG + b"\xee" * (1_200_000 - len(_TINY_JPEG))
        paths = []
        for i in range(3):
            mp3 = tmp_path / f"m{i}.mp3"
            _make_mp3(mp3, cover=payload)
            paths.append(mp3)
            extract_cover(mp3)

        stats = audio_mod._cover_cache.stats()
        # Oldest entry must have been evicted to make room.
        assert stats["entries"] <= 2
        assert stats["bytes"] <= 3 * 1024 * 1024
    finally:
        audio_mod._cover_cache = saved


# --- Opus (Vorbis-comment picture block) ---


def test_extract_cover_opus_with_picture(tmp_path: Path) -> None:
    """Opus files use the same metadata_block_picture mechanism as OggVorbis."""
    opus_fixture = Path(__file__).parent / "fixtures" / "silent.opus"
    if not opus_fixture.exists():
        pytest.skip("no .opus fixture available in this environment")
    from mutagen.oggopus import OggOpus

    dest = tmp_path / "song.opus"
    dest.write_bytes(opus_fixture.read_bytes())
    ogg = OggOpus(str(dest))
    pic = Picture()
    pic.type = 3
    pic.mime = "image/jpeg"
    pic.desc = "cover"
    pic.data = _TINY_JPEG
    ogg["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]
    ogg.save()

    data = _extract_cover(dest)
    assert data == _TINY_JPEG


def test_extract_cover_opus_missing_fixture_graceful(tmp_path: Path) -> None:
    """A bare/invalid .opus file must return None rather than crash."""
    path = tmp_path / "bad.opus"
    path.write_bytes(b"OggS" + b"\x00" * 64)  # nonsense Ogg header
    assert _extract_cover(path) is None


def test_extract_cover_wav_is_skipped(tmp_path: Path) -> None:
    """WAV has no standard embedded-cover slot: skip without raising."""
    path = tmp_path / "noise.wav"
    path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    assert _extract_cover(path) is None


# --- Case-insensitive folder cover ---


@pytest.mark.asyncio
async def test_folder_cover_case_insensitive(cover_client) -> None:
    """`Folder.JPG` (mixed case) must be picked up on case-sensitive filesystems."""
    client, media = cover_client
    album = media / "Album"
    album.mkdir()
    # Mixed-case basename + uppercase extension — would miss the old lower-case lookup.
    (album / "Folder.JPG").write_bytes(_TINY_JPEG)
    _make_mp3(album / "t01.mp3", cover=None)

    resp = await client.get("/api/library/cover", params={"path": "Album", "kind": "folder"})
    assert resp.status_code == 200
    assert resp.content == _TINY_JPEG


@pytest.mark.asyncio
async def test_folder_cover_prefers_cover_over_folder(cover_client) -> None:
    """When both `COVER.*` and `Folder.*` exist, prefer cover (regardless of case)."""
    client, media = cover_client
    album = media / "Album"
    album.mkdir()
    (album / "Folder.png").write_bytes(_TINY_PNG)
    (album / "COVER.jpg").write_bytes(_TINY_JPEG)

    resp = await client.get("/api/library/cover", params={"path": "Album", "kind": "folder"})
    assert resp.status_code == 200
    assert resp.content == _TINY_JPEG


# --- ETag ---


@pytest.mark.asyncio
async def test_cover_endpoint_sets_etag_and_no_immutable(cover_client) -> None:
    """ETag is present, Cache-Control is revalidateable (no `immutable`)."""
    client, media = cover_client
    album = media / "Album"
    album.mkdir()
    _make_mp3(album / "t01.mp3", cover=_TINY_JPEG)

    resp = await client.get("/api/library/cover", params={"path": "Album/t01.mp3", "kind": "track"})
    assert resp.status_code == 200
    etag = resp.headers.get("etag")
    assert etag, "ETag must be set on cover responses"
    cc = resp.headers["cache-control"]
    assert "immutable" not in cc
    # Short max-age keeps fresh cover uploads visible within a minute while
    # the ETag carries the strong freshness guarantee via conditional GET.
    assert "max-age=60" in cc
    assert "must-revalidate" in cc


@pytest.mark.asyncio
async def test_cover_endpoint_etag_changes_with_mtime(cover_client) -> None:
    """Rewriting the track updates mtime → ETag must change."""
    import os
    import time as _time

    client, media = cover_client
    album = media / "Album"
    album.mkdir()
    mp3 = album / "t01.mp3"
    _make_mp3(mp3, cover=_TINY_JPEG)

    r1 = await client.get("/api/library/cover", params={"path": "Album/t01.mp3", "kind": "track"})
    assert r1.status_code == 200
    etag1 = r1.headers["etag"]

    _time.sleep(0.02)
    _make_mp3(mp3, cover=_TINY_PNG)
    st = mp3.stat()
    os.utime(mp3, (st.st_atime, st.st_mtime + 2))

    r2 = await client.get("/api/library/cover", params={"path": "Album/t01.mp3", "kind": "track"})
    assert r2.status_code == 200
    etag2 = r2.headers["etag"]
    assert etag1 != etag2, "ETag must change when the source file changes"


@pytest.mark.asyncio
async def test_cover_endpoint_if_none_match_returns_304(cover_client) -> None:
    """A matching If-None-Match header produces a 304 with no body."""
    client, media = cover_client
    album = media / "Album"
    album.mkdir()
    _make_mp3(album / "t01.mp3", cover=_TINY_JPEG)

    r1 = await client.get("/api/library/cover", params={"path": "Album/t01.mp3", "kind": "track"})
    etag = r1.headers["etag"]

    r2 = await client.get(
        "/api/library/cover",
        params={"path": "Album/t01.mp3", "kind": "track"},
        headers={"If-None-Match": etag},
    )
    assert r2.status_code == 304
    # 304 must still carry the ETag so intermediate caches can confirm freshness.
    assert r2.headers.get("etag") == etag


# --- Public media_dir accessor ---


def test_library_service_exposes_media_dir(tmp_path: Path) -> None:
    """`media_dir` property returns the configured path without leaking writes."""
    svc = LibraryService(tmp_path)
    assert svc.media_dir == tmp_path
    # Property is read-only.
    with pytest.raises(AttributeError):
        svc.media_dir = tmp_path  # type: ignore[misc]
