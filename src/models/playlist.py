"""Playlist-related data models."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from .video import VideoMetadata


class VideoStatus(Enum):
    """Status of a video in a playlist."""

    AVAILABLE = "available"
    MISSING = "missing"
    PRIVATE = "private"
    FAILED = "failed"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"


@dataclass(frozen=True)
class PlaylistMetadata:
    """Metadata for a YouTube playlist."""

    playlist_id: str  # YouTube playlist ID format
    title: str
    description: Optional[str] = None
    video_count: int = 0
    total_size_estimate: Optional[int] = None  # For DVD capacity warnings

    def __post_init__(self) -> None:
        """Validate playlist metadata after initialization."""
        if not self.playlist_id:
            raise ValueError("playlist_id cannot be empty")
        if not self.title:
            raise ValueError("title cannot be empty")
        if self.video_count < 0:
            raise ValueError("video_count must be non-negative")
        if self.total_size_estimate is not None and self.total_size_estimate < 0:
            raise ValueError("total_size_estimate must be non-negative")


@dataclass
class Playlist:
    """Represents a YouTube playlist with videos and their statuses."""

    metadata: PlaylistMetadata
    videos: List[VideoMetadata]  # Maintain original ordering
    video_statuses: Dict[str, VideoStatus]  # video_id -> status mapping

    def __post_init__(self) -> None:
        """Validate playlist after initialization."""
        if len(self.videos) != self.metadata.video_count:
            # Allow slight mismatch as playlist may have changed
            pass

        # Ensure all videos have status entries
        for video in self.videos:
            if video.video_id not in self.video_statuses:
                self.video_statuses[video.video_id] = VideoStatus.AVAILABLE

    def check_dvd_capacity(self, dvd_capacity_gb: float = 4.7) -> bool:
        """Check if playlist fits on a DVD.

        Args:
            dvd_capacity_gb: DVD capacity in GB (default 4.7GB for single layer)

        Returns:
            True if playlist fits on DVD, False otherwise
        """
        if self.metadata.total_size_estimate is None:
            # Cannot determine without size estimate
            return True

        dvd_capacity_bytes = dvd_capacity_gb * 1024 * 1024 * 1024
        return self.metadata.total_size_estimate <= dvd_capacity_bytes

    def get_available_videos(self) -> List[VideoMetadata]:
        """Get list of videos that are available for processing."""
        return [
            video
            for video in self.videos
            if self.video_statuses.get(video.video_id)
            in {VideoStatus.AVAILABLE, VideoStatus.DOWNLOADED, VideoStatus.DOWNLOADING}
        ]

    def get_failed_videos(self) -> List[VideoMetadata]:
        """Get list of videos that failed to download or are unavailable."""
        return [
            video
            for video in self.videos
            if self.video_statuses.get(video.video_id)
            in {VideoStatus.MISSING, VideoStatus.PRIVATE, VideoStatus.FAILED}
        ]

    def update_video_status(self, video_id: str, status: VideoStatus) -> None:
        """Update the status of a video."""
        if video_id not in {video.video_id for video in self.videos}:
            raise ValueError(f"Video ID {video_id} not found in playlist")
        self.video_statuses[video_id] = status

    def get_success_rate(self) -> float:
        """Get the percentage of videos that are available."""
        if not self.videos:
            return 0.0

        available_count = len(self.get_available_videos())
        return (available_count / len(self.videos)) * 100.0
