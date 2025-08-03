"""Tests for cleanup service functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.services.cleanup import CleanupManager, CleanupStats


@pytest.fixture
def temp_directories():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_path = Path(temp_dir)
        cache_dir = base_path / "cache"
        output_dir = base_path / "output"
        temp_cache_dir = base_path / "temp"

        # Create directory structure
        cache_dir.mkdir()
        output_dir.mkdir()
        temp_cache_dir.mkdir()

        # Create cache subdirectories
        (cache_dir / "downloads").mkdir()
        (cache_dir / "converted").mkdir()
        (cache_dir / "metadata").mkdir()
        (cache_dir / "downloads" / ".in-progress").mkdir()
        (cache_dir / "converted" / ".in-progress").mkdir()

        yield {
            "base": base_path,
            "cache": cache_dir,
            "output": output_dir,
            "temp": temp_cache_dir,
        }


@pytest.fixture
def cleanup_manager(temp_directories):
    """Create a CleanupManager instance for testing."""
    return CleanupManager(
        cache_dir=temp_directories["cache"],
        output_dir=temp_directories["output"],
        temp_dir=temp_directories["temp"],
    )


class TestCleanupStats:
    """Test CleanupStats functionality."""

    def test_cleanup_stats_initialization(self):
        """Test CleanupStats initialization."""
        stats = CleanupStats()

        assert stats.files_removed == 0
        assert stats.directories_removed == 0
        assert stats.bytes_freed == 0
        assert stats.errors == 0
        assert stats.total_items_removed == 0
        assert stats.size_freed_mb == 0.0
        assert stats.size_freed_gb == 0.0

    def test_cleanup_stats_properties(self):
        """Test CleanupStats calculated properties."""
        stats = CleanupStats()
        stats.files_removed = 5
        stats.directories_removed = 2
        stats.bytes_freed = 1024 * 1024 * 2  # 2MB
        stats.errors = 1

        assert stats.total_items_removed == 7
        assert stats.size_freed_mb == 2.0
        assert stats.size_freed_gb == 2.0 / 1024

    def test_cleanup_stats_repr(self):
        """Test CleanupStats string representation."""
        stats = CleanupStats()
        stats.files_removed = 3
        stats.directories_removed = 1
        stats.bytes_freed = 1024
        stats.errors = 0

        repr_str = repr(stats)
        assert "files=3" in repr_str
        assert "dirs=1" in repr_str
        assert "bytes=1024" in repr_str
        assert "errors=0" in repr_str


class TestCleanupManager:
    """Test CleanupManager functionality."""

    def test_cleanup_manager_initialization(self, temp_directories):
        """Test CleanupManager initialization."""
        manager = CleanupManager(
            cache_dir=temp_directories["cache"],
            output_dir=temp_directories["output"],
            temp_dir=temp_directories["temp"],
        )

        assert manager.cache_dir == temp_directories["cache"]
        assert manager.output_dir == temp_directories["output"]
        assert manager.temp_dir == temp_directories["temp"]

    def test_clean_downloads_no_directory(self, temp_directories):
        """Test cleaning downloads when directory doesn't exist."""
        # Remove downloads directory and its contents
        downloads_dir = temp_directories["cache"] / "downloads"
        import shutil

        shutil.rmtree(downloads_dir)

        manager = CleanupManager(
            cache_dir=temp_directories["cache"],
            output_dir=temp_directories["output"],
        )

        stats = manager.clean_downloads()
        assert stats.files_removed == 0
        assert stats.directories_removed == 0
        assert stats.bytes_freed == 0

    def test_clean_downloads_with_files(self, cleanup_manager, temp_directories):
        """Test cleaning downloads with files present."""
        downloads_dir = temp_directories["cache"] / "downloads"

        # Create test files
        test_files = [
            downloads_dir / "video1.mp4",
            downloads_dir / "video2.webm",
            downloads_dir / "video3.mp4",
        ]

        for file_path in test_files:
            file_path.write_bytes(b"fake video content")

        # Create hidden file that should be skipped
        hidden_file = downloads_dir / ".hidden_file"
        hidden_file.write_bytes(b"hidden content")

        stats = cleanup_manager.clean_downloads()

        assert stats.files_removed == 3
        assert stats.directories_removed == 0
        assert stats.bytes_freed > 0
        assert stats.errors == 0

        # Verify files were removed
        for file_path in test_files:
            assert not file_path.exists()

        # Verify hidden file was preserved
        assert hidden_file.exists()

    def test_clean_conversions_with_files(self, cleanup_manager, temp_directories):
        """Test cleaning conversions with files present (legacy + subdirectories)."""
        converted_dir = temp_directories["cache"] / "converted"

        # Create test files in direct structure (legacy)
        legacy_files = [
            converted_dir / "video1.mpg",
            converted_dir / "video2.mpg",
        ]

        for file_path in legacy_files:
            file_path.write_bytes(b"fake converted content")

        # Create test files in subdirectory structure (current)
        video_dirs = [
            converted_dir / "video3",
            converted_dir / "video4",
        ]

        subdirectory_files = []
        for video_dir in video_dirs:
            video_dir.mkdir(exist_ok=True)
            video_file = video_dir / f"{video_dir.name}_dvd.mpg"
            thumb_file = video_dir / f"{video_dir.name}_thumb.jpg"
            video_file.write_bytes(b"fake converted video")
            thumb_file.write_bytes(b"fake thumbnail")
            subdirectory_files.extend([video_file, thumb_file])

        # Create metadata file
        metadata_file = converted_dir / "converted_metadata.json"
        metadata_file.write_text(
            '{"video3": {"path": "test"}, "video4": {"path": "test"}}'
        )

        # Create hidden file that should be preserved
        hidden_file = converted_dir / ".in-progress"
        hidden_file.mkdir(exist_ok=True)
        (hidden_file / "temp.txt").write_bytes(b"in progress content")

        stats = cleanup_manager.clean_conversions()

        # Remove 2 legacy + 4 subdirectory + 1 metadata = 7 files
        # Should remove 2 video subdirectories
        assert stats.files_removed == 7
        assert stats.directories_removed == 2
        assert stats.bytes_freed > 0

        # Verify legacy files were removed
        for file_path in legacy_files:
            assert not file_path.exists()

        # Verify subdirectory files were removed
        for file_path in subdirectory_files:
            assert not file_path.exists()

        # Verify subdirectories were removed
        for video_dir in video_dirs:
            assert not video_dir.exists()

        # Verify metadata file was removed
        assert not metadata_file.exists()

        # Verify hidden directory was preserved
        assert hidden_file.exists()
        assert (hidden_file / "temp.txt").exists()

    def test_clean_dvd_output_with_video_ts(self, cleanup_manager, temp_directories):
        """Test cleaning DVD output directories."""
        output_dir = temp_directories["output"]

        # Create playlist directories with VIDEO_TS
        playlist_dirs = [
            output_dir / "playlist1",
            output_dir / "playlist2",
        ]

        for playlist_dir in playlist_dirs:
            playlist_dir.mkdir()
            video_ts_dir = playlist_dir / "VIDEO_TS"
            video_ts_dir.mkdir()

            # Create some DVD files
            (video_ts_dir / "VIDEO_TS.IFO").write_bytes(b"fake dvd data")
            (video_ts_dir / "VTS_01_1.VOB").write_bytes(b"fake video data")

        stats = cleanup_manager.clean_dvd_output()

        assert stats.files_removed == 0
        assert stats.directories_removed == 2  # Two VIDEO_TS directories
        assert stats.bytes_freed > 0

        # Verify VIDEO_TS directories were removed
        for playlist_dir in playlist_dirs:
            video_ts_dir = playlist_dir / "VIDEO_TS"
            assert not video_ts_dir.exists()
            # But playlist directory should still exist
            assert playlist_dir.exists()

    def test_clean_isos_with_files(self, cleanup_manager, temp_directories):
        """Test cleaning ISO files."""
        output_dir = temp_directories["output"]

        # Create ISO files in various locations
        iso_files = [
            output_dir / "playlist1.iso",
            output_dir / "subdir" / "playlist2.iso",
        ]

        # Create subdirectory
        (output_dir / "subdir").mkdir()

        for iso_file in iso_files:
            iso_file.write_bytes(b"fake iso content")

        stats = cleanup_manager.clean_isos()

        assert stats.files_removed == 2
        assert stats.directories_removed == 0
        assert stats.bytes_freed > 0

        # Verify ISO files were removed
        for iso_file in iso_files:
            assert not iso_file.exists()

    def test_clean_temp_files(self, cleanup_manager, temp_directories):
        """Test cleaning temporary files."""
        temp_dir = temp_directories["temp"]

        # Create temp files and directories
        temp_file = temp_dir / "temp_file.tmp"
        temp_subdir = temp_dir / "temp_subdir"

        temp_file.write_bytes(b"temp content")
        temp_subdir.mkdir()
        (temp_subdir / "nested_file.tmp").write_bytes(b"nested temp content")

        stats = cleanup_manager.clean_temp_files()

        assert stats.total_items_removed == 2  # file + directory
        assert stats.bytes_freed > 0

        # Verify temp items were removed
        assert not temp_file.exists()
        assert not temp_subdir.exists()

    def test_clean_all_comprehensive(self, cleanup_manager, temp_directories):
        """Test comprehensive cleanup of all data types."""
        # Set up data in all locations
        downloads_dir = temp_directories["cache"] / "downloads"
        converted_dir = temp_directories["cache"] / "converted"
        output_dir = temp_directories["output"]
        temp_dir = temp_directories["temp"]

        # Create download files
        (downloads_dir / "video1.mp4").write_bytes(b"download content")

        # Create conversion files
        (converted_dir / "video1.mpg").write_bytes(b"converted content")

        # Create DVD output
        playlist_dir = output_dir / "playlist1"
        playlist_dir.mkdir()
        video_ts_dir = playlist_dir / "VIDEO_TS"
        video_ts_dir.mkdir()
        (video_ts_dir / "VIDEO_TS.IFO").write_bytes(b"dvd content")

        # Create ISO
        (output_dir / "playlist1.iso").write_bytes(b"iso content")

        # Create temp files
        (temp_dir / "temp.tmp").write_bytes(b"temp content")

        results = cleanup_manager.clean_all()

        # Verify all cleanup types were executed
        assert "downloads" in results
        assert "conversions" in results
        assert "dvd_output" in results
        assert "isos" in results
        assert "temp" in results

        # Verify files were cleaned
        total_files = sum(stats.files_removed for stats in results.values())
        total_dirs = sum(stats.directories_removed for stats in results.values())

        assert total_files > 0
        assert total_dirs > 0

    def test_get_cleanup_preview_downloads(self, cleanup_manager, temp_directories):
        """Test cleanup preview for downloads."""
        downloads_dir = temp_directories["cache"] / "downloads"

        # Create test files
        test_files = [
            downloads_dir / "video1.mp4",
            downloads_dir / "video2.mp4",
        ]

        for file_path in test_files:
            file_path.write_bytes(b"content")

        # Create hidden file (should be excluded)
        (downloads_dir / ".hidden").write_bytes(b"hidden")

        preview = cleanup_manager.get_cleanup_preview("downloads")

        assert len(preview) == 2
        assert all(item.name.endswith(".mp4") for item in preview)

    def test_get_cleanup_preview_all(self, cleanup_manager, temp_directories):
        """Test cleanup preview for all types."""
        # Set up minimal data
        downloads_dir = temp_directories["cache"] / "downloads"
        (downloads_dir / "video1.mp4").write_bytes(b"content")

        output_dir = temp_directories["output"]
        (output_dir / "test.iso").write_bytes(b"iso content")

        preview = cleanup_manager.get_cleanup_preview("all")

        assert len(preview) >= 2  # At least the download and ISO

    @patch("src.services.cleanup.shutil.rmtree")
    def test_cleanup_error_handling(
        self, mock_rmtree, cleanup_manager, temp_directories
    ):
        """Test error handling during cleanup operations."""
        # Set up a directory to clean
        output_dir = temp_directories["output"]
        playlist_dir = output_dir / "playlist1"
        playlist_dir.mkdir()
        video_ts_dir = playlist_dir / "VIDEO_TS"
        video_ts_dir.mkdir()
        (video_ts_dir / "test.file").write_bytes(b"content")

        # Mock rmtree to raise an error
        mock_rmtree.side_effect = OSError("Permission denied")

        stats = cleanup_manager.clean_dvd_output()

        # Should have recorded the error
        assert stats.errors == 1
        assert stats.directories_removed == 0

    def test_dry_run_mode(self, cleanup_manager, temp_directories):
        """Test dry run mode doesn't actually remove files."""
        downloads_dir = temp_directories["cache"] / "downloads"
        test_file = downloads_dir / "video1.mp4"
        test_file.write_bytes(b"content")

        # Run in dry run mode
        stats = cleanup_manager.clean_downloads(dry_run=True)

        # File should still exist
        assert test_file.exists()

        # But stats should reflect what would have been cleaned
        assert stats.bytes_freed > 0
