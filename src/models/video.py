"""Video-related data models."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class VideoMetadata:
    """Metadata for a video from a playlist."""

    video_id: str
    title: str
    duration: int  # Duration in seconds
    url: str
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate video metadata after initialization."""
        logger.trace(  # type: ignore[attr-defined]
            f"Validating VideoMetadata for video_id={self.video_id}"
        )

        if not self.video_id:
            logger.error("VideoMetadata validation failed: empty video_id")
            raise ValueError("video_id cannot be empty")
        if not self.title:
            logger.error(
                f"VideoMetadata validation failed: empty title for "
                f"video_id={self.video_id}"
            )
            raise ValueError("title cannot be empty")
        if self.duration < 0:
            logger.error(
                f"VideoMetadata validation failed: negative duration {self.duration} "
                f"for video_id={self.video_id}"
            )
            raise ValueError("duration must be non-negative")
        if not self.url:
            logger.error(
                f"VideoMetadata validation failed: empty url for "
                f"video_id={self.video_id}"
            )
            raise ValueError("url cannot be empty")

        logger.debug(
            f"VideoMetadata validated successfully: {self.video_id} - {self.title} "
            f"({self.duration}s)"
        )


@dataclass(frozen=True)
class VideoFile:
    """Represents a video file with its metadata and file information."""

    metadata: VideoMetadata
    file_path: Path
    file_size: int  # Size in bytes
    checksum: str  # SHA-256 checksum for integrity verification
    format: str  # File format (e.g., "mp4", "webm", "mkv")

    def __post_init__(self) -> None:
        """Validate video file after initialization."""
        logger.trace(  # type: ignore[attr-defined]
            f"Validating VideoFile for {self.metadata.video_id} at {self.file_path}"
        )

        if self.file_size < 0:
            logger.error(
                f"VideoFile validation failed: negative file_size {self.file_size} "
                f"for {self.metadata.video_id}"
            )
            raise ValueError("file_size must be non-negative")
        if not self.checksum:
            logger.error(
                f"VideoFile validation failed: empty checksum for "
                f"{self.metadata.video_id}"
            )
            raise ValueError("checksum cannot be empty")
        if not self.format:
            logger.error(
                f"VideoFile validation failed: empty format for "
                f"{self.metadata.video_id}"
            )
            raise ValueError("format cannot be empty")

        logger.debug(
            f"VideoFile validated successfully: {self.metadata.video_id} - "
            f"{self.size_mb:.1f}MB {self.format}"
        )

    @property
    def exists(self) -> bool:
        """Check if the video file exists on disk."""
        file_exists = self.file_path.exists()
        logger.trace(  # type: ignore[attr-defined]
            f"File existence check for {self.metadata.video_id}: {file_exists}"
        )
        return file_exists

    @property
    def size_mb(self) -> float:
        """Get file size in MB."""
        return self.file_size / (1024 * 1024)

    def is_valid_size(self) -> bool:
        """Check if the actual file size matches the recorded size."""
        if not self.exists:
            logger.debug(
                f"Size validation failed for {self.metadata.video_id}: "
                f"file does not exist"
            )
            return False

        actual_size = self.file_path.stat().st_size
        size_matches = actual_size == self.file_size

        if not size_matches:
            logger.warning(
                f"Size mismatch for {self.metadata.video_id}: expected "
                f"{self.file_size}, actual {actual_size}"
            )
        else:
            logger.trace(  # type: ignore[attr-defined]
                f"Size validation passed for {self.metadata.video_id}: "
                f"{actual_size} bytes"
            )

        return size_matches
