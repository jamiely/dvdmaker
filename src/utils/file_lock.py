"""File locking utilities for concurrent access protection.

This module provides file locking mechanisms to prevent cache corruption
during concurrent script execution.
"""

import functools
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

from .logging import get_logger

logger = get_logger(__name__)


class FileLock:
    """A simple file-based lock implementation for cross-process synchronization."""

    def __init__(self, lock_path: Path, timeout: float = 30.0) -> None:
        """Initialize the file lock.

        Args:
            lock_path: Path to the lock file
            timeout: Maximum time to wait for lock acquisition in seconds
        """
        self.lock_path = lock_path
        self.timeout = timeout
        self.locked = False
        self.lock_file: Optional[int] = None

        logger.trace(  # type: ignore[attr-defined]
            f"FileLock initialized for {lock_path} with timeout {timeout}s"
        )

    def acquire(self, non_blocking: bool = False) -> bool:
        """Acquire the lock.

        Args:
            non_blocking: If True, don't wait for lock availability

        Returns:
            True if lock was acquired, False otherwise

        Raises:
            TimeoutError: If lock cannot be acquired within timeout (blocking mode)
            RuntimeError: If lock is already held by this instance
        """
        if self.locked:
            raise RuntimeError("Lock is already held by this instance")

        logger.trace(  # type: ignore[attr-defined]
            f"Attempting to acquire lock: {self.lock_path}"
        )

        start_time = time.time()

        while True:
            try:
                # Create lock file exclusively (fails if file exists)
                self.lock_file = os.open(
                    str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                )

                # Write PID and timestamp to lock file
                lock_info = f"{os.getpid()}\n{time.time()}\n"
                os.write(self.lock_file, lock_info.encode())
                os.close(self.lock_file)

                self.locked = True
                logger.debug(f"Successfully acquired lock: {self.lock_path}")
                return True

            except OSError:
                # Lock file already exists
                if non_blocking:
                    logger.trace(  # type: ignore[attr-defined]
                        f"Lock unavailable (non-blocking): {self.lock_path}"
                    )
                    return False

                # Check if we've exceeded timeout
                elapsed = time.time() - start_time
                if elapsed >= self.timeout:
                    logger.warning(
                        f"Failed to acquire lock within {self.timeout}s: "
                        f"{self.lock_path}"
                    )
                    raise TimeoutError(
                        f"Failed to acquire lock within {self.timeout}s: "
                        f"{self.lock_path}"
                    )

                # Check if existing lock is stale
                if self._is_stale_lock():
                    logger.info(f"Removing stale lock: {self.lock_path}")
                    self._remove_lock_file()
                    continue

                # Wait a bit before retrying
                time.sleep(0.1)

    def release(self) -> None:
        """Release the lock.

        Raises:
            RuntimeError: If lock is not held by this instance
        """
        if not self.locked:
            raise RuntimeError("Lock is not held by this instance")

        logger.trace(f"Releasing lock: {self.lock_path}")  # type: ignore[attr-defined]

        self._remove_lock_file()
        self.locked = False
        self.lock_file = None

        logger.debug(f"Successfully released lock: {self.lock_path}")

    def _is_stale_lock(self) -> bool:
        """Check if the existing lock file is stale.

        A lock is considered stale if:
        1. It's older than 5 minutes (process likely crashed)
        2. The PID in the lock file doesn't exist

        Returns:
            True if lock is stale and can be removed
        """
        if not self.lock_path.exists():
            return False

        try:
            with open(self.lock_path, "r") as f:
                lines = f.read().strip().split("\n")
                if len(lines) < 2:
                    logger.warning(f"Invalid lock file format: {self.lock_path}")
                    return True

                pid = int(lines[0])
                timestamp = float(lines[1])

                # Check if lock is older than 5 minutes
                if time.time() - timestamp > 300:  # 5 minutes
                    logger.debug(f"Lock is stale (too old): {self.lock_path}")
                    return True

                # Check if process still exists (Unix/Linux only)
                try:
                    os.kill(pid, 0)  # Signal 0 checks process existence
                    return False  # Process exists, lock is valid
                except OSError:
                    logger.debug(
                        f"Lock process {pid} no longer exists: {self.lock_path}"
                    )
                    return True  # Process doesn't exist, lock is stale

        except (ValueError, OSError) as e:
            logger.warning(f"Error checking lock file {self.lock_path}: {e}")
            return True  # Assume stale if we can't read it

    def _remove_lock_file(self) -> None:
        """Remove the lock file if it exists."""
        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
                logger.trace(  # type: ignore[attr-defined]
                    f"Removed lock file: {self.lock_path}"
                )
        except OSError as e:
            logger.warning(f"Failed to remove lock file {self.lock_path}: {e}")

    def __enter__(self) -> "FileLock":
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        if self.locked:
            self.release()

    def __del__(self) -> None:
        """Cleanup on object destruction."""
        if self.locked:
            try:
                self.release()
            except Exception:
                pass  # Best effort cleanup


def with_file_lock(
    lock_path: Path, timeout: float = 30.0
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for functions that need file locking.

    Args:
        lock_path: Path to the lock file
        timeout: Maximum time to wait for lock acquisition

    Example:
        @with_file_lock(Path("/tmp/my_operation.lock"))
        def critical_operation():
            # This function will be protected by a file lock
            pass
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with FileLock(lock_path, timeout):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def retry_on_concurrent_access(
    max_retries: int = 3,
    retry_delay: float = 1.0,
    backoff_multiplier: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (OSError, TimeoutError),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that retries operations when concurrent access conflicts occur.

    Args:
        max_retries: Maximum number of retry attempts
        retry_delay: Initial delay between retries in seconds
        backoff_multiplier: Multiplier for exponential backoff
        exceptions: Tuple of exceptions to retry on

    Example:
        @retry_on_concurrent_access(max_retries=3, retry_delay=0.5)
        def file_operation():
            # This function will be retried if it fails due to concurrent access
            pass
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            delay = retry_delay

            for attempt in range(max_retries + 1):  # +1 to include the initial attempt
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"Operation {func.__name__} failed after "
                            f"{max_retries} retries: {e}"
                        )
                        break

                    logger.warning(
                        f"Operation {func.__name__} failed (attempt "
                        f"{attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay:.1f}s: {e}"
                    )

                    time.sleep(delay)
                    delay *= backoff_multiplier

            # Re-raise the last exception if all retries failed
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


class RetryableLock:
    """A file lock that automatically retries on failure with exponential backoff."""

    def __init__(
        self,
        lock_path: Path,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ) -> None:
        """Initialize the retryable lock.

        Args:
            lock_path: Path to the lock file
            timeout: Maximum time to wait for lock acquisition
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries
        """
        self.lock_path = lock_path
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._lock: Optional[FileLock] = None

    def __enter__(self) -> "RetryableLock":
        """Context manager entry with retry logic."""
        delay = self.retry_delay
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                self._lock = FileLock(self.lock_path, self.timeout)
                self._lock.acquire()
                return self

            except (OSError, TimeoutError) as e:
                last_exception = e

                if attempt == self.max_retries:
                    logger.error(
                        f"Failed to acquire lock {self.lock_path} after "
                        f"{self.max_retries} retries"
                    )
                    break

                logger.warning(
                    f"Failed to acquire lock {self.lock_path} (attempt {attempt + 1}/"
                    f"{self.max_retries + 1}), retrying in {delay:.1f}s: {e}"
                )

                time.sleep(delay)
                delay *= 2.0  # Exponential backoff

        if last_exception:
            raise last_exception

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        if self._lock and self._lock.locked:
            self._lock.release()
