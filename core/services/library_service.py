"""Library service for browsing and managing the audio media directory.

Media layout:
  ~/tonado/media/
    ├── Die drei Fragezeichen/
    │   ├── cover.jpg
    │   ├── track01.mp3
    │   └── track02.mp3
    └── Bibi Blocksberg/
        └── ...

Each folder = one album/audiobook. cover.jpg is the album art.
Folder name is the title (no ID3 parsing — deliberate simplicity).
Duration is read from audio headers via mutagen.
"""

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_AUDIO_EXTENSIONS = {".mp3", ".ogg", ".flac", ".wav", ".m4a", ".aac", ".opus", ".wma"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _get_duration(file_path: Path) -> float:
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
        elif suffix == ".m4a" or suffix == ".aac":
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


@dataclass
class MediaFolder:
    """A folder in the media library (= one album/audiobook)."""

    name: str
    path: str  # Relative path from media root (used by MPD)
    track_count: int = 0
    cover_path: str | None = None
    duration_seconds: float = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "track_count": self.track_count,
            "cover_path": self.cover_path,
            "duration_seconds": round(self.duration_seconds),
        }


@dataclass
class MediaTrack:
    """A single audio track."""

    filename: str
    path: str
    duration_seconds: float = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "path": self.path,
            "duration_seconds": round(self.duration_seconds),
        }


class LibraryService:
    """Manages the audio media library on the filesystem."""

    def __init__(self, media_dir: Path) -> None:
        self._media_dir = media_dir

    async def start(self) -> None:
        self._media_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Library service started (media_dir=%s)", self._media_dir)

    def list_folders(self) -> list[MediaFolder]:
        """List all media folders (albums/audiobooks)."""
        folders: list[MediaFolder] = []
        if not self._media_dir.exists():
            return folders

        for entry in sorted(self._media_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            tracks = [f for f in entry.iterdir() if f.suffix.lower() in _AUDIO_EXTENSIONS]
            cover = self._find_cover(entry)
            total_duration = sum(_get_duration(f) for f in tracks)

            folders.append(MediaFolder(
                name=entry.name,
                path=entry.name,
                track_count=len(tracks),
                cover_path=f"/api/library/{entry.name}/cover" if cover else None,
                duration_seconds=total_duration,
            ))

        return folders

    def get_folder(self, folder_name: str) -> MediaFolder | None:
        """Get details for a specific folder."""
        folder_path = self._media_dir / folder_name
        if not folder_path.is_dir():
            return None

        tracks = [f for f in folder_path.iterdir() if f.suffix.lower() in _AUDIO_EXTENSIONS]
        cover = self._find_cover(folder_path)
        total_duration = sum(_get_duration(f) for f in tracks)

        return MediaFolder(
            name=folder_name,
            path=folder_name,
            track_count=len(tracks),
            cover_path=f"/api/library/{folder_name}/cover" if cover else None,
            duration_seconds=total_duration,
        )

    def list_tracks(self, folder_name: str) -> list[MediaTrack]:
        """List all audio tracks in a folder with durations."""
        folder_path = self._media_dir / folder_name
        if not folder_path.is_dir():
            return []

        tracks = []
        for f in sorted(folder_path.iterdir()):
            if f.suffix.lower() in _AUDIO_EXTENSIONS:
                tracks.append(MediaTrack(
                    filename=f.name,
                    path=f"{folder_name}/{f.name}",
                    duration_seconds=_get_duration(f),
                ))
        return tracks

    def get_cover_path(self, folder_name: str) -> Path | None:
        """Get the absolute path to a folder's cover image."""
        folder_path = self._media_dir / folder_name
        return self._find_cover(folder_path)

    def create_folder(self, folder_name: str) -> MediaFolder:
        """Create a new media folder."""
        folder_path = self._media_dir / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        logger.info("Created media folder: %s", folder_name)
        return MediaFolder(name=folder_name, path=folder_name)

    def delete_folder(self, folder_name: str) -> bool:
        """Delete a media folder and all its contents."""
        folder_path = self._media_dir / folder_name
        if not folder_path.is_dir():
            return False
        shutil.rmtree(folder_path)
        logger.info("Deleted media folder: %s", folder_name)
        return True

    def rename_folder(self, old_name: str, new_name: str) -> bool:
        """Rename a media folder."""
        old_path = self._media_dir / old_name
        new_path = self._media_dir / new_name
        if not old_path.is_dir() or new_path.exists():
            return False
        old_path.rename(new_path)
        logger.info("Renamed media folder: %s → %s", old_name, new_name)
        return True

    def get_upload_path(self, folder_name: str, filename: str) -> Path:
        """Get the target path for an uploaded file."""
        folder_path = self._media_dir / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        return folder_path / filename

    def disk_usage(self) -> dict[str, int]:
        """Get disk usage stats for the media directory."""
        total_size = 0
        file_count = 0
        folder_count = 0

        if self._media_dir.exists():
            for entry in self._media_dir.rglob("*"):
                if entry.is_file():
                    total_size += entry.stat().st_size
                    file_count += 1
                elif entry.is_dir() and not entry.name.startswith("."):
                    folder_count += 1

        return {
            "total_bytes": total_size,
            "file_count": file_count,
            "folder_count": folder_count,
        }

    @staticmethod
    def _find_cover(folder_path: Path) -> Path | None:
        """Find cover art in a folder. Prioritizes 'cover.*' then any image."""
        if not folder_path.is_dir():
            return None
        for ext in _IMAGE_EXTENSIONS:
            cover = folder_path / f"cover{ext}"
            if cover.exists():
                return cover
        for f in folder_path.iterdir():
            if f.suffix.lower() in _IMAGE_EXTENSIONS:
                return f
        return None
