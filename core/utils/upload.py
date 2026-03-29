"""Upload utilities for streaming files to disk with validation."""

import logging
from pathlib import Path

from fastapi import HTTPException, UploadFile

logger = logging.getLogger(__name__)


async def stream_to_disk(
    file: UploadFile,
    target_path: Path,
    max_bytes: int,
    allowed_extensions: set[str],
) -> int:
    """Stream an uploaded file to disk with size and type validation.

    Args:
        file: The uploaded file.
        target_path: Where to write the file.
        max_bytes: Maximum allowed file size in bytes.
        allowed_extensions: Set of allowed lowercase extensions (e.g. {".mp3", ".ogg"}).

    Returns:
        The number of bytes written.

    Raises:
        HTTPException: On validation failure or write error.
    """
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed_extensions:
        raise HTTPException(400, f"File type not allowed: {suffix}")

    try:
        bytes_written = 0
        with open(target_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1 MB chunks
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    f.close()
                    target_path.unlink(missing_ok=True)
                    raise HTTPException(
                        413,
                        f"File too large (max {max_bytes // (1024 * 1024)} MB)",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload failed: %s", e)
        target_path.unlink(missing_ok=True)
        raise HTTPException(500, "Upload failed")

    return bytes_written
