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
"""

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_AUDIO_EXTENSIONS = {".mp3", ".ogg", ".flac", ".wav", ".m4a", ".aac", ".opus", ".wma"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class MediaFolder:
    """A folder in the media library (= one album/audiobook)."""

    name: str
    path: str  # Relative path from media root (used by MPD)
    track_count: int = 0
    cover_path: str | None = None
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "track_count": self.track_count,
            "cover_path": self.cover_path,
            "size_bytes": self.size_bytes,
        }


@dataclass
class MediaTrack:
    """A single audio track."""

    filename: str
    path: str
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "path": self.path,
            "size_bytes": self.size_bytes,
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
            size = sum(f.stat().st_size for f in tracks)

            folders.append(MediaFolder(
                name=entry.name,
                path=entry.name,  # MPD relative path
                track_count=len(tracks),
                cover_path=f"/api/library/{entry.name}/cover" if cover else None,
                size_bytes=size,
            ))

        return folders

    def get_folder(self, folder_name: str) -> MediaFolder | None:
        """Get details for a specific folder."""
        folder_path = self._media_dir / folder_name
        if not folder_path.is_dir():
            return None

        tracks = [f for f in folder_path.iterdir() if f.suffix.lower() in _AUDIO_EXTENSIONS]
        cover = self._find_cover(folder_path)
        size = sum(f.stat().st_size for f in tracks)

        return MediaFolder(
            name=folder_name,
            path=folder_name,
            track_count=len(tracks),
            cover_path=f"/api/library/{folder_name}/cover" if cover else None,
            size_bytes=size,
        )

    def list_tracks(self, folder_name: str) -> list[MediaTrack]:
        """List all audio tracks in a folder."""
        folder_path = self._media_dir / folder_name
        if not folder_path.is_dir():
            return []

        tracks = []
        for f in sorted(folder_path.iterdir()):
            if f.suffix.lower() in _AUDIO_EXTENSIONS:
                tracks.append(MediaTrack(
                    filename=f.name,
                    path=f"{folder_name}/{f.name}",
                    size_bytes=f.stat().st_size,
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

        # Check for cover.* files first
        for ext in _IMAGE_EXTENSIONS:
            cover = folder_path / f"cover{ext}"
            if cover.exists():
                return cover

        # Fall back to any image file
        for f in folder_path.iterdir():
            if f.suffix.lower() in _IMAGE_EXTENSIONS:
                return f

        return None
