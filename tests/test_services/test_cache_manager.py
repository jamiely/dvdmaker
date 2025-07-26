"""Tests for CacheManager class."""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.models.playlist import PlaylistMetadata
from src.models.video import VideoFile, VideoMetadata
from src.services.cache_manager import CacheManager


@pytest.fixture
def temp_cache_dir():
    """Create a temporary directory for cache testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def sample_video_metadata():
    """Sample video metadata for testing."""
    return VideoMetadata(
        video_id="test_video_123",
        title="Test Video Title",
        duration=300,
        url="https://youtube.com/watch?v=test_video_123",
        thumbnail_url="https://example.com/thumb.jpg",
        description="Test video description",
    )


@pytest.fixture
def sample_playlist_metadata():
    """Sample playlist metadata for testing."""
    return PlaylistMetadata(
        playlist_id="test_playlist_456",
        title="Test Playlist",
        description="Test playlist description",
        video_count=5,
        total_size_estimate=1000000,
    )


@pytest.fixture
def cache_manager(temp_cache_dir):
    """Create a CacheManager instance for testing."""
    return CacheManager(cache_dir=temp_cache_dir)


@pytest.fixture
def sample_video_file(temp_cache_dir):
    """Create a sample video file for testing."""
    test_file = temp_cache_dir / "test_video.mp4"
    test_content = b"fake video content for testing"
    test_file.write_bytes(test_content)
    return test_file


class TestCacheManagerInitialization:
    """Tests for CacheManager initialization and directory creation."""

    def test_init_creates_directories(self, temp_cache_dir):
        """Test that initialization creates all necessary directories."""
        cache_manager = CacheManager(cache_dir=temp_cache_dir)  # noqa: F841

        expected_dirs = [
            temp_cache_dir,
            temp_cache_dir / "downloads",
            temp_cache_dir / "converted",
            temp_cache_dir / "metadata",
            temp_cache_dir / "downloads" / ".in-progress",
            temp_cache_dir / "converted" / ".in-progress",
        ]

        for directory in expected_dirs:
            assert directory.exists(), f"Directory {directory} was not created"
            assert directory.is_dir(), f"{directory} is not a directory"

    def test_init_with_force_flags(self, temp_cache_dir):
        """Test initialization with force flags set."""
        cache_manager = CacheManager(
            cache_dir=temp_cache_dir, force_download=True, force_convert=True
        )

        assert cache_manager.force_download is True
        assert cache_manager.force_convert is True

    def test_init_creates_filename_mapper(self, temp_cache_dir):
        """Test that initialization creates filename mapper."""
        cache_manager = CacheManager(cache_dir=temp_cache_dir)

        assert cache_manager.filename_mapper is not None
        assert cache_manager.filename_mapper.mapping_file == (
            temp_cache_dir / "filename_mapping.json"
        )

    def test_init_directory_creation_failure(self, temp_cache_dir):
        """Test handling of directory creation failure."""
        # Create a nested path that will fail due to parent directory permissions
        nested_cache_dir = temp_cache_dir / "nested"

        # Mock mkdir to raise permission error
        with patch.object(Path, "mkdir", side_effect=OSError("Permission denied")):
            with pytest.raises(RuntimeError, match="Failed to create cache directory"):
                CacheManager(cache_dir=nested_cache_dir)


class TestCachePathGeneration:
    """Tests for cache path generation methods."""

    def test_get_download_cache_path(self, cache_manager):
        """Test download cache path generation."""
        video_id = "test_video_123"
        expected_path = cache_manager.downloads_dir / "test_video_123.mp4"

        actual_path = cache_manager.get_download_cache_path(video_id)
        assert actual_path == expected_path

    def test_get_download_cache_path_custom_format(self, cache_manager):
        """Test download cache path with custom format."""
        video_id = "test_video_123"
        format_ext = "webm"
        expected_path = cache_manager.downloads_dir / "test_video_123.webm"

        actual_path = cache_manager.get_download_cache_path(video_id, format_ext)
        assert actual_path == expected_path

    def test_get_converted_cache_path(self, cache_manager):
        """Test converted cache path generation."""
        video_id = "test_video_123"
        expected_path = cache_manager.converted_dir / "test_video_123.mpg"

        actual_path = cache_manager.get_converted_cache_path(video_id)
        assert actual_path == expected_path

    def test_get_metadata_cache_path(self, cache_manager):
        """Test metadata cache path generation."""
        video_id = "test_video_123"
        expected_path = cache_manager.metadata_dir / "test_video_123_metadata.json"

        actual_path = cache_manager.get_metadata_cache_path(video_id)
        assert actual_path == expected_path

    def test_get_playlist_metadata_cache_path(self, cache_manager):
        """Test playlist metadata cache path generation."""
        playlist_id = "test_playlist_456"
        expected_path = (
            cache_manager.metadata_dir / "playlist_test_playlist_456_metadata.json"
        )

        actual_path = cache_manager.get_playlist_metadata_cache_path(playlist_id)
        assert actual_path == expected_path


class TestDownloadCaching:
    """Tests for download caching functionality."""

    def test_is_download_cached_no_file(self, cache_manager):
        """Test cache check when no file exists."""
        result = cache_manager.is_download_cached("nonexistent_video")
        assert result is False

    def test_is_download_cached_with_force_download(
        self, cache_manager, sample_video_file
    ):
        """Test cache check with force_download flag."""
        cache_manager.force_download = True

        # Create a cached file
        video_id = "test_video"
        cache_path = cache_manager.get_download_cache_path(video_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        sample_video_file.rename(cache_path)

        result = cache_manager.is_download_cached(video_id)
        assert result is False

    def test_is_download_cached_in_progress(self, cache_manager, sample_video_file):
        """Test cache check when file is in progress."""
        video_id = "test_video"

        # Create cached file
        cache_path = cache_manager.get_download_cache_path(video_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        sample_video_file.rename(cache_path)

        # Create in-progress marker
        in_progress_path = cache_manager.downloads_in_progress_dir / cache_path.name
        in_progress_path.touch()

        result = cache_manager.is_download_cached(video_id)
        assert result is False

    def test_is_download_cached_valid_file(self, cache_manager, sample_video_file):
        """Test cache check with valid cached file."""
        video_id = "test_video"

        # Create cached file
        cache_path = cache_manager.get_download_cache_path(video_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        sample_video_file.rename(cache_path)

        result = cache_manager.is_download_cached(video_id)
        assert result is True

    def test_is_download_cached_size_mismatch(self, cache_manager, sample_video_file):
        """Test cache check with size mismatch in metadata."""
        video_id = "test_video"

        # Create cached file
        cache_path = cache_manager.get_download_cache_path(video_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        sample_video_file.rename(cache_path)

        # Create metadata with wrong size
        metadata_path = cache_manager.get_metadata_cache_path(video_id)
        metadata_data = {"file_size": 99999, "checksum": "fake_checksum"}  # Wrong size
        with open(metadata_path, "w") as f:
            json.dump(metadata_data, f)

        result = cache_manager.is_download_cached(video_id)
        assert result is False

    @patch("src.services.cache_manager.shutil.copy2")
    @patch("src.services.cache_manager.shutil.move")
    def test_store_download_success(
        self,
        mock_move,
        mock_copy2,
        cache_manager,
        sample_video_file,
        sample_video_metadata,
    ):
        """Test successful download storage."""
        video_id = sample_video_metadata.video_id

        # Mock file operations
        mock_copy2.return_value = None
        mock_move.return_value = None

        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_size = 1024

            with patch.object(
                cache_manager, "_calculate_file_checksum"
            ) as mock_checksum:
                mock_checksum.return_value = "fake_checksum_hash"

                result = cache_manager.store_download(
                    video_id, sample_video_file, sample_video_metadata
                )

        assert isinstance(result, VideoFile)
        assert result.metadata == sample_video_metadata
        assert result.file_size == 1024
        assert result.checksum == "fake_checksum_hash"

        # Verify metadata was saved
        metadata_path = cache_manager.get_metadata_cache_path(video_id)
        assert metadata_path.exists()

    def test_store_download_nonexistent_source(
        self, cache_manager, sample_video_metadata
    ):
        """Test download storage with nonexistent source file."""
        nonexistent_file = Path("/nonexistent/file.mp4")

        with pytest.raises(RuntimeError, match="Source file does not exist"):
            cache_manager.store_download(
                sample_video_metadata.video_id, nonexistent_file, sample_video_metadata
            )

    @patch("src.services.cache_manager.shutil.copy2")
    def test_store_download_copy_failure(
        self, mock_copy2, cache_manager, sample_video_file, sample_video_metadata
    ):
        """Test download storage with copy failure."""
        mock_copy2.side_effect = OSError("Copy failed")

        with pytest.raises(RuntimeError, match="Failed to store download cache"):
            cache_manager.store_download(
                sample_video_metadata.video_id, sample_video_file, sample_video_metadata
            )

    def test_get_cached_download_success(self, cache_manager, sample_video_metadata):
        """Test successful retrieval of cached download."""
        video_id = sample_video_metadata.video_id

        # Create cached file
        cache_path = cache_manager.get_download_cache_path(video_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(b"fake video content")

        # Create metadata
        metadata_path = cache_manager.get_metadata_cache_path(video_id)
        metadata_data = {
            "video_id": sample_video_metadata.video_id,
            "title": sample_video_metadata.title,
            "duration": sample_video_metadata.duration,
            "url": sample_video_metadata.url,
            "thumbnail_url": sample_video_metadata.thumbnail_url,
            "description": sample_video_metadata.description,
            "file_size": len(b"fake video content"),
            "checksum": "fake_checksum",
            "format": "mp4",
        }
        with open(metadata_path, "w") as f:
            json.dump(metadata_data, f)

        # Mock is_download_cached to return True
        with patch.object(cache_manager, "is_download_cached", return_value=True):
            result = cache_manager.get_cached_download(video_id)

        assert result is not None
        assert isinstance(result, VideoFile)
        assert result.metadata.video_id == video_id

    def test_get_cached_download_not_cached(self, cache_manager):
        """Test retrieval when download is not cached."""
        with patch.object(cache_manager, "is_download_cached", return_value=False):
            result = cache_manager.get_cached_download("nonexistent_video")

        assert result is None

    def test_get_cached_download_metadata_error(self, cache_manager):
        """Test retrieval with corrupted metadata."""
        video_id = "test_video"

        # Create cached file
        cache_path = cache_manager.get_download_cache_path(video_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(b"fake video content")

        # Create invalid metadata
        metadata_path = cache_manager.get_metadata_cache_path(video_id)
        metadata_path.write_text("invalid json")

        with patch.object(cache_manager, "is_download_cached", return_value=True):
            result = cache_manager.get_cached_download(video_id)

        assert result is None


class TestConvertedCaching:
    """Tests for converted file caching functionality."""

    def test_is_converted_cached_no_file(self, cache_manager):
        """Test converted cache check when no file exists."""
        result = cache_manager.is_converted_cached("nonexistent_video")
        assert result is False

    def test_is_converted_cached_with_force_convert(
        self, cache_manager, sample_video_file
    ):
        """Test converted cache check with force_convert flag."""
        cache_manager.force_convert = True

        # Create a cached file
        video_id = "test_video"
        cache_path = cache_manager.get_converted_cache_path(video_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        sample_video_file.rename(cache_path)

        result = cache_manager.is_converted_cached(video_id)
        assert result is False

    def test_is_converted_cached_in_progress(self, cache_manager, sample_video_file):
        """Test converted cache check when file is in progress."""
        video_id = "test_video"

        # Create cached file
        cache_path = cache_manager.get_converted_cache_path(video_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        sample_video_file.rename(cache_path)

        # Create in-progress marker
        in_progress_path = cache_manager.converted_in_progress_dir / cache_path.name
        in_progress_path.touch()

        result = cache_manager.is_converted_cached(video_id)
        assert result is False

    def test_is_converted_cached_valid_file(self, cache_manager, sample_video_file):
        """Test converted cache check with valid cached file."""
        video_id = "test_video"

        # Create cached file
        cache_path = cache_manager.get_converted_cache_path(video_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        sample_video_file.rename(cache_path)

        result = cache_manager.is_converted_cached(video_id)
        assert result is True

    @patch("src.services.cache_manager.shutil.copy2")
    @patch("src.services.cache_manager.shutil.move")
    def test_store_converted_success(
        self,
        mock_move,
        mock_copy2,
        cache_manager,
        sample_video_file,
        sample_video_metadata,
    ):
        """Test successful converted file storage."""
        video_id = sample_video_metadata.video_id

        # Mock file operations
        mock_copy2.return_value = None
        mock_move.return_value = None

        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_size = 2048

            with patch.object(
                cache_manager, "_calculate_file_checksum"
            ) as mock_checksum:
                mock_checksum.return_value = "converted_checksum_hash"

                result = cache_manager.store_converted(
                    video_id, sample_video_file, sample_video_metadata
                )

        assert isinstance(result, VideoFile)
        assert result.metadata == sample_video_metadata
        assert result.file_size == 2048
        assert result.checksum == "converted_checksum_hash"

    def test_get_cached_converted_success(self, cache_manager, sample_video_metadata):
        """Test successful retrieval of cached converted file."""
        video_id = sample_video_metadata.video_id

        # Create cached converted file
        cache_path = cache_manager.get_converted_cache_path(video_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(b"fake converted content")

        # Create metadata
        metadata_path = cache_manager.get_metadata_cache_path(video_id)
        metadata_data = {
            "video_id": sample_video_metadata.video_id,
            "title": sample_video_metadata.title,
            "duration": sample_video_metadata.duration,
            "url": sample_video_metadata.url,
            "thumbnail_url": sample_video_metadata.thumbnail_url,
            "description": sample_video_metadata.description,
        }
        with open(metadata_path, "w") as f:
            json.dump(metadata_data, f)

        with patch.object(cache_manager, "is_converted_cached", return_value=True):
            with patch.object(
                cache_manager, "_calculate_file_checksum"
            ) as mock_checksum:
                mock_checksum.return_value = "converted_checksum"
                result = cache_manager.get_cached_converted(video_id)

        assert result is not None
        assert isinstance(result, VideoFile)
        assert result.metadata.video_id == video_id

    def test_get_cached_converted_no_metadata(self, cache_manager):
        """Test retrieval of converted file without metadata."""
        video_id = "test_video"

        # Create cached file without metadata
        cache_path = cache_manager.get_converted_cache_path(video_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(b"fake converted content")

        with patch.object(cache_manager, "is_converted_cached", return_value=True):
            result = cache_manager.get_cached_converted(video_id)

        assert result is None


class TestPlaylistMetadataCaching:
    """Tests for playlist metadata caching."""

    def test_store_playlist_metadata(self, cache_manager, sample_playlist_metadata):
        """Test storing playlist metadata."""
        cache_manager.store_playlist_metadata(sample_playlist_metadata)

        cache_path = cache_manager.get_playlist_metadata_cache_path(
            sample_playlist_metadata.playlist_id
        )
        assert cache_path.exists()

        with open(cache_path, "r") as f:
            data = json.load(f)

        assert data["playlist_id"] == sample_playlist_metadata.playlist_id
        assert data["title"] == sample_playlist_metadata.title
        assert "cached_at" in data

    def test_get_cached_playlist_metadata_success(
        self, cache_manager, sample_playlist_metadata
    ):
        """Test successful retrieval of cached playlist metadata."""
        # Store first
        cache_manager.store_playlist_metadata(sample_playlist_metadata)

        # Retrieve
        result = cache_manager.get_cached_playlist_metadata(
            sample_playlist_metadata.playlist_id
        )

        assert result is not None
        assert result.playlist_id == sample_playlist_metadata.playlist_id
        assert result.title == sample_playlist_metadata.title

    def test_get_cached_playlist_metadata_not_found(self, cache_manager):
        """Test retrieval of non-existent playlist metadata."""
        result = cache_manager.get_cached_playlist_metadata("nonexistent_playlist")
        assert result is None

    def test_get_cached_playlist_metadata_corrupted(self, cache_manager):
        """Test retrieval with corrupted playlist metadata."""
        playlist_id = "test_playlist"
        cache_path = cache_manager.get_playlist_metadata_cache_path(playlist_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("invalid json")

        result = cache_manager.get_cached_playlist_metadata(playlist_id)
        assert result is None


class TestFilenameMapping:
    """Tests for filename mapping functionality."""

    def test_get_normalized_filename(self, cache_manager):
        """Test filename normalization."""
        video_id = "test_video_123"
        original_title = "Test Video with Special Characters"

        with patch.object(
            cache_manager.filename_mapper, "get_normalized_filename"
        ) as mock_normalize:
            mock_normalize.return_value = "normalized_filename.mp4"

            result = cache_manager.get_normalized_filename(video_id, original_title)

            assert result == "normalized_filename.mp4"
            mock_normalize.assert_called_once_with(video_id, original_title)

    def test_save_filename_mapping(self, cache_manager):
        """Test saving filename mappings."""
        with patch.object(cache_manager.filename_mapper, "save_mapping") as mock_save:
            cache_manager.save_filename_mapping()
            mock_save.assert_called_once()


class TestCacheCleanup:
    """Tests for cache cleanup functionality."""

    def test_cleanup_cache(self, cache_manager):
        """Test cache cleanup removes old files."""
        # Create old file
        old_file = cache_manager.downloads_dir / "old_video.mp4"
        old_file.write_bytes(b"old content")

        # Make file appear old by setting modification time
        old_time = datetime.now() - timedelta(days=35)
        old_timestamp = old_time.timestamp()
        os.utime(old_file, (old_timestamp, old_timestamp))

        # Create recent file
        recent_file = cache_manager.downloads_dir / "recent_video.mp4"
        recent_file.write_bytes(b"recent content")

        # Run cleanup
        cache_manager.cleanup_cache(max_age_days=30)

        # Check results
        assert not old_file.exists()
        assert recent_file.exists()

    def test_cleanup_cache_ignores_hidden_files(self, cache_manager):
        """Test that cleanup ignores hidden files and directories."""
        # Create hidden file
        hidden_file = cache_manager.downloads_dir / ".hidden_file"
        hidden_file.write_bytes(b"hidden content")

        # Make it old
        old_time = datetime.now() - timedelta(days=35)
        old_timestamp = old_time.timestamp()
        os.utime(hidden_file, (old_timestamp, old_timestamp))

        # Run cleanup
        cache_manager.cleanup_cache(max_age_days=30)

        # Hidden file should still exist
        assert hidden_file.exists()

    def test_cleanup_cache_handles_errors(self, cache_manager):
        """Test that cleanup handles file access errors gracefully."""
        # Create file
        test_file = cache_manager.downloads_dir / "test_video.mp4"
        test_file.write_bytes(b"test content")

        # Mock unlink to raise error
        with patch.object(Path, "unlink", side_effect=OSError("Permission denied")):
            # Should not raise exception
            cache_manager.cleanup_cache(max_age_days=0)


class TestCacheStats:
    """Tests for cache statistics functionality."""

    def test_get_cache_stats_empty(self, cache_manager):
        """Test cache statistics with empty cache."""
        stats = cache_manager.get_cache_stats()

        expected_stats = {
            "downloads_count": 0,
            "downloads_size": 0,
            "converted_count": 0,
            "converted_size": 0,
            "metadata_count": 0,
            "metadata_size": 0,
        }

        assert stats == expected_stats

    def test_get_cache_stats_with_files(self, cache_manager):
        """Test cache statistics with files present."""
        # Create test files
        download_file = cache_manager.downloads_dir / "video1.mp4"
        download_file.write_bytes(b"x" * 1024)  # 1KB

        converted_file = cache_manager.converted_dir / "video1.mpg"
        converted_file.write_bytes(b"y" * 2048)  # 2KB

        metadata_file = cache_manager.metadata_dir / "video1_metadata.json"
        metadata_file.write_bytes(b"z" * 512)  # 512B

        stats = cache_manager.get_cache_stats()

        assert stats["downloads_count"] == 1
        assert stats["downloads_size"] == 1024
        assert stats["converted_count"] == 1
        assert stats["converted_size"] == 2048
        assert stats["metadata_count"] == 1
        assert stats["metadata_size"] == 512

    def test_get_cache_stats_ignores_hidden_files(self, cache_manager):
        """Test that statistics ignore hidden files."""
        # Create hidden file
        hidden_file = cache_manager.downloads_dir / ".hidden"
        hidden_file.write_bytes(b"hidden content")

        # Create normal file
        normal_file = cache_manager.downloads_dir / "normal.mp4"
        normal_file.write_bytes(b"normal content")

        stats = cache_manager.get_cache_stats()

        assert stats["downloads_count"] == 1
        assert stats["downloads_size"] == len(b"normal content")


class TestChecksumCalculation:
    """Tests for checksum calculation."""

    def test_calculate_file_checksum(self, cache_manager, sample_video_file):
        """Test checksum calculation."""
        checksum = cache_manager._calculate_file_checksum(sample_video_file)

        assert isinstance(checksum, str)
        assert len(checksum) == 64  # SHA-256 produces 64-character hex string

        # Verify it's reproducible
        checksum2 = cache_manager._calculate_file_checksum(sample_video_file)
        assert checksum == checksum2

    def test_calculate_file_checksum_nonexistent(self, cache_manager):
        """Test checksum calculation with nonexistent file."""
        nonexistent_file = Path("/nonexistent/file.mp4")

        with pytest.raises(RuntimeError, match="Failed to calculate checksum"):
            cache_manager._calculate_file_checksum(nonexistent_file)

    def test_calculate_file_checksum_different_files(
        self, cache_manager, temp_cache_dir
    ):
        """Test that different files produce different checksums."""
        file1 = temp_cache_dir / "file1.txt"
        file2 = temp_cache_dir / "file2.txt"

        file1.write_bytes(b"content1")
        file2.write_bytes(b"content2")

        checksum1 = cache_manager._calculate_file_checksum(file1)
        checksum2 = cache_manager._calculate_file_checksum(file2)

        assert checksum1 != checksum2
