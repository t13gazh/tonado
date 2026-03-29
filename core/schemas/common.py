"""Shared enums and types used across schemas and services."""

from enum import StrEnum


class ContentType(StrEnum):
    """Content types for card-to-content mappings."""

    FOLDER = "folder"
    STREAM = "stream"
    PODCAST = "podcast"
    PLAYLIST = "playlist"
    COMMAND = "command"
