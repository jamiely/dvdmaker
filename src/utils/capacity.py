"""DVD capacity management utilities."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, List

from ..models.video import VideoMetadata
from ..utils.logging import get_logger

if TYPE_CHECKING:
    from ..services.converter import ConvertedVideoFile

logger = get_logger(__name__)


@dataclass
class ExcludedVideo:
    """Information about a video that was excluded due to capacity constraints."""

    metadata: VideoMetadata
    size_mb: float

    @property
    def youtube_url(self) -> str:
        """Get the YouTube URL for this video."""
        return f"https://www.youtube.com/watch?v={self.metadata.video_id}"


@dataclass
class CapacityResult:
    """Result of DVD capacity filtering."""

    included_videos: List["ConvertedVideoFile"]
    excluded_videos: List[ExcludedVideo]
    total_size_mb: float
    excluded_size_mb: float

    @property
    def has_exclusions(self) -> bool:
        """Check if any videos were excluded."""
        return len(self.excluded_videos) > 0

    @property
    def total_size_gb(self) -> float:
        """Get total size of included videos in GB."""
        return self.total_size_mb / 1024

    @property
    def excluded_size_gb(self) -> float:
        """Get total size of excluded videos in GB."""
        return self.excluded_size_mb / 1024


def select_videos_for_dvd_capacity(
    converted_videos: List["ConvertedVideoFile"], dvd_capacity_gb: float = 4.7
) -> CapacityResult:
    """Select videos that fit within DVD capacity constraints.

    Selects videos in order until the capacity limit is reached. Videos are
    included in the order they appear in the input list (maintaining playlist order).

    Args:
        converted_videos: List of converted video files
        dvd_capacity_gb: DVD capacity in GB (default 4.7GB for single layer)

    Returns:
        CapacityResult with included videos, excluded videos, and size information
    """
    logger.debug(
        f"Selecting videos for DVD capacity: {dvd_capacity_gb}GB limit, "
        f"{len(converted_videos)} videos to process"
    )

    dvd_capacity_mb = dvd_capacity_gb * 1024  # Convert to MB

    included_videos: List["ConvertedVideoFile"] = []
    excluded_videos: List[ExcludedVideo] = []
    current_size_mb = 0.0
    excluded_size_mb = 0.0

    for video in converted_videos:
        video_size_mb = video.size_mb

        # Check if this video would exceed capacity
        if current_size_mb + video_size_mb <= dvd_capacity_mb:
            included_videos.append(video)
            current_size_mb += video_size_mb
            logger.trace(  # type: ignore[attr-defined]
                f"Including video {video.metadata.video_id}: {video_size_mb:.1f}MB "
                f"(total: {current_size_mb:.1f}MB)"
            )
        else:
            # Video would exceed capacity, exclude it
            excluded_video = ExcludedVideo(
                metadata=video.metadata, size_mb=video_size_mb
            )
            excluded_videos.append(excluded_video)
            excluded_size_mb += video_size_mb
            logger.debug(
                f"Excluding video {video.metadata.video_id} ({video.metadata.title}): "
                f"{video_size_mb:.1f}MB would exceed capacity"
            )

    result = CapacityResult(
        included_videos=included_videos,
        excluded_videos=excluded_videos,
        total_size_mb=current_size_mb,
        excluded_size_mb=excluded_size_mb,
    )

    if result.has_exclusions:
        logger.warning(
            f"DVD capacity filtering complete: {len(included_videos)} videos included "
            f"({result.total_size_gb:.2f}GB), {len(excluded_videos)} videos excluded "
            f"({result.excluded_size_gb:.2f}GB)"
        )
    else:
        logger.info(
            f"All {len(included_videos)} videos fit on DVD "
            f"({result.total_size_gb:.2f}GB / {dvd_capacity_gb}GB)"
        )

    return result


def log_excluded_videos(excluded_videos: List[ExcludedVideo]) -> None:
    """Log detailed information about excluded videos.

    Args:
        excluded_videos: List of videos that were excluded
    """
    if not excluded_videos:
        return

    logger.warning(
        f"The following {len(excluded_videos)} videos could not fit on the DVD:"
    )

    for i, video in enumerate(excluded_videos, 1):
        logger.warning(
            f"  {i}. {video.metadata.title} "
            f"({video.size_mb:.1f}MB) - {video.youtube_url}"
        )

    total_excluded_gb = sum(v.size_mb for v in excluded_videos) / 1024
    logger.warning(f"Total excluded size: {total_excluded_gb:.2f}GB")
