"""Tests for video models."""

import tempfile
from pathlib import Path

import pytest

from src.models.video import VideoFile, VideoMetadata


class TestVideoMetadata:
    """Test cases for VideoMetadata dataclass."""

    def test_valid_video_metadata(self) -> None:
        """Test creating valid video metadata."""
        metadata = VideoMetadata(
            video_id="abc123",
            title="Test Video",
            duration=120,
            url="https://youtube.com/watch?v=abc123",
            thumbnail_url="https://i.ytimg.com/vi/abc123/default.jpg",
            description="A test video",
        )

        assert metadata.video_id == "abc123"
        assert metadata.title == "Test Video"
        assert metadata.duration == 120
        assert metadata.url == "https://youtube.com/watch?v=abc123"
        assert metadata.thumbnail_url == "https://i.ytimg.com/vi/abc123/default.jpg"
        assert metadata.description == "A test video"

    def test_video_metadata_minimal(self) -> None:
        """Test creating video metadata with minimal required fields."""
        metadata = VideoMetadata(
            video_id="abc123",
            title="Test Video",
            duration=120,
            url="https://youtube.com/watch?v=abc123",
        )

        assert metadata.video_id == "abc123"
        assert metadata.title == "Test Video"
        assert metadata.duration == 120
        assert metadata.url == "https://youtube.com/watch?v=abc123"
        assert metadata.thumbnail_url is None
        assert metadata.description is None

    def test_video_metadata_empty_id_raises_error(self) -> None:
        """Test that empty video_id raises ValueError."""
        with pytest.raises(ValueError, match="video_id cannot be empty"):
            VideoMetadata(
                video_id="",
                title="Test Video",
                duration=120,
                url="https://youtube.com/watch?v=abc123",
            )

    def test_video_metadata_empty_title_raises_error(self) -> None:
        """Test that empty title raises ValueError."""
        with pytest.raises(ValueError, match="title cannot be empty"):
            VideoMetadata(
                video_id="abc123",
                title="",
                duration=120,
                url="https://youtube.com/watch?v=abc123",
            )

    def test_video_metadata_negative_duration_raises_error(self) -> None:
        """Test that negative duration raises ValueError."""
        with pytest.raises(ValueError, match="duration must be non-negative"):
            VideoMetadata(
                video_id="abc123",
                title="Test Video",
                duration=-1,
                url="https://youtube.com/watch?v=abc123",
            )

    def test_video_metadata_empty_url_raises_error(self) -> None:
        """Test that empty url raises ValueError."""
        with pytest.raises(ValueError, match="url cannot be empty"):
            VideoMetadata(video_id="abc123", title="Test Video", duration=120, url="")

    def test_video_metadata_zero_duration_valid(self) -> None:
        """Test that zero duration is valid."""
        metadata = VideoMetadata(
            video_id="abc123",
            title="Test Video",
            duration=0,
            url="https://youtube.com/watch?v=abc123",
        )
        assert metadata.duration == 0


class TestVideoFile:
    """Test cases for VideoFile dataclass."""

    @pytest.fixture
    def sample_metadata(self) -> VideoMetadata:
        """Create sample video metadata for testing."""
        return VideoMetadata(
            video_id="abc123",
            title="Test Video",
            duration=120,
            url="https://youtube.com/watch?v=abc123",
        )

    @pytest.fixture
    def temp_file(self) -> Path:
        """Create a temporary file for testing."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as f:
            f.write(b"test video content")
            return Path(f.name)

    def test_valid_video_file(self, sample_metadata: VideoMetadata) -> None:
        """Test creating valid video file."""
        file_path = Path("/path/to/video.mp4")
        video_file = VideoFile(
            metadata=sample_metadata,
            file_path=file_path,
            file_size=1024,
            checksum="abcdef123456",
            format="mp4",
        )

        assert video_file.metadata == sample_metadata
        assert video_file.file_path == file_path
        assert video_file.file_size == 1024
        assert video_file.checksum == "abcdef123456"
        assert video_file.format == "mp4"

    def test_video_file_negative_size_raises_error(
        self, sample_metadata: VideoMetadata
    ) -> None:
        """Test that negative file size raises ValueError."""
        with pytest.raises(ValueError, match="file_size must be non-negative"):
            VideoFile(
                metadata=sample_metadata,
                file_path=Path("/path/to/video.mp4"),
                file_size=-1,
                checksum="abcdef123456",
                format="mp4",
            )

    def test_video_file_empty_checksum_raises_error(
        self, sample_metadata: VideoMetadata
    ) -> None:
        """Test that empty checksum raises ValueError."""
        with pytest.raises(ValueError, match="checksum cannot be empty"):
            VideoFile(
                metadata=sample_metadata,
                file_path=Path("/path/to/video.mp4"),
                file_size=1024,
                checksum="",
                format="mp4",
            )

    def test_video_file_empty_format_raises_error(
        self, sample_metadata: VideoMetadata
    ) -> None:
        """Test that empty format raises ValueError."""
        with pytest.raises(ValueError, match="format cannot be empty"):
            VideoFile(
                metadata=sample_metadata,
                file_path=Path("/path/to/video.mp4"),
                file_size=1024,
                checksum="abcdef123456",
                format="",
            )

    def test_video_file_exists_nonexistent_file(
        self, sample_metadata: VideoMetadata
    ) -> None:
        """Test exists property with non-existent file."""
        video_file = VideoFile(
            metadata=sample_metadata,
            file_path=Path("/nonexistent/path/video.mp4"),
            file_size=1024,
            checksum="abcdef123456",
            format="mp4",
        )

        assert not video_file.exists

    def test_video_file_exists_existing_file(
        self, sample_metadata: VideoMetadata, temp_file: Path
    ) -> None:
        """Test exists property with existing file."""
        video_file = VideoFile(
            metadata=sample_metadata,
            file_path=temp_file,
            file_size=1024,
            checksum="abcdef123456",
            format="mp4",
        )

        assert video_file.exists
        # Cleanup
        temp_file.unlink()

    def test_video_file_size_mb_property(self, sample_metadata: VideoMetadata) -> None:
        """Test size_mb property calculation."""
        video_file = VideoFile(
            metadata=sample_metadata,
            file_path=Path("/path/to/video.mp4"),
            file_size=1048576,  # 1 MB
            checksum="abcdef123456",
            format="mp4",
        )

        assert video_file.size_mb == 1.0

    def test_video_file_is_valid_size_nonexistent_file(
        self, sample_metadata: VideoMetadata
    ) -> None:
        """Test is_valid_size with non-existent file."""
        video_file = VideoFile(
            metadata=sample_metadata,
            file_path=Path("/nonexistent/path/video.mp4"),
            file_size=1024,
            checksum="abcdef123456",
            format="mp4",
        )

        assert not video_file.is_valid_size()

    def test_video_file_is_valid_size_existing_file(
        self, sample_metadata: VideoMetadata, temp_file: Path
    ) -> None:
        """Test is_valid_size with existing file."""
        actual_size = temp_file.stat().st_size

        video_file = VideoFile(
            metadata=sample_metadata,
            file_path=temp_file,
            file_size=actual_size,
            checksum="abcdef123456",
            format="mp4",
        )

        assert video_file.is_valid_size()

        # Test with wrong size
        video_file_wrong_size = VideoFile(
            metadata=sample_metadata,
            file_path=temp_file,
            file_size=actual_size + 100,
            checksum="abcdef123456",
            format="mp4",
        )

        assert not video_file_wrong_size.is_valid_size()

        # Cleanup
        temp_file.unlink()

    def test_video_file_zero_size_valid(self, sample_metadata: VideoMetadata) -> None:
        """Test that zero file size is valid."""
        video_file = VideoFile(
            metadata=sample_metadata,
            file_path=Path("/path/to/video.mp4"),
            file_size=0,
            checksum="abcdef123456",
            format="mp4",
        )
        assert video_file.file_size == 0
        assert video_file.size_mb == 0.0
