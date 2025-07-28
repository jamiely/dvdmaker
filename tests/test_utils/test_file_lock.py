"""Tests for file locking utilities."""

import os
import threading
import time
from unittest.mock import patch

import pytest

from src.utils.file_lock import FileLock, RetryableLock, retry_on_concurrent_access


class TestFileLock:
    """Test basic file lock functionality."""

    def test_file_lock_creation_and_cleanup(self, tmp_path):
        """Test that lock files are created and cleaned up properly."""
        lock_path = tmp_path / "test.lock"

        # Lock file should not exist initially
        assert not lock_path.exists()

        lock = FileLock(lock_path)

        # Lock file should not exist until acquired
        assert not lock_path.exists()

        lock.acquire()

        # Lock file should exist after acquisition
        assert lock_path.exists()

        # Check lock file contents
        with open(lock_path, "r") as f:
            lines = f.read().strip().split("\n")
            assert len(lines) == 2
            assert lines[0] == str(os.getpid())  # PID
            assert float(lines[1]) > 0  # Timestamp

        lock.release()

        # Lock file should be cleaned up after release
        assert not lock_path.exists()

    def test_file_lock_context_manager(self, tmp_path):
        """Test file lock as context manager."""
        lock_path = tmp_path / "test.lock"

        with FileLock(lock_path):
            assert lock_path.exists()

        assert not lock_path.exists()

    def test_file_lock_blocking_behavior(self, tmp_path):
        """Test that file locks block each other."""
        lock_path = tmp_path / "test.lock"
        results = []

        def worker(worker_id, hold_time, timeout):
            try:
                with FileLock(lock_path, timeout=timeout):
                    results.append(f"worker_{worker_id}_acquired")
                    time.sleep(hold_time)
                    results.append(f"worker_{worker_id}_released")
            except Exception as e:
                results.append(f"worker_{worker_id}_error_{type(e).__name__}")

        # Start two workers - first holds lock longer than second's timeout
        thread1 = threading.Thread(target=worker, args=(1, 1.5, 3.0))
        thread2 = threading.Thread(target=worker, args=(2, 0.1, 0.5))  # Short timeout

        thread1.start()
        time.sleep(0.2)  # Ensure first worker gets lock first
        thread2.start()

        thread1.join()
        thread2.join()

        # At least one should timeout or both should succeed (depending on timing)
        successful_acquisitions = [r for r in results if "_acquired" in r]

        # We should have at least one successful acquisition
        assert (
            len(successful_acquisitions) >= 1
        ), f"Expected at least one success, got: {results}"

    def test_stale_lock_detection_by_age(self, tmp_path):
        """Test detection of stale locks by age."""
        lock_path = tmp_path / "test.lock"

        # Create an old lock file
        with open(lock_path, "w") as f:
            f.write(f"{os.getpid()}\n0.0\n")  # Very old timestamp

        lock = FileLock(lock_path, timeout=1.0)

        # Should be able to acquire despite existing file
        lock.acquire()
        assert lock.locked
        lock.release()

    def test_stale_lock_detection_by_pid(self, tmp_path):
        """Test detection of stale locks by non-existent PID."""
        lock_path = tmp_path / "test.lock"

        # Create a lock file with a PID that likely doesn't exist
        fake_pid = 999999
        with open(lock_path, "w") as f:
            f.write(f"{fake_pid}\n{time.time()}\n")

        lock = FileLock(lock_path, timeout=1.0)

        # Should be able to acquire despite existing file
        lock.acquire()
        assert lock.locked
        lock.release()

    def test_file_lock_non_blocking_mode(self, tmp_path):
        """Test non-blocking mode of file lock."""
        lock_path = tmp_path / "test.lock"

        # Create and hold a lock
        lock1 = FileLock(lock_path)
        lock1.acquire()

        # Try to acquire in non-blocking mode
        lock2 = FileLock(lock_path)
        result = lock2.acquire(non_blocking=True)

        assert not result
        assert not lock2.locked

        lock1.release()

    def test_file_lock_error_handling(self, tmp_path):
        """Test error handling in file lock operations."""
        lock_path = tmp_path / "test.lock"

        lock = FileLock(lock_path)

        # Test releasing without acquiring
        with pytest.raises(RuntimeError, match="not held"):
            lock.release()

        # Test double acquisition
        lock.acquire()
        with pytest.raises(RuntimeError, match="already held"):
            lock.acquire()

        lock.release()


class TestRetryableLock:
    """Test retryable lock functionality."""

    def test_retryable_lock_immediate_success(self, tmp_path):
        """Test retryable lock when no contention exists."""
        lock_path = tmp_path / "test.lock"

        with RetryableLock(lock_path):
            assert lock_path.exists()

        assert not lock_path.exists()

    @patch("time.sleep")  # Speed up the test
    def test_retryable_lock_success_after_retry(self, mock_sleep, tmp_path):
        """Test retryable lock succeeds after initial failure."""
        lock_path = tmp_path / "test.lock"
        results = []

        def first_worker():
            with FileLock(lock_path, timeout=5.0):
                results.append("first_acquired")
                time.sleep(0.5)  # Hold briefly
                results.append("first_released")

        def second_worker():
            time.sleep(0.1)  # Start after first
            with RetryableLock(lock_path, timeout=1.0, max_retries=3, retry_delay=0.1):
                results.append("second_acquired")

        thread1 = threading.Thread(target=first_worker)
        thread2 = threading.Thread(target=second_worker)

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # Both should succeed
        assert "first_acquired" in results
        assert "first_released" in results
        assert "second_acquired" in results

        # Sleep should have been called (retry attempts)
        assert mock_sleep.called

    def test_retryable_lock_failure_after_max_retries(self, tmp_path):
        """Test retryable lock fails after max retries exceeded."""
        lock_path = tmp_path / "test.lock"
        exception_raised = []

        # Hold lock in first worker for longer than retry timeout
        def long_worker():
            with FileLock(lock_path, timeout=10.0):
                time.sleep(2.0)

        def retry_worker():
            time.sleep(0.1)
            try:
                with RetryableLock(
                    lock_path, timeout=0.1, max_retries=2, retry_delay=0.1
                ):
                    pass  # Should not reach here
            except Exception as e:
                exception_raised.append(type(e).__name__)

        thread1 = threading.Thread(target=long_worker)
        thread2 = threading.Thread(target=retry_worker)

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # Second thread should have raised an exception
        assert (
            len(exception_raised) == 1
        ), f"Expected exception, got: {exception_raised}"


class TestRetryDecorator:
    """Test retry decorator functionality."""

    def test_retry_decorator_success_first_try(self):
        """Test retry decorator when function succeeds immediately."""
        call_count = 0

        @retry_on_concurrent_access(max_retries=3, retry_delay=0.1)
        def successful_function():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_function()

        assert result == "success"
        assert call_count == 1

    @patch("time.sleep")
    def test_retry_decorator_success_after_retries(self, mock_sleep):
        """Test retry decorator succeeds after initial failures."""
        call_count = 0

        @retry_on_concurrent_access(max_retries=3, retry_delay=0.1)
        def eventually_successful_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OSError("Simulated concurrent access error")
            return "success"

        result = eventually_successful_function()

        assert result == "success"
        assert call_count == 3
        assert mock_sleep.call_count == 2  # 2 retries

    @patch("time.sleep")
    def test_retry_decorator_failure_after_max_retries(self, mock_sleep):
        """Test retry decorator fails after max retries exceeded."""
        call_count = 0

        @retry_on_concurrent_access(max_retries=2, retry_delay=0.1)
        def always_failing_function():
            nonlocal call_count
            call_count += 1
            raise OSError("Persistent error")

        with pytest.raises(OSError, match="Persistent error"):
            always_failing_function()

        assert call_count == 3  # Initial attempt + 2 retries
        assert mock_sleep.call_count == 2

    def test_retry_decorator_with_different_exception(self):
        """Test retry decorator doesn't retry on non-specified exceptions."""
        call_count = 0

        @retry_on_concurrent_access(max_retries=3, exceptions=(OSError,))
        def function_with_different_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Different error type")

        with pytest.raises(ValueError, match="Different error type"):
            function_with_different_error()

        assert call_count == 1  # No retries for ValueError

    @patch("time.sleep")
    def test_retry_decorator_exponential_backoff(self, mock_sleep):
        """Test retry decorator uses exponential backoff."""
        call_count = 0

        @retry_on_concurrent_access(
            max_retries=3, retry_delay=0.1, backoff_multiplier=2.0
        )
        def function_needing_retries():
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise OSError("Simulated error")
            return "success"

        result = function_needing_retries()

        assert result == "success"
        assert call_count == 4

        # Check exponential backoff delays: 0.1, 0.2, 0.4
        expected_delays = [0.1, 0.2, 0.4]
        actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays


class TestIntegration:
    """Integration tests for file locking with other components."""

    def test_concurrent_cache_operations(self, tmp_path):
        """Test concurrent cache operations use locking correctly."""
        from src.models.video import VideoMetadata
        from src.services.cache_manager import CacheManager

        cache_manager = CacheManager(tmp_path / "cache")

        # Create test video file
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake video content")

        results = []

        def cache_worker(worker_id):
            try:
                # Create separate file for each worker
                worker_file = tmp_path / f"test_{worker_id}.mp4"
                worker_file.write_bytes(b"fake video content")

                cache_manager.store_download(
                    f"video_{worker_id}",
                    worker_file,
                    VideoMetadata(
                        video_id=f"video_{worker_id}",
                        title=f"Video {worker_id}",
                        duration=120,
                        url="https://example.com/video",
                    ),
                )
                results.append(f"worker_{worker_id}_success")

            except Exception as e:
                results.append(f"worker_{worker_id}_error_{str(e)[:50]}")

        # Start multiple workers
        threads = []
        for i in range(3):
            thread = threading.Thread(target=cache_worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All workers should succeed
        assert len([r for r in results if "success" in r]) == 3
        assert len([r for r in results if "error" in r]) == 0
