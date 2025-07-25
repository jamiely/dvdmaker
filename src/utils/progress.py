"""Progress reporting utilities for tracking operation progress."""

import sys
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class ProgressInfo:
    """Information about progress of an operation."""

    current: int
    total: int
    message: str = ""
    details: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """Initialize details dict if None."""
        if self.details is None:
            self.details = {}

    @property
    def percentage(self) -> float:
        """Get progress as percentage (0-100)."""
        if self.total <= 0:
            return 0.0
        return min(100.0, (self.current / self.total) * 100.0)

    @property
    def is_complete(self) -> bool:
        """Check if operation is complete."""
        return self.current >= self.total

    def __str__(self) -> str:
        """String representation of progress."""
        percentage = self.percentage
        if self.message:
            return f"{percentage:.1f}% - {self.message}"
        return f"{percentage:.1f}% ({self.current}/{self.total})"


class ProgressCallback(ABC):
    """Abstract base class for progress callbacks."""

    @abstractmethod
    def update(self, progress: ProgressInfo) -> None:
        """Update progress.

        Args:
            progress: Current progress information
        """
        pass

    @abstractmethod
    def complete(self, message: str = "") -> None:
        """Signal completion.

        Args:
            message: Optional completion message
        """
        pass

    @abstractmethod
    def error(self, message: str) -> None:
        """Signal error.

        Args:
            message: Error message
        """
        pass


class ConsoleProgressCallback(ProgressCallback):
    """Console-based progress reporter with animated progress bar."""

    def __init__(self, width: int = 50, show_percentage: bool = True) -> None:
        """Initialize console progress callback.

        Args:
            width: Width of progress bar in characters
            show_percentage: Whether to show percentage
        """
        self.width = width
        self.show_percentage = show_percentage
        self._last_line_length = 0
        self._lock = threading.Lock()

    def update(self, progress: ProgressInfo) -> None:
        """Update progress display."""
        with self._lock:
            # Calculate progress bar
            filled_width = int((progress.percentage / 100.0) * self.width)
            bar = "█" * filled_width + "░" * (self.width - filled_width)

            # Build progress line
            parts = [f"[{bar}]"]

            if self.show_percentage:
                parts.append(f"{progress.percentage:5.1f}%")

            parts.append(f"({progress.current}/{progress.total})")

            if progress.message:
                parts.append(f"- {progress.message}")

            line = " ".join(parts)

            # Clear previous line and print new one
            sys.stdout.write("\r" + " " * self._last_line_length + "\r")
            sys.stdout.write(line)
            sys.stdout.flush()

            self._last_line_length = len(line)

    def complete(self, message: str = "") -> None:
        """Signal completion."""
        with self._lock:
            # Clear the progress line
            sys.stdout.write("\r" + " " * self._last_line_length + "\r")

            if message:
                print(f"✓ {message}")
            else:
                print("✓ Complete")

            self._last_line_length = 0

    def error(self, message: str) -> None:
        """Signal error."""
        with self._lock:
            # Clear the progress line
            sys.stdout.write("\r" + " " * self._last_line_length + "\r")
            print(f"✗ Error: {message}")
            self._last_line_length = 0


class SilentProgressCallback(ProgressCallback):
    """Progress callback that does nothing (for testing or silent operation)."""

    def update(self, progress: ProgressInfo) -> None:
        """Do nothing."""
        pass

    def complete(self, message: str = "") -> None:
        """Do nothing."""
        pass

    def error(self, message: str) -> None:
        """Do nothing."""
        pass


class CallbackProgressCallback(ProgressCallback):
    """Progress callback that calls provided functions."""

    def __init__(
        self,
        update_fn: Optional[Callable[[ProgressInfo], None]] = None,
        complete_fn: Optional[Callable[[str], None]] = None,
        error_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialize callback progress reporter.

        Args:
            update_fn: Function to call on progress updates
            complete_fn: Function to call on completion
            error_fn: Function to call on error
        """
        self.update_fn = update_fn
        self.complete_fn = complete_fn
        self.error_fn = error_fn

    def update(self, progress: ProgressInfo) -> None:
        """Call update function if provided."""
        if self.update_fn:
            self.update_fn(progress)

    def complete(self, message: str = "") -> None:
        """Call complete function if provided."""
        if self.complete_fn:
            self.complete_fn(message)

    def error(self, message: str) -> None:
        """Call error function if provided."""
        if self.error_fn:
            self.error_fn(message)


class ProgressTracker:
    """Tracks progress for a single operation with cancellation support."""

    def __init__(
        self,
        total: int,
        callback: Optional[ProgressCallback] = None,
        initial_message: str = "",
    ) -> None:
        """Initialize progress tracker.

        Args:
            total: Total number of units to complete
            callback: Progress callback to notify
            initial_message: Initial progress message
        """
        self.total = total
        self.current = 0
        self.callback = callback or SilentProgressCallback()
        self.message = initial_message
        self.details: Dict[str, Any] = {}
        self._cancelled = False
        self._lock = threading.Lock()

    def update(self, increment: int = 1, message: str = "", **details: Any) -> None:
        """Update progress.

        Args:
            increment: Amount to increment progress by
            message: New progress message
            **details: Additional details to include
        """
        with self._lock:
            if self._cancelled:
                return

            self.current = min(self.total, self.current + increment)

            if message:
                self.message = message

            if details:
                self.details.update(details)

            progress = ProgressInfo(
                current=self.current,
                total=self.total,
                message=self.message,
                details=self.details.copy(),
            )

            self.callback.update(progress)

    def set_progress(self, current: int, message: str = "", **details: Any) -> None:
        """Set absolute progress.

        Args:
            current: Current progress value
            message: New progress message
            **details: Additional details to include
        """
        with self._lock:
            if self._cancelled:
                return

            self.current = min(self.total, max(0, current))

            if message:
                self.message = message

            if details:
                self.details.update(details)

            progress = ProgressInfo(
                current=self.current,
                total=self.total,
                message=self.message,
                details=self.details.copy(),
            )

            self.callback.update(progress)

    def complete(self, message: str = "") -> None:
        """Mark operation as complete.

        Args:
            message: Completion message
        """
        with self._lock:
            if self._cancelled:
                return

            self.current = self.total
            self.callback.complete(message)

    def error(self, message: str) -> None:
        """Signal error in operation.

        Args:
            message: Error message
        """
        with self._lock:
            self.callback.error(message)

    def cancel(self) -> None:
        """Cancel the operation."""
        with self._lock:
            self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """Check if operation is cancelled."""
        with self._lock:
            return self._cancelled

    @property
    def is_complete(self) -> bool:
        """Check if operation is complete."""
        with self._lock:
            return self.current >= self.total


class MultiStepProgressTracker:
    """Tracks progress across multiple steps with weighted completion."""

    def __init__(
        self,
        steps: Dict[str, int],
        callback: Optional[ProgressCallback] = None,
    ) -> None:
        """Initialize multi-step progress tracker.

        Args:
            steps: Dictionary mapping step names to their weights
            callback: Progress callback to notify
        """
        self.steps = steps
        self.total_weight = sum(steps.values())
        self.completed_weight = 0
        self.current_step: Optional[str] = None
        self.step_progress: Dict[str, int] = {step: 0 for step in steps}
        self.callback = callback or SilentProgressCallback()
        self._lock = threading.Lock()

    def start_step(self, step_name: str, message: str = "") -> None:
        """Start a new step.

        Args:
            step_name: Name of the step to start
            message: Step start message
        """
        with self._lock:
            if step_name not in self.steps:
                raise ValueError(f"Unknown step: {step_name}")

            self.current_step = step_name
            self._update_progress(message)

    def update_step(self, progress: int, message: str = "") -> None:
        """Update current step progress.

        Args:
            progress: Progress within current step (0 to step weight)
            message: Progress message
        """
        with self._lock:
            if not self.current_step:
                return

            step_weight = self.steps[self.current_step]
            self.step_progress[self.current_step] = min(step_weight, max(0, progress))
            self._update_progress(message)

    def complete_step(self, message: str = "") -> None:
        """Complete the current step.

        Args:
            message: Step completion message
        """
        with self._lock:
            if not self.current_step:
                return

            step_weight = self.steps[self.current_step]
            self.step_progress[self.current_step] = step_weight
            self._update_progress(message)

    def _update_progress(self, message: str) -> None:
        """Update overall progress."""
        current_total = sum(self.step_progress.values())

        progress = ProgressInfo(
            current=current_total,
            total=self.total_weight,
            message=message,
            details={
                "current_step": self.current_step,
                "step_progress": self.step_progress.copy(),
            },
        )

        self.callback.update(progress)

    def complete(self, message: str = "") -> None:
        """Complete all steps.

        Args:
            message: Overall completion message
        """
        with self._lock:
            # Mark all steps as complete
            for step in self.steps:
                self.step_progress[step] = self.steps[step]

            self.callback.complete(message)

    def error(self, message: str) -> None:
        """Signal error.

        Args:
            message: Error message
        """
        with self._lock:
            self.callback.error(message)
