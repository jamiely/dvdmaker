"""Video-related data models."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


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
        if not self.video_id:
            raise ValueError("video_id cannot be empty")
        if not self.title:
            raise ValueError("title cannot be empty")
        if self.duration < 0:
            raise ValueError("duration must be non-negative")
        if not self.url:
            raise ValueError("url cannot be empty")


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
        if self.file_size < 0:
            raise ValueError("file_size must be non-negative")
        if not self.checksum:
            raise ValueError("checksum cannot be empty")
        if not self.format:
            raise ValueError("format cannot be empty")

    @property
    def exists(self) -> bool:
        """Check if the video file exists on disk."""
        return self.file_path.exists()

    @property
    def size_mb(self) -> float:
        """Get file size in MB."""
        return self.file_size / (1024 * 1024)

    def is_valid_size(self) -> bool:
        """Check if the actual file size matches the recorded size."""
        if not self.exists:
            return False
        return self.file_path.stat().st_size == self.file_size
