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

import asyncio
import logging
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.services.base import BaseService
from core.utils.audio import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, get_duration

logger = logging.getLogger(__name__)


@dataclass
class MediaFolder:
    """A folder in the media library (= one album/audiobook)."""

    name: str
    path: str  # Relative path from media root (used by MPD)
    track_count: int = 0
    cover_path: str | None = None
    duration_seconds: float = 0
    mtime: float = 0  # Folder modification timestamp (unix seconds); drives "newest first" sort.

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration_seconds"] = round(self.duration_seconds)
        return d


@dataclass
class MediaTrack:
    """A single audio track."""

    filename: str
    path: str
    duration_seconds: float = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration_seconds"] = round(self.duration_seconds)
        return d


class LibraryService(BaseService):
    """Manages the audio media library on the filesystem."""

    def __init__(self, media_dir: Path) -> None:
        super().__init__()
        self._media_dir = media_dir

    @property
    def media_dir(self) -> Path:
        """Read-only view of the media root. Routers use this for path resolution.

        Exposing the attribute through a property keeps the underlying field
        private (no external writes) while preventing callers from reaching
        into `_media_dir` directly.
        """
        return self._media_dir

    async def start(self) -> None:
        self._media_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Library service started (media_dir=%s)", self._media_dir)

    async def list_folders(self) -> list[MediaFolder]:
        """List all media folders (albums/audiobooks).

        Runs the IO-intensive scanning (directory iteration + mutagen duration
        parsing) in a thread-pool executor so the event loop stays responsive.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._list_folders_sync)

    def _list_folders_sync(self) -> list[MediaFolder]:
        """Synchronous implementation of list_folders (runs in executor)."""
        folders: list[MediaFolder] = []
        if not self._media_dir.exists():
            return folders

        for entry in sorted(self._media_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            tracks = [f for f in entry.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS]
            cover = self._find_cover(entry)
            total_duration = sum(get_duration(f) for f in tracks)
            # Folder mtime: use max mtime of contents (audio + cover) to reflect
            # "when did this album last change"; fall back to directory mtime.
            try:
                content_mtimes = [f.stat().st_mtime for f in tracks]
                if cover:
                    content_mtimes.append(cover.stat().st_mtime)
                mtime = max(content_mtimes) if content_mtimes else entry.stat().st_mtime
            except OSError:
                mtime = 0

            folders.append(MediaFolder(
                name=entry.name,
                path=entry.name,
                track_count=len(tracks),
                cover_path=f"/api/library/{entry.name}/cover" if cover else None,
                duration_seconds=total_duration,
                mtime=mtime,
            ))

        return folders

    def get_folder(self, folder_name: str) -> MediaFolder | None:
        """Get details for a specific folder."""
        folder_path = self._media_dir / folder_name
        if not folder_path.is_dir():
            return None

        tracks = [f for f in folder_path.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS]
        cover = self._find_cover(folder_path)
        total_duration = sum(get_duration(f) for f in tracks)
        try:
            content_mtimes = [f.stat().st_mtime for f in tracks]
            if cover:
                content_mtimes.append(cover.stat().st_mtime)
            mtime = max(content_mtimes) if content_mtimes else folder_path.stat().st_mtime
        except OSError:
            mtime = 0

        return MediaFolder(
            name=folder_name,
            path=folder_name,
            track_count=len(tracks),
            cover_path=f"/api/library/{folder_name}/cover" if cover else None,
            duration_seconds=total_duration,
            mtime=mtime,
        )

    def list_tracks(self, folder_name: str) -> list[MediaTrack]:
        """List all audio tracks in a folder with durations."""
        folder_path = self._media_dir / folder_name
        if not folder_path.is_dir():
            return []

        tracks = []
        for f in sorted(folder_path.iterdir()):
            if f.suffix.lower() in AUDIO_EXTENSIONS:
                tracks.append(MediaTrack(
                    filename=f.name,
                    path=f"{folder_name}/{f.name}",
                    duration_seconds=get_duration(f),
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

    # Preferred cover basenames (lower-case). Matched case-insensitively so
    # `Cover.JPG`, `Folder.png`, `FRONT.webp` etc. are all found on Linux.
    _COVER_BASENAMES = ("cover", "folder", "front")

    @staticmethod
    def _find_cover(folder_path: Path) -> Path | None:
        """Find cover art in a folder, case-insensitively.

        Priority:
          1. Any file whose basename (without extension) is cover/folder/front
             and whose extension is a known image type — regardless of case.
          2. Fallback: first file with an image extension in directory order.
        """
        if not folder_path.is_dir():
            return None
        try:
            entries = list(folder_path.iterdir())
        except OSError:
            return None

        # Index by (basename.lower(), ext.lower()) so we can honour preference order.
        preferred: dict[str, Path] = {}
        fallback: Path | None = None
        for entry in entries:
            if not entry.is_file():
                continue
            ext = entry.suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                continue
            stem = entry.stem.lower()
            if stem in LibraryService._COVER_BASENAMES and stem not in preferred:
                preferred[stem] = entry
            elif fallback is None:
                fallback = entry

        for name in LibraryService._COVER_BASENAMES:
            if name in preferred:
                return preferred[name]
        return fallback
