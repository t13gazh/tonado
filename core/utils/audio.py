"""Audio file utilities shared across services."""

from pathlib import Path

AUDIO_EXTENSIONS = {".mp3", ".ogg", ".flac", ".wav", ".m4a", ".aac", ".opus", ".wma"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


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
