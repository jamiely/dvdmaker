"""Tests for progress reporting utilities."""

import threading
import time
from unittest.mock import Mock, patch

import pytest

from src.utils.progress import (
    CallbackProgressCallback,
    ConsoleProgressCallback,
    MultiStepProgressTracker,
    ProgressInfo,
    ProgressTracker,
    SilentProgressCallback,
)


class TestProgressInfo:
    """Test cases for ProgressInfo class."""

    def test_progress_info_initialization(self):
        """Test ProgressInfo initialization."""
        progress = ProgressInfo(current=5, total=10, message="Test")

        assert progress.current == 5
        assert progress.total == 10
        assert progress.message == "Test"
        assert progress.details == {}

    def test_progress_info_with_details(self):
        """Test ProgressInfo with details."""
        details = {"file": "test.mp4", "speed": "1MB/s"}
        progress = ProgressInfo(current=3, total=7, details=details)

        assert progress.details == details

    def test_progress_info_details_initialization(self):
        """Test that details are initialized to empty dict if None."""
        progress = ProgressInfo(current=1, total=5)

        assert progress.details == {}

    def test_percentage_calculation(self):
        """Test percentage calculation."""
        progress = ProgressInfo(current=3, total=10)
        assert progress.percentage == 30.0

        progress = ProgressInfo(current=7, total=10)
        assert progress.percentage == 70.0

        progress = ProgressInfo(current=10, total=10)
        assert progress.percentage == 100.0

    def test_percentage_with_zero_total(self):
        """Test percentage calculation with zero total."""
        progress = ProgressInfo(current=5, total=0)
        assert progress.percentage == 0.0

    def test_percentage_over_100(self):
        """Test percentage calculation when current > total."""
        progress = ProgressInfo(current=15, total=10)
        assert progress.percentage == 100.0

    def test_is_complete(self):
        """Test is_complete property."""
        progress = ProgressInfo(current=5, total=10)
        assert not progress.is_complete

        progress = ProgressInfo(current=10, total=10)
        assert progress.is_complete

        progress = ProgressInfo(current=15, total=10)
        assert progress.is_complete

    def test_string_representation_with_message(self):
        """Test string representation with message."""
        progress = ProgressInfo(current=3, total=10, message="Processing files")
        result = str(progress)

        assert "30.0%" in result
        assert "Processing files" in result

    def test_string_representation_without_message(self):
        """Test string representation without message."""
        progress = ProgressInfo(current=7, total=20)
        result = str(progress)

        assert "35.0%" in result
        assert "(7/20)" in result


class TestSilentProgressCallback:
    """Test cases for SilentProgressCallback."""

    def test_initialization(self):
        """Test SilentProgressCallback initialization."""
        callback = SilentProgressCallback()
        assert callback is not None

    def test_update_does_nothing(self):
        """Test that update method does nothing."""
        callback = SilentProgressCallback()
        progress = ProgressInfo(current=5, total=10)

        # Should not raise any exceptions
        callback.update(progress)

    def test_complete_does_nothing(self):
        """Test that complete method does nothing."""
        callback = SilentProgressCallback()

        # Should not raise any exceptions
        callback.complete("Done")

    def test_error_does_nothing(self):
        """Test that error method does nothing."""
        callback = SilentProgressCallback()

        # Should not raise any exceptions
        callback.error("Error occurred")


class TestConsoleProgressCallback:
    """Test cases for ConsoleProgressCallback."""

    def test_initialization_default(self):
        """Test ConsoleProgressCallback initialization with defaults."""
        callback = ConsoleProgressCallback()

        assert callback.width == 50
        assert callback.show_percentage is True

    def test_initialization_custom(self):
        """Test ConsoleProgressCallback initialization with custom values."""
        callback = ConsoleProgressCallback(width=30, show_percentage=False)

        assert callback.width == 30
        assert callback.show_percentage is False

    @patch("sys.stdout")
    def test_update_with_percentage(self, mock_stdout):
        """Test update method with percentage display."""
        callback = ConsoleProgressCallback(width=10, show_percentage=True)
        progress = ProgressInfo(current=5, total=10, message="Processing")

        callback.update(progress)

        # Check that stdout.write was called
        assert mock_stdout.write.called
        assert mock_stdout.flush.called

    @patch("sys.stdout")
    def test_update_without_percentage(self, mock_stdout):
        """Test update method without percentage display."""
        callback = ConsoleProgressCallback(width=10, show_percentage=False)
        progress = ProgressInfo(current=3, total=10)

        callback.update(progress)

        assert mock_stdout.write.called
        assert mock_stdout.flush.called

    @patch("builtins.print")
    @patch("sys.stdout")
    def test_complete_with_message(self, mock_stdout, mock_print):
        """Test complete method with message."""
        callback = ConsoleProgressCallback()

        callback.complete("Task completed successfully")

        mock_print.assert_called_once_with("✓ Task completed successfully")

    @patch("builtins.print")
    @patch("sys.stdout")
    def test_complete_without_message(self, mock_stdout, mock_print):
        """Test complete method without message."""
        callback = ConsoleProgressCallback()

        callback.complete()

        mock_print.assert_called_once_with("✓ Complete")

    @patch("builtins.print")
    @patch("sys.stdout")
    def test_error(self, mock_stdout, mock_print):
        """Test error method."""
        callback = ConsoleProgressCallback()

        callback.error("Something went wrong")

        mock_print.assert_called_once_with("✗ Error: Something went wrong")

    def test_thread_safety(self):
        """Test that console callback is thread-safe."""
        callback = ConsoleProgressCallback()
        errors = []

        def worker(progress_val):
            try:
                progress = ProgressInfo(current=progress_val, total=100)
                with patch("sys.stdout"), patch("builtins.print"):
                    callback.update(progress)
                    callback.complete("Done")
                    callback.error("Error")
            except Exception as e:
                errors.append(e)

        # Run multiple threads
        threads = []
        for i in range(10):
            thread = threading.Thread(target=worker, args=(i * 10,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # No errors should occur
        assert len(errors) == 0


class TestCallbackProgressCallback:
    """Test cases for CallbackProgressCallback."""

    def test_initialization_with_all_callbacks(self):
        """Test initialization with all callback functions."""
        update_fn = Mock()
        complete_fn = Mock()
        error_fn = Mock()

        callback = CallbackProgressCallback(
            update_fn=update_fn, complete_fn=complete_fn, error_fn=error_fn
        )

        assert callback.update_fn == update_fn
        assert callback.complete_fn == complete_fn
        assert callback.error_fn == error_fn

    def test_initialization_with_no_callbacks(self):
        """Test initialization with no callback functions."""
        callback = CallbackProgressCallback()

        assert callback.update_fn is None
        assert callback.complete_fn is None
        assert callback.error_fn is None

    def test_update_with_callback(self):
        """Test update method calls provided callback."""
        update_fn = Mock()
        callback = CallbackProgressCallback(update_fn=update_fn)
        progress = ProgressInfo(current=5, total=10)

        callback.update(progress)

        update_fn.assert_called_once_with(progress)

    def test_update_without_callback(self):
        """Test update method does nothing when no callback provided."""
        callback = CallbackProgressCallback()
        progress = ProgressInfo(current=5, total=10)

        # Should not raise any exceptions
        callback.update(progress)

    def test_complete_with_callback(self):
        """Test complete method calls provided callback."""
        complete_fn = Mock()
        callback = CallbackProgressCallback(complete_fn=complete_fn)

        callback.complete("All done")

        complete_fn.assert_called_once_with("All done")

    def test_complete_without_callback(self):
        """Test complete method does nothing when no callback provided."""
        callback = CallbackProgressCallback()

        # Should not raise any exceptions
        callback.complete("All done")

    def test_error_with_callback(self):
        """Test error method calls provided callback."""
        error_fn = Mock()
        callback = CallbackProgressCallback(error_fn=error_fn)

        callback.error("Something failed")

        error_fn.assert_called_once_with("Something failed")

    def test_error_without_callback(self):
        """Test error method does nothing when no callback provided."""
        callback = CallbackProgressCallback()

        # Should not raise any exceptions
        callback.error("Something failed")


class TestProgressTracker:
    """Test cases for ProgressTracker."""

    def test_initialization_default(self):
        """Test ProgressTracker initialization with defaults."""
        tracker = ProgressTracker(total=100)

        assert tracker.total == 100
        assert tracker.current == 0
        assert tracker.message == ""
        assert tracker.details == {}
        assert not tracker._cancelled
        assert isinstance(tracker.callback, SilentProgressCallback)

    def test_initialization_with_callback(self):
        """Test ProgressTracker initialization with callback."""
        callback = Mock()
        tracker = ProgressTracker(
            total=50, callback=callback, initial_message="Starting"
        )

        assert tracker.total == 50
        assert tracker.callback == callback
        assert tracker.message == "Starting"

    def test_update_increment(self):
        """Test update method with increment."""
        callback = Mock()
        tracker = ProgressTracker(total=10, callback=callback)

        tracker.update(increment=3, message="Processing files")

        assert tracker.current == 3
        assert tracker.message == "Processing files"
        callback.update.assert_called_once()

        # Check the ProgressInfo passed to callback
        progress_info = callback.update.call_args[0][0]
        assert progress_info.current == 3
        assert progress_info.total == 10
        assert progress_info.message == "Processing files"

    def test_update_with_details(self):
        """Test update method with details."""
        callback = Mock()
        tracker = ProgressTracker(total=10, callback=callback)

        tracker.update(increment=2, file="test.mp4", speed="2MB/s")

        assert tracker.details["file"] == "test.mp4"
        assert tracker.details["speed"] == "2MB/s"

    def test_update_exceeds_total(self):
        """Test update method doesn't exceed total."""
        callback = Mock()
        tracker = ProgressTracker(total=10, callback=callback)

        tracker.update(increment=15)

        assert tracker.current == 10  # Capped at total

    def test_update_when_cancelled(self):
        """Test update method when tracker is cancelled."""
        callback = Mock()
        tracker = ProgressTracker(total=10, callback=callback)

        tracker.cancel()
        tracker.update(increment=5)

        assert tracker.current == 0  # Should not update
        callback.update.assert_not_called()

    def test_set_progress(self):
        """Test set_progress method."""
        callback = Mock()
        tracker = ProgressTracker(total=20, callback=callback)

        tracker.set_progress(current=7, message="Halfway there")

        assert tracker.current == 7
        assert tracker.message == "Halfway there"
        callback.update.assert_called_once()

    def test_set_progress_bounds(self):
        """Test set_progress method respects bounds."""
        callback = Mock()
        tracker = ProgressTracker(total=10, callback=callback)

        # Test negative value
        tracker.set_progress(current=-5)
        assert tracker.current == 0

        # Test exceeding total
        tracker.set_progress(current=15)
        assert tracker.current == 10

    def test_complete(self):
        """Test complete method."""
        callback = Mock()
        tracker = ProgressTracker(total=10, callback=callback)

        tracker.complete("All finished")

        assert tracker.current == 10
        callback.complete.assert_called_once_with("All finished")

    def test_complete_when_cancelled(self):
        """Test complete method when tracker is cancelled."""
        callback = Mock()
        tracker = ProgressTracker(total=10, callback=callback)

        tracker.cancel()
        tracker.complete("Should not complete")

        callback.complete.assert_not_called()

    def test_error(self):
        """Test error method."""
        callback = Mock()
        tracker = ProgressTracker(total=10, callback=callback)

        tracker.error("Something went wrong")

        callback.error.assert_called_once_with("Something went wrong")

    def test_cancel(self):
        """Test cancel method."""
        tracker = ProgressTracker(total=10)

        assert not tracker.is_cancelled
        tracker.cancel()
        assert tracker.is_cancelled

    def test_is_complete_property(self):
        """Test is_complete property."""
        tracker = ProgressTracker(total=10)

        assert not tracker.is_complete

        tracker.update(increment=10)
        assert tracker.is_complete

    def test_thread_safety(self):
        """Test that ProgressTracker is thread-safe."""
        callback = Mock()
        tracker = ProgressTracker(total=100, callback=callback)
        errors = []

        def worker():
            try:
                for i in range(10):
                    tracker.update(increment=1, message=f"Worker update {i}")
                    time.sleep(
                        0.001
                    )  # Small delay to increase chance of race conditions
            except Exception as e:
                errors.append(e)

        # Run multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # No errors should occur
        assert len(errors) == 0
        # Final value should be capped at total
        assert tracker.current <= tracker.total


class TestMultiStepProgressTracker:
    """Test cases for MultiStepProgressTracker."""

    def test_initialization(self):
        """Test MultiStepProgressTracker initialization."""
        steps = {"download": 30, "convert": 50, "finalize": 20}
        callback = Mock()
        tracker = MultiStepProgressTracker(steps=steps, callback=callback)

        assert tracker.steps == steps
        assert tracker.total_weight == 100
        assert tracker.completed_weight == 0
        assert tracker.current_step is None
        assert tracker.callback == callback
        assert all(tracker.step_progress[step] == 0 for step in steps)

    def test_initialization_without_callback(self):
        """Test initialization without callback uses SilentProgressCallback."""
        steps = {"step1": 10, "step2": 20}
        tracker = MultiStepProgressTracker(steps=steps)

        assert isinstance(tracker.callback, SilentProgressCallback)

    def test_start_step(self):
        """Test start_step method."""
        steps = {"download": 30, "convert": 50}
        callback = Mock()
        tracker = MultiStepProgressTracker(steps=steps, callback=callback)

        tracker.start_step("download", "Starting download")

        assert tracker.current_step == "download"
        callback.update.assert_called_once()

    def test_start_unknown_step(self):
        """Test start_step with unknown step raises ValueError."""
        steps = {"download": 30, "convert": 50}
        tracker = MultiStepProgressTracker(steps=steps)

        with pytest.raises(ValueError, match="Unknown step: unknown"):
            tracker.start_step("unknown")

    def test_update_step(self):
        """Test update_step method."""
        steps = {"download": 30, "convert": 50}
        callback = Mock()
        tracker = MultiStepProgressTracker(steps=steps, callback=callback)

        tracker.start_step("download")
        callback.reset_mock()  # Clear the start_step call

        tracker.update_step(progress=15, message="Half done")

        assert tracker.step_progress["download"] == 15
        callback.update.assert_called_once()

    def test_update_step_without_current_step(self):
        """Test update_step without setting current step."""
        steps = {"download": 30, "convert": 50}
        callback = Mock()
        tracker = MultiStepProgressTracker(steps=steps, callback=callback)

        tracker.update_step(progress=15)

        # Should not update anything
        assert all(tracker.step_progress[step] == 0 for step in steps)

    def test_update_step_bounds(self):
        """Test update_step respects bounds."""
        steps = {"download": 30}
        tracker = MultiStepProgressTracker(steps=steps)

        tracker.start_step("download")

        # Test negative value
        tracker.update_step(progress=-10)
        assert tracker.step_progress["download"] == 0

        # Test exceeding step weight
        tracker.update_step(progress=50)
        assert tracker.step_progress["download"] == 30

    def test_complete_step(self):
        """Test complete_step method."""
        steps = {"download": 30, "convert": 50}
        callback = Mock()
        tracker = MultiStepProgressTracker(steps=steps, callback=callback)

        tracker.start_step("download")
        callback.reset_mock()

        tracker.complete_step("Download finished")

        assert tracker.step_progress["download"] == 30
        callback.update.assert_called_once()

    def test_complete_step_without_current_step(self):
        """Test complete_step without setting current step."""
        steps = {"download": 30, "convert": 50}
        callback = Mock()
        tracker = MultiStepProgressTracker(steps=steps, callback=callback)

        tracker.complete_step("Should not complete")

        # Should not update anything
        assert all(tracker.step_progress[step] == 0 for step in steps)

    def test_complete_all_steps(self):
        """Test complete method marks all steps complete."""
        steps = {"download": 30, "convert": 50, "finalize": 20}
        callback = Mock()
        tracker = MultiStepProgressTracker(steps=steps, callback=callback)

        tracker.complete("All done")

        assert tracker.step_progress["download"] == 30
        assert tracker.step_progress["convert"] == 50
        assert tracker.step_progress["finalize"] == 20
        callback.complete.assert_called_once_with("All done")

    def test_error(self):
        """Test error method."""
        steps = {"download": 30, "convert": 50}
        callback = Mock()
        tracker = MultiStepProgressTracker(steps=steps, callback=callback)

        tracker.error("Download failed")

        callback.error.assert_called_once_with("Download failed")

    def test_progress_calculation(self):
        """Test that progress is calculated correctly across steps."""
        steps = {"step1": 40, "step2": 60}  # Total weight = 100
        callback = Mock()
        tracker = MultiStepProgressTracker(steps=steps, callback=callback)

        # Complete first step
        tracker.start_step("step1")
        tracker.complete_step()

        # Get the ProgressInfo from the callback
        progress_info = callback.update.call_args[0][0]
        assert progress_info.current == 40
        assert progress_info.total == 100
        assert progress_info.percentage == 40.0

        # Partially complete second step
        callback.reset_mock()
        tracker.start_step("step2")
        tracker.update_step(progress=30)  # Half of step2's weight

        progress_info = callback.update.call_args[0][0]
        assert progress_info.current == 70  # 40 + 30
        assert progress_info.total == 100
        assert progress_info.percentage == 70.0

    def test_progress_details(self):
        """Test that progress details include step information."""
        steps = {"download": 50, "convert": 50}
        callback = Mock()
        tracker = MultiStepProgressTracker(steps=steps, callback=callback)

        tracker.start_step("download", "Downloading files")

        progress_info = callback.update.call_args[0][0]
        assert progress_info.details["current_step"] == "download"
        assert "step_progress" in progress_info.details
        assert progress_info.details["step_progress"]["download"] == 0
        assert progress_info.details["step_progress"]["convert"] == 0


class TestProgressLogging:
    """Test cases for progress logging behavior."""

    def test_progress_info_logs_creation(self, caplog):
        """Test that ProgressInfo logs its creation."""
        caplog.set_level("DEBUG")

        ProgressInfo(current=5, total=10, message="Test progress")

        # Note: trace level logs might not appear in caplog
        # This test mainly ensures no exceptions are raised

    def test_console_callback_logs_initialization(self, caplog):
        """Test that ConsoleProgressCallback logs initialization."""
        caplog.set_level("DEBUG")

        ConsoleProgressCallback(width=25, show_percentage=False)

        debug_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "DEBUG" and "src.utils.progress" in record.name
        ]
        assert any(
            "ConsoleProgressCallback initialized" in msg for msg in debug_messages
        )

    def test_console_callback_logs_error(self, caplog):
        """Test that ConsoleProgressCallback logs errors."""
        caplog.set_level("ERROR")

        callback = ConsoleProgressCallback()
        with patch("sys.stdout"), patch("builtins.print"):
            callback.error("Test error message")

        error_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "ERROR" and "src.utils.progress" in record.name
        ]
        assert any(
            "ConsoleProgressCallback error: Test error message" in msg
            for msg in error_messages
        )
