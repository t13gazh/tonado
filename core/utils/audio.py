"""Audio file utilities shared across services."""

import base64
import logging
import threading
from collections import OrderedDict
from pathlib import Path

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".ogg", ".flac", ".wav", ".m4a", ".aac", ".opus", ".wma"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Mapping of image bytes' magic numbers to content type.
_MIME_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),  # Partial: WebP starts with "RIFF....WEBP"
    (b"GIF8", "image/gif"),
)


def detect_image_mime(data: bytes) -> str:
    """Sniff a common image mime type from raw bytes. Falls back to octet-stream."""
    if not data:
        return "application/octet-stream"
    for magic, mime in _MIME_MAGIC:
        if data.startswith(magic):
            # WebP check: "RIFF....WEBP"
            if mime == "image/webp" and not (len(data) >= 12 and data[8:12] == b"WEBP"):
                continue
            return mime
    return "application/octet-stream"


def get_duration(file_path: Path) -> float:
    """Get audio file duration in seconds using mutagen. Returns 0 on failure."""
    try:
        suffix = file_path.suffix.lower()
        # Use format-specific classes for reliable parsing
        if suffix == ".mp3":
            from mutagen.mp3 import MP3
            return MP3(str(file_path)).info.length
        elif suffix == ".ogg":
            from mutagen.oggvorbis import OggVorbis
            return OggVorbis(str(file_path)).info.length
        elif suffix == ".flac":
            from mutagen.flac import FLAC
            return FLAC(str(file_path)).info.length
        elif suffix in (".m4a", ".aac"):
            from mutagen.mp4 import MP4
            return MP4(str(file_path)).info.length
        elif suffix == ".opus":
            from mutagen.oggopus import OggOpus
            return OggOpus(str(file_path)).info.length
        elif suffix == ".wav":
            from mutagen.wave import WAVE
            return WAVE(str(file_path)).info.length
        else:
            from mutagen import File as MutagenFile
            audio = MutagenFile(str(file_path))
            if audio and audio.info:
                return audio.info.length
    except Exception:
        pass
    return 0


def _extract_cover(file_path: Path) -> bytes | None:
    """Extract embedded cover art from an audio file.

    Returns the raw image bytes, or None if no cover is embedded or extraction fails.
    Supports MP3 (APIC), FLAC (pictures), OGG Vorbis + Opus (metadata_block_picture),
    MP4/M4A (covr), ASF/WMA (WM/Picture). WAV has no standard embedded-cover slot and
    is skipped without crashing.
    Never raises — logs a warning on failure.
    """
    try:
        suffix = file_path.suffix.lower()
        if suffix == ".mp3":
            from mutagen.id3 import ID3, ID3NoHeaderError
            try:
                tags = ID3(str(file_path))
            except ID3NoHeaderError:
                return None
            apics = tags.getall("APIC")
            if not apics:
                return None
            # Prefer FrontCover (type=3); else first available.
            for apic in apics:
                if getattr(apic, "type", None) == 3:
                    return bytes(apic.data)
            return bytes(apics[0].data)

        if suffix == ".flac":
            from mutagen.flac import FLAC
            flac = FLAC(str(file_path))
            pics = flac.pictures
            if not pics:
                return None
            for pic in pics:
                if getattr(pic, "type", None) == 3:
                    return bytes(pic.data)
            return bytes(pics[0].data)

        if suffix in (".ogg", ".opus"):
            # Vorbis-comment-based: both OggVorbis and OggOpus use
            # `metadata_block_picture` (base64-encoded FLAC Picture block).
            from mutagen.flac import Picture
            if suffix == ".ogg":
                from mutagen.oggvorbis import OggVorbis
                ogg = OggVorbis(str(file_path))
            else:
                from mutagen.oggopus import OggOpus
                ogg = OggOpus(str(file_path))
            raw = ogg.get("metadata_block_picture", [])
            if not raw:
                return None
            front: bytes | None = None
            fallback: bytes | None = None
            for entry in raw:
                try:
                    pic = Picture(base64.b64decode(entry))
                except Exception:
                    continue
                if fallback is None:
                    fallback = bytes(pic.data)
                if getattr(pic, "type", None) == 3:
                    front = bytes(pic.data)
                    break
            return front or fallback

        if suffix in (".m4a", ".aac"):
            from mutagen.mp4 import MP4
            mp4 = MP4(str(file_path))
            covers = mp4.tags.get("covr") if mp4.tags else None
            if not covers:
                return None
            return bytes(covers[0])

        if suffix == ".wma":
            # ASF containers store cover art as WM/Picture attributes. The value
            # is a packed struct; mutagen exposes it as ASFByteArrayAttribute with
            # a `.value` bytes payload in ASF-picture format: <1-byte type>
            # <4-byte LE size> <null-terminated UTF-16LE mime> <null-terminated
            # UTF-16LE description> <image-bytes>.
            try:
                from mutagen.asf import ASF
            except Exception:
                return None
            asf = ASF(str(file_path))
            attrs = asf.tags.get("WM/Picture", []) if asf.tags else []
            if not attrs:
                return None
            for attr in attrs:
                raw = getattr(attr, "value", None)
                if not isinstance(raw, (bytes, bytearray)) or len(raw) < 10:
                    continue
                payload = _parse_asf_picture(bytes(raw))
                if payload is not None:
                    return payload
            return None

        if suffix == ".wav":
            # WAV has no standardized embedded-cover slot (ID3 chunks exist in
            # the wild but are non-portable). Skip gracefully.
            return None

    except Exception as exc:
        logger.warning("Cover extraction failed for %s: %s", file_path, exc)
    return None


def _parse_asf_picture(raw: bytes) -> bytes | None:
    """Parse an ASF WM/Picture attribute payload and return the image bytes.

    Layout: picture-type (1B) | size (4B LE) | mime UTF-16LE \0\0 | desc UTF-16LE \0\0 | image.
    Returns None if the structure is malformed.
    """
    try:
        idx = 1 + 4  # skip type + size
        # MIME string terminated by UTF-16 null (two zero bytes).
        end = raw.find(b"\x00\x00", idx)
        while end != -1 and (end - idx) % 2 != 0:
            end = raw.find(b"\x00\x00", end + 1)
        if end == -1:
            return None
        idx = end + 2
        # Description string, same termination rule.
        end = raw.find(b"\x00\x00", idx)
        while end != -1 and (end - idx) % 2 != 0:
            end = raw.find(b"\x00\x00", end + 1)
        if end == -1:
            return None
        idx = end + 2
        if idx >= len(raw):
            return None
        return bytes(raw[idx:])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Byte-budgeted cover cache
# ---------------------------------------------------------------------------

# Per-entry cap: covers larger than this are never cached (passthrough). 2 MB
# is generous for album art at reasonable JPEG/PNG quality and keeps a single
# rogue FLAC from wrecking the budget.
_COVER_PER_ITEM_MAX_BYTES = 2 * 1024 * 1024
# Total byte budget across all cached covers.
_COVER_TOTAL_MAX_BYTES = 30 * 1024 * 1024
# Upper bound on entry count — a safety net independent of byte budget.
_COVER_MAX_ENTRIES = 100


class _CoverCache:
    """Thread-safe LRU cover cache with per-item and total byte caps.

    Items over `_COVER_PER_ITEM_MAX_BYTES` are *not* stored at all (passthrough);
    each extraction for them re-reads the file. This keeps the Pi Zero W safe
    from 10 MB embedded covers blowing the RSS budget.
    """

    def __init__(
        self,
        per_item_max: int = _COVER_PER_ITEM_MAX_BYTES,
        total_max: int = _COVER_TOTAL_MAX_BYTES,
        max_entries: int = _COVER_MAX_ENTRIES,
    ) -> None:
        self._per_item_max = per_item_max
        self._total_max = total_max
        self._max_entries = max_entries
        self._store: "OrderedDict[tuple[str, float, int], bytes | None]" = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._bytes = 0

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._store),
                "bytes": self._bytes,
                "per_item_max": self._per_item_max,
                "total_max": self._total_max,
                "max_entries": self._max_entries,
            }

    def get_or_load(
        self,
        key: tuple[str, float, int],
        loader,
    ) -> bytes | None:
        """Return cached value for `key`, otherwise call `loader()` and cache if eligible."""
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                return self._store[key]

        # Load outside the lock — extraction can be slow (disk + mutagen).
        value = loader()

        with self._lock:
            # Another thread may have populated the same key concurrently.
            if key in self._store:
                self._store.move_to_end(key)
                return self._store[key]

            # `None` is free to cache: it's just the absence marker.
            size = len(value) if value is not None else 0

            # Oversized payload — do not cache; always re-extract.
            if size > self._per_item_max:
                return value

            # Evict until we have room for this entry (count + bytes).
            while (
                self._store
                and (
                    len(self._store) >= self._max_entries
                    or self._bytes + size > self._total_max
                )
            ):
                _, dropped = self._store.popitem(last=False)
                self._bytes -= len(dropped) if dropped is not None else 0
                if self._bytes < 0:
                    self._bytes = 0

            self._store[key] = value
            self._bytes += size
            return value


_cover_cache = _CoverCache()


def _cover_key(file_path: Path) -> tuple[str, float, int] | None:
    """Cache key: path + mtime + size. Returns None if file doesn't exist."""
    try:
        st = file_path.stat()
        return (str(file_path), st.st_mtime, st.st_size)
    except OSError:
        return None


def extract_cover(file_path: Path) -> bytes | None:
    """Return embedded cover art, byte-budgeted in-memory cache.

    Cache key includes mtime + size so edits invalidate automatically. Covers
    above ~2 MB bypass the cache and are re-read on every hit to avoid OOM on
    low-memory targets (Pi Zero W).
    """
    key = _cover_key(file_path)
    if key is None:
        return None
    return _cover_cache.get_or_load(key, lambda: _extract_cover(file_path))


def cover_cache_stats() -> dict[str, int]:
    """Expose cache stats (for tests / diagnostics)."""
    return _cover_cache.stats()


def cover_cache_clear() -> None:
    """Drop all cached covers (for tests)."""
    _cover_cache.clear()


def cover_etag(file_path: Path) -> str | None:
    """Build a weak ETag derived from mtime+size.

    Cheap and invalidates whenever the underlying file changes. Returns None
    when the file cannot be stat'd (caller should skip the header).
    """
    try:
        st = file_path.stat()
    except OSError:
        return None
    # Weak ETag — we do not guarantee byte-for-byte equality across encodings,
    # but mtime+size is stable for our cache-invalidation purposes.
    return f'W/"{int(st.st_mtime * 1000):x}-{st.st_size:x}"'
