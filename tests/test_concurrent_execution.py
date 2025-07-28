"""Tests for concurrent script execution scenarios.

This module tests the file locking and concurrent access protection
mechanisms to ensure safe execution of multiple script instances.
"""

import threading
import time
from unittest.mock import Mock, patch

import pytest

from src.models.video import VideoMetadata
from src.services.cache_manager import CacheManager
from src.utils.file_lock import FileLock, RetryableLock


class TestFileLocking:
    """Test file locking mechanisms."""

    def test_file_lock_basic_usage(self, tmp_path):
        """Test basic file lock usage."""
        lock_path = tmp_path / "test.lock"

        with FileLock(lock_path):
            assert lock_path.exists()

        # Lock should be released
        assert not lock_path.exists()

    def test_concurrent_file_lock_blocks(self, tmp_path):
        """Test that concurrent file locks block each other."""
        lock_path = tmp_path / "test.lock"
        results = []

        def worker(worker_id):
            try:
                with FileLock(lock_path, timeout=0.5):  # Shorter timeout
                    results.append(f"worker_{worker_id}_start")
                    time.sleep(1.0)  # Hold lock longer than timeout
                    results.append(f"worker_{worker_id}_end")
            except Exception as e:
                results.append(f"worker_{worker_id}_error_{type(e).__name__}")

        # Start first worker
        thread1 = threading.Thread(target=worker, args=(1,))
        thread1.start()

        # Wait a bit to ensure first worker gets the lock
        time.sleep(0.1)

        # Start second worker
        thread2 = threading.Thread(target=worker, args=(2,))
        thread2.start()

        # Wait for completion
        thread1.join()
        thread2.join()

        # One should succeed, one should timeout
        assert len(results) >= 2

        # At least one should timeout due to the lock
        timeout_errors = [r for r in results if "error_TimeoutError" in r]
        successful_completions = [r for r in results if r.endswith("_end")]

        # We expect at least one timeout error and at least one successful completion
        assert (
            len(timeout_errors) >= 1
        ), f"Expected at least one timeout, got: {results}"
        assert (
            len(successful_completions) >= 1
        ), f"Expected at least one success, got: {results}"

    def test_retryable_lock_success_after_retry(self, tmp_path):
        """Test that RetryableLock succeeds after initial failure."""
        lock_path = tmp_path / "test.lock"
        results = []

        def first_worker():
            with FileLock(lock_path, timeout=5.0):
                results.append("first_worker_acquired")
                time.sleep(1.0)  # Hold lock briefly
                results.append("first_worker_released")

        def second_worker():
            time.sleep(0.2)  # Start slightly after first worker
            try:
                with RetryableLock(
                    lock_path, timeout=2.0, max_retries=3, retry_delay=0.3
                ):
                    results.append("second_worker_acquired")
            except Exception as e:
                results.append(f"second_worker_error_{type(e).__name__}")

        # Start workers
        thread1 = threading.Thread(target=first_worker)
        thread2 = threading.Thread(target=second_worker)

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # Both should succeed
        assert "first_worker_acquired" in results
        assert "first_worker_released" in results
        assert "second_worker_acquired" in results

    def test_stale_lock_cleanup(self, tmp_path):
        """Test that stale locks are properly cleaned up."""
        lock_path = tmp_path / "test.lock"

        # Create a stale lock file (old timestamp, fake PID)
        with open(lock_path, "w") as f:
            f.write("99999\n0.0\n")  # Fake PID and very old timestamp

        # Should be able to acquire lock despite existing file
        with FileLock(lock_path, timeout=1.0):
            assert True  # Lock acquired successfully


class TestConcurrentCacheAccess:
    """Test concurrent access to cache manager."""

    @pytest.fixture
    def cache_manager(self, tmp_path):
        """Create a cache manager for testing."""
        return CacheManager(
            cache_dir=tmp_path / "cache", force_download=False, force_convert=False
        )

    @pytest.fixture
    def video_metadata(self):
        """Create test video metadata."""
        return VideoMetadata(
            video_id="test_video_123",
            title="Test Video",
            duration=120,
            url="https://example.com/video",
            thumbnail_url=None,
            description="Test description",
        )

    def test_concurrent_download_cache_access(
        self, cache_manager, video_metadata, tmp_path
    ):
        """Test concurrent access to download cache."""
        results = []
        errors = []

        # Create a temporary video file to cache
        video_file = tmp_path / "test_video.mp4"
        video_file.write_bytes(b"fake video content")

        def cache_worker(worker_id):
            try:
                video_file_copy = tmp_path / f"test_video_{worker_id}.mp4"
                video_file_copy.write_bytes(b"fake video content")

                cached_video = cache_manager.store_download(
                    video_metadata.video_id, video_file_copy, video_metadata
                )
                results.append(f"worker_{worker_id}_success")
                return cached_video

            except Exception as e:
                errors.append(
                    f"worker_{worker_id}_error_{type(e).__name__}_{str(e)[:50]}"
                )

        # Start multiple workers trying to cache the same video
        threads = []
        for i in range(3):
            thread = threading.Thread(target=cache_worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # At least one should succeed, others might get blocked or succeed
        assert len(results) >= 1

        # Check that cache file exists and is valid
        assert cache_manager.is_download_cached(video_metadata.video_id)

    def test_concurrent_metadata_access(self, cache_manager):
        """Test concurrent access to metadata storage."""
        from src.models.playlist import PlaylistMetadata

        playlist_metadata = PlaylistMetadata(
            playlist_id="test_playlist_123",
            title="Test Playlist",
            description="Test description",
            video_count=5,
            total_size_estimate=1000000,
        )

        results = []
        errors = []

        def metadata_worker(worker_id):
            try:
                cache_manager.store_playlist_metadata(playlist_metadata)
                results.append(f"worker_{worker_id}_success")

            except Exception as e:
                errors.append(f"worker_{worker_id}_error_{type(e).__name__}")

        # Start multiple workers trying to store the same metadata
        threads = []
        for i in range(3):
            thread = threading.Thread(target=metadata_worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # All should succeed (or at least one)
        assert len(results) >= 1

        # Check that metadata was stored
        cached_metadata = cache_manager.get_cached_playlist_metadata(
            playlist_metadata.playlist_id
        )
        assert cached_metadata is not None
        assert cached_metadata.playlist_id == playlist_metadata.playlist_id

    def test_cache_hit_miss_consistency(self, cache_manager, video_metadata, tmp_path):
        """Test that cache hit/miss logic is consistent during concurrent access."""
        # Create a video file
        video_file = tmp_path / "test_video.mp4"
        video_file.write_bytes(b"fake video content")

        # Store it in cache first
        cache_manager.store_download(
            video_metadata.video_id, video_file, video_metadata
        )

        results = []

        def check_cache_worker(worker_id):
            is_cached = cache_manager.is_download_cached(video_metadata.video_id)
            cached_video = cache_manager.get_cached_download(video_metadata.video_id)

            results.append(
                {
                    "worker_id": worker_id,
                    "is_cached": is_cached,
                    "has_cached_video": cached_video is not None,
                }
            )

        # Start multiple workers checking cache status
        threads = []
        for i in range(5):
            thread = threading.Thread(target=check_cache_worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # All workers should see consistent cache status
        assert len(results) == 5
        assert all(r["is_cached"] for r in results)
        assert all(r["has_cached_video"] for r in results)


class TestPlaylistSpecificDirectories:
    """Test playlist-specific output directory isolation."""

    def test_playlist_directory_creation(self, tmp_path):
        """Test that playlist-specific directories are created correctly."""
        from src.services.cache_manager import CacheManager
        from src.services.dvd_author import DVDAuthor
        from src.services.tool_manager import ToolManager

        # Mock dependencies
        settings = Mock()
        settings.output_dir = tmp_path / "output"
        settings.video_format = "ntsc"
        settings.aspect_ratio = "4:3"

        tool_manager = Mock(spec=ToolManager)
        cache_manager = Mock(spec=CacheManager)

        dvd_author = DVDAuthor(settings, tool_manager, cache_manager)

        # Test directory creation for different playlist IDs
        playlist_ids = ["PLtest123", "PLother456", "PLspecial_chars!@#"]
        created_dirs = []

        for playlist_id in playlist_ids:
            playlist_dir = dvd_author._create_playlist_output_dir(
                settings.output_dir, playlist_id
            )
            created_dirs.append(playlist_dir)
            assert playlist_dir.exists()
            assert playlist_dir.parent == settings.output_dir

        # All directories should be different
        assert len(set(created_dirs)) == len(playlist_ids)

    def test_concurrent_dvd_creation_isolation(self, tmp_path):
        """Test that concurrent DVD creation operations are isolated."""
        # This would require more complex mocking of the entire DVD creation process
        # For now, we test the directory isolation aspect

        from src.services.dvd_author import DVDAuthor

        settings = Mock()
        settings.output_dir = tmp_path / "output"

        tool_manager = Mock()
        cache_manager = Mock()

        dvd_author = DVDAuthor(settings, tool_manager, cache_manager)

        results = []

        def create_playlist_dir_worker(playlist_id):
            try:
                playlist_dir = dvd_author._create_playlist_output_dir(
                    settings.output_dir, playlist_id
                )
                results.append(
                    {
                        "playlist_id": playlist_id,
                        "directory": playlist_dir,
                        "success": True,
                    }
                )
            except Exception as e:
                results.append(
                    {"playlist_id": playlist_id, "error": str(e), "success": False}
                )

        # Start workers for different playlists
        playlist_ids = [f"PLtest{i}" for i in range(5)]
        threads = []

        for playlist_id in playlist_ids:
            thread = threading.Thread(
                target=create_playlist_dir_worker, args=(playlist_id,)
            )
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # All should succeed
        assert len(results) == 5
        assert all(r["success"] for r in results)

        # All directories should be different
        directories = [r["directory"] for r in results if r["success"]]
        assert len(set(directories)) == len(directories)


class TestRaceConditions:
    """Test for race conditions in various scenarios."""

    def test_filename_mapping_race_condition(self, tmp_path):
        """Test that filename mapping updates don't corrupt each other."""
        cache_manager = CacheManager(
            cache_dir=tmp_path / "cache", force_download=False, force_convert=False
        )

        results = []

        def filename_mapping_worker(worker_id):
            try:
                # Get normalized filename (this triggers mapping updates)
                for i in range(5):
                    video_id = f"video_{worker_id}_{i}"
                    title = f"Test Video {worker_id} - {i} 测试视频"

                    normalized = cache_manager.get_normalized_filename(video_id, title)
                    results.append(
                        {
                            "worker_id": worker_id,
                            "video_id": video_id,
                            "normalized": normalized,
                        }
                    )

                # Save mapping
                cache_manager.save_filename_mapping()

            except Exception as e:
                results.append({"worker_id": worker_id, "error": str(e)})

        # Start multiple workers
        threads = []
        for i in range(3):
            thread = threading.Thread(target=filename_mapping_worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Check that no errors occurred
        error_results = [r for r in results if "error" in r]
        assert len(error_results) == 0, f"Errors occurred: {error_results}"

        # Check that all mappings were recorded
        success_results = [r for r in results if "normalized" in r]
        assert len(success_results) == 15  # 3 workers * 5 videos each

    @patch("time.sleep")  # Speed up the test
    def test_lock_timeout_and_retry(self, mock_sleep, tmp_path):
        """Test lock timeout and retry behavior."""
        lock_path = tmp_path / "test.lock"
        results = []

        def long_running_worker():
            try:
                with FileLock(lock_path, timeout=10.0):
                    results.append("long_worker_acquired")
                    time.sleep(2.0)  # Hold lock for a while
                    results.append("long_worker_released")
            except Exception as e:
                results.append(f"long_worker_error_{type(e).__name__}")

        def retry_worker():
            time.sleep(0.1)  # Start after long worker
            try:
                with RetryableLock(
                    lock_path, timeout=0.5, max_retries=5, retry_delay=0.1
                ):
                    results.append("retry_worker_acquired")
            except Exception as e:
                results.append(f"retry_worker_error_{type(e).__name__}")

        # Start both workers
        thread1 = threading.Thread(target=long_running_worker)
        thread2 = threading.Thread(target=retry_worker)

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # Both should eventually succeed
        assert "long_worker_acquired" in results
        assert "long_worker_released" in results
        assert "retry_worker_acquired" in results


if __name__ == "__main__":
    pytest.main([__file__])
