"""Test capacity management utilities."""

from unittest.mock import Mock

import pytest

from src.models.video import VideoMetadata
from src.utils.capacity import (
    CapacityResult,
    ExcludedVideo,
    log_excluded_videos,
    select_videos_for_dvd_capacity,
)


@pytest.fixture
def sample_video_metadata():
    """Create sample video metadata."""
    return VideoMetadata(
        video_id="test123",
        title="Test Video",
        duration=300,
        url="https://www.youtube.com/watch?v=test123",
    )


@pytest.fixture
def sample_converted_video(sample_video_metadata):
    """Create a sample converted video file."""
    video = Mock()
    video.metadata = sample_video_metadata
    video.size_mb = 1000.0  # 1GB
    return video


class TestExcludedVideo:
    """Test ExcludedVideo class."""

    def test_excluded_video_creation(self, sample_video_metadata):
        """Test creating an ExcludedVideo."""
        excluded = ExcludedVideo(metadata=sample_video_metadata, size_mb=500.0)

        assert excluded.metadata == sample_video_metadata
        assert excluded.size_mb == 500.0
        assert excluded.youtube_url == "https://www.youtube.com/watch?v=test123"


class TestCapacityResult:
    """Test CapacityResult class."""

    def test_capacity_result_properties(self, sample_converted_video):
        """Test CapacityResult properties."""
        excluded_video = ExcludedVideo(
            metadata=sample_converted_video.metadata, size_mb=500.0
        )

        result = CapacityResult(
            included_videos=[sample_converted_video],
            excluded_videos=[excluded_video],
            total_size_mb=1000.0,
            excluded_size_mb=500.0,
        )

        assert result.has_exclusions is True
        assert result.total_size_gb == pytest.approx(0.976, rel=1e-2)  # 1000/1024
        assert result.excluded_size_gb == pytest.approx(0.488, rel=1e-2)  # 500/1024
        assert result.total_duration_human_readable == "5m"  # 300s duration

    def test_capacity_result_no_exclusions(self, sample_converted_video):
        """Test CapacityResult with no exclusions."""
        result = CapacityResult(
            included_videos=[sample_converted_video],
            excluded_videos=[],
            total_size_mb=1000.0,
            excluded_size_mb=0.0,
        )

        assert result.has_exclusions is False
        assert result.total_size_gb == pytest.approx(0.976, rel=1e-2)
        assert result.excluded_size_gb == 0.0
        assert result.total_duration_human_readable == "5m"  # 300s duration


class TestSelectVideosForDvdCapacity:
    """Test DVD capacity selection function."""

    def test_all_videos_fit(self):
        """Test when all videos fit on DVD."""
        # Create small videos that all fit
        videos = []
        for i in range(3):
            video = Mock()
            video.metadata = VideoMetadata(
                video_id=f"test{i}",
                title=f"Test Video {i}",
                duration=300,
                url=f"https://www.youtube.com/watch?v=test{i}",
            )
            video.size_mb = 1000.0  # 1GB each, 3GB total
            videos.append(video)

        result = select_videos_for_dvd_capacity(videos, dvd_capacity_gb=4.7)

        assert len(result.included_videos) == 3
        assert len(result.excluded_videos) == 0
        assert result.has_exclusions is False
        assert result.total_size_gb == pytest.approx(2.93, rel=1e-2)  # 3000/1024

    def test_some_videos_excluded(self):
        """Test when some videos need to be excluded."""
        videos = []
        for i in range(5):
            video = Mock()
            video.metadata = VideoMetadata(
                video_id=f"test{i}",
                title=f"Test Video {i}",
                duration=300,
                url=f"https://www.youtube.com/watch?v=test{i}",
            )
            video.size_mb = 1200.0  # 1.2GB each, 6GB total
            videos.append(video)

        result = select_videos_for_dvd_capacity(videos, dvd_capacity_gb=4.7)

        # Should include first 4 videos (4.8GB) and exclude last 1 (1.2GB)
        assert len(result.included_videos) == 4
        assert len(result.excluded_videos) == 1
        assert result.has_exclusions is True
        assert result.total_size_gb == pytest.approx(4.69, rel=1e-2)  # 4800/1024
        assert result.excluded_size_gb == pytest.approx(1.17, rel=1e-2)  # 1200/1024

    def test_empty_video_list(self):
        """Test with empty video list."""
        result = select_videos_for_dvd_capacity([], dvd_capacity_gb=4.7)

        assert len(result.included_videos) == 0
        assert len(result.excluded_videos) == 0
        assert result.has_exclusions is False
        assert result.total_size_gb == 0.0
        assert result.excluded_size_gb == 0.0

    def test_single_video_too_large(self):
        """Test when first video exceeds capacity."""
        video = Mock()
        video.metadata = VideoMetadata(
            video_id="test1",
            title="Large Video",
            duration=7200,
            url="https://www.youtube.com/watch?v=test1",
        )
        video.size_mb = 6000.0  # 6GB - larger than DVD capacity

        result = select_videos_for_dvd_capacity([video], dvd_capacity_gb=4.7)

        assert len(result.included_videos) == 0
        assert len(result.excluded_videos) == 1
        assert result.has_exclusions is True
        assert result.total_size_gb == 0.0
        assert result.excluded_size_gb == pytest.approx(5.86, rel=1e-2)  # 6000/1024

    def test_custom_dvd_capacity(self):
        """Test with custom DVD capacity."""
        videos = []
        for i in range(3):
            video = Mock()
            video.metadata = VideoMetadata(
                video_id=f"test{i}",
                title=f"Test Video {i}",
                duration=300,
                url=f"https://www.youtube.com/watch?v=test{i}",
            )
            video.size_mb = 4000.0  # 4GB each
            videos.append(video)

        # Test with 8.5GB dual-layer DVD
        result = select_videos_for_dvd_capacity(videos, dvd_capacity_gb=8.5)

        # Should include first 2 videos (8GB) and exclude last one (4GB)
        assert len(result.included_videos) == 2
        assert len(result.excluded_videos) == 1
        assert result.has_exclusions is True


class TestLogExcludedVideos:
    """Test excluded videos logging function."""

    def test_log_excluded_videos_empty(self, caplog):
        """Test logging with empty list."""
        log_excluded_videos([])

        # Should not log anything
        assert len(caplog.records) == 0

    def test_log_excluded_videos_single(self, caplog, sample_video_metadata):
        """Test logging with single excluded video."""
        excluded = ExcludedVideo(metadata=sample_video_metadata, size_mb=1500.0)

        log_excluded_videos([excluded])

        # Check log messages
        warning_messages = [
            record.message for record in caplog.records if record.levelname == "WARNING"
        ]
        assert len(warning_messages) == 3  # Header, video info, total size
        assert "1 videos could not fit" in warning_messages[0]
        assert "Test Video" in warning_messages[1]
        assert "1500.0MB" in warning_messages[1]
        assert "https://www.youtube.com/watch?v=test123" in warning_messages[1]
        assert "Total excluded size: 1.46GB" in warning_messages[2]

    def test_log_excluded_videos_multiple(self, caplog):
        """Test logging with multiple excluded videos."""
        excluded_videos = []
        for i in range(3):
            metadata = VideoMetadata(
                video_id=f"test{i}",
                title=f"Test Video {i}",
                duration=300,
                url=f"https://www.youtube.com/watch?v=test{i}",
            )
            excluded = ExcludedVideo(metadata=metadata, size_mb=1000.0)
            excluded_videos.append(excluded)

        log_excluded_videos(excluded_videos)

        # Check log messages
        warning_messages = [
            record.message for record in caplog.records if record.levelname == "WARNING"
        ]
        assert len(warning_messages) == 5  # Header + 3 videos + total
        assert "3 videos could not fit" in warning_messages[0]
        assert "Total excluded size: 2.93GB" in warning_messages[4]
