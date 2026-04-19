"""Audio file utilities shared across services."""

import base64
import logging
from functools import lru_cache
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
    Supports MP3 (APIC), FLAC (pictures), OGG Vorbis (metadata_block_picture), MP4/M4A (covr).
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

        if suffix == ".ogg":
            from mutagen.oggvorbis import OggVorbis
            from mutagen.flac import Picture
            ogg = OggVorbis(str(file_path))
            raw = ogg.get("metadata_block_picture", [])
            if not raw:
                return None
            # Pick FrontCover when multiple are present.
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

    except Exception as exc:
        logger.warning("Cover extraction failed for %s: %s", file_path, exc)
    return None


def _cover_key(file_path: Path) -> tuple[str, float, int] | None:
    """Cache key: path + mtime + size. Returns None if file doesn't exist."""
    try:
        st = file_path.stat()
        return (str(file_path), st.st_mtime, st.st_size)
    except OSError:
        return None


@lru_cache(maxsize=100)
def _cached_cover(key: tuple[str, float, int]) -> bytes | None:
    """Internal LRU-cached cover extractor, keyed by (path, mtime, size)."""
    return _extract_cover(Path(key[0]))


def extract_cover(file_path: Path) -> bytes | None:
    """Return embedded cover art, cached in-memory (LRU, 100 entries).

    Cache key includes mtime + size so edits invalidate automatically.
    """
    key = _cover_key(file_path)
    if key is None:
        return None
    return _cached_cover(key)
