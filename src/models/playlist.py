"""Playlist-related data models."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from ..utils.logging import get_logger
from ..utils.time_format import format_duration_human_readable
from .video import VideoMetadata

logger = get_logger(__name__)


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
        logger.trace(  # type: ignore[attr-defined]
            f"Validating PlaylistMetadata for playlist_id={self.playlist_id}"
        )

        if not self.playlist_id:
            logger.error("PlaylistMetadata validation failed: empty playlist_id")
            raise ValueError("playlist_id cannot be empty")
        if not self.title:
            logger.error(
                f"PlaylistMetadata validation failed: empty title for "
                f"playlist_id={self.playlist_id}"
            )
            raise ValueError("title cannot be empty")
        if self.video_count < 0:
            logger.error(
                f"PlaylistMetadata validation failed: negative video_count "
                f"{self.video_count} for playlist_id={self.playlist_id}"
            )
            raise ValueError("video_count must be non-negative")
        if self.total_size_estimate is not None and self.total_size_estimate < 0:
            logger.error(
                f"PlaylistMetadata validation failed: negative total_size_estimate "
                f"{self.total_size_estimate} for playlist_id={self.playlist_id}"
            )
            raise ValueError("total_size_estimate must be non-negative")

        size_mb = (
            (self.total_size_estimate / (1024 * 1024))
            if self.total_size_estimate
            else 0
        )
        logger.debug(
            f"PlaylistMetadata validated: {self.playlist_id} - {self.title} "
            f"({self.video_count} videos, ~{size_mb:.1f}MB)"
        )


@dataclass
class Playlist:
    """Represents a YouTube playlist with videos and their statuses."""

    metadata: PlaylistMetadata
    videos: List[VideoMetadata]  # Maintain original ordering
    video_statuses: Dict[str, VideoStatus]  # video_id -> status mapping

    def __post_init__(self) -> None:
        """Validate playlist after initialization."""
        logger.trace(  # type: ignore[attr-defined]
            f"Validating Playlist for {self.metadata.playlist_id} with "
            f"{len(self.videos)} videos"
        )

        if len(self.videos) != self.metadata.video_count:
            # Allow slight mismatch as playlist may have changed
            logger.warning(
                f"Video count mismatch for {self.metadata.playlist_id}: "
                f"metadata={self.metadata.video_count}, actual={len(self.videos)}"
            )

        # Ensure all videos have status entries
        videos_without_status = 0
        for video in self.videos:
            if video.video_id not in self.video_statuses:
                self.video_statuses[video.video_id] = VideoStatus.AVAILABLE
                videos_without_status += 1

        if videos_without_status > 0:
            logger.debug(
                f"Added default AVAILABLE status for {videos_without_status} videos "
                f"in {self.metadata.playlist_id}"
            )

        logger.debug(
            f"Playlist validated: {self.metadata.playlist_id} with "
            f"{len(self.videos)} videos"
        )

    def check_dvd_capacity(self, dvd_capacity_gb: float = 4.7) -> bool:
        """Check if playlist fits on a DVD.

        Args:
            dvd_capacity_gb: DVD capacity in GB (default 4.7GB for single layer)

        Returns:
            True if playlist fits on DVD, False otherwise
        """
        if self.metadata.total_size_estimate is None:
            # Cannot determine without size estimate
            logger.debug(
                f"DVD capacity check for {self.metadata.playlist_id}: "
                f"no size estimate, assuming it fits"
            )
            return True

        dvd_capacity_bytes = dvd_capacity_gb * 1024 * 1024 * 1024
        fits = self.metadata.total_size_estimate <= dvd_capacity_bytes

        size_gb = self.metadata.total_size_estimate / (1024 * 1024 * 1024)
        if fits:
            logger.debug(
                f"DVD capacity check for {self.metadata.playlist_id}: "
                f"{size_gb:.2f}GB fits on {dvd_capacity_gb}GB DVD"
            )
        else:
            logger.warning(
                f"DVD capacity exceeded for {self.metadata.playlist_id}: "
                f"{size_gb:.2f}GB > {dvd_capacity_gb}GB"
            )

        return fits

    def get_available_videos(self) -> List[VideoMetadata]:
        """Get list of videos that are available for processing."""
        available_videos = [
            video
            for video in self.videos
            if self.video_statuses.get(video.video_id)
            in {VideoStatus.AVAILABLE, VideoStatus.DOWNLOADED, VideoStatus.DOWNLOADING}
        ]

        logger.debug(
            f"Found {len(available_videos)}/{len(self.videos)} available videos "
            f"in {self.metadata.playlist_id}"
        )
        return available_videos

    def get_failed_videos(self) -> List[VideoMetadata]:
        """Get list of videos that failed to download or are unavailable."""
        failed_videos = [
            video
            for video in self.videos
            if self.video_statuses.get(video.video_id)
            in {VideoStatus.MISSING, VideoStatus.PRIVATE, VideoStatus.FAILED}
        ]

        if failed_videos:
            logger.warning(
                f"Found {len(failed_videos)}/{len(self.videos)} failed videos "
                f"in {self.metadata.playlist_id}"
            )
        else:
            logger.debug(f"No failed videos in {self.metadata.playlist_id}")

        return failed_videos

    def update_video_status(self, video_id: str, status: VideoStatus) -> None:
        """Update the status of a video."""
        if video_id not in {video.video_id for video in self.videos}:
            logger.error(
                f"Attempted to update status for unknown video {video_id} "
                f"in {self.metadata.playlist_id}"
            )
            raise ValueError(f"Video ID {video_id} not found in playlist")

        old_status = self.video_statuses.get(video_id)
        self.video_statuses[video_id] = status

        logger.debug(
            f"Updated video status in {self.metadata.playlist_id}: {video_id} "
            f"{old_status} -> {status.value}"
        )

    def get_success_rate(self) -> float:
        """Get the percentage of videos that are available."""
        if not self.videos:
            logger.debug(
                f"Success rate calculation for {self.metadata.playlist_id}: "
                f"0% (no videos)"
            )
            return 0.0

        available_count = len(self.get_available_videos())
        success_rate = (available_count / len(self.videos)) * 100.0

        logger.debug(
            f"Success rate for {self.metadata.playlist_id}: {success_rate:.1f}% "
            f"({available_count}/{len(self.videos)})"
        )
        return success_rate

    @property
    def total_duration(self) -> int:
        """Get the total duration of all videos in seconds."""
        return sum(video.duration for video in self.videos)

    @property
    def total_duration_human_readable(self) -> str:
        """Get the total duration in human-readable format."""
        return format_duration_human_readable(self.total_duration)
