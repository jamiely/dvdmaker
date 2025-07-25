"""Logging utilities for structured JSON logging with TRACE level support."""

import json
import logging
import logging.handlers
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Generator, Optional, TypeVar, Union

# Add TRACE level
TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")


def trace(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Log a message with severity 'TRACE'."""
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, message, args, **kwargs)


# Add trace method to Logger class
logging.Logger.trace = trace  # type: ignore[attr-defined]

# Thread-local storage for correlation IDs and context
_context = threading.local()

F = TypeVar("F", bound=Callable[..., Any])


class ContextFilter(logging.Filter):
    """Filter to add context information to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add context information to the log record."""
        # Add correlation ID
        record.correlation_id = getattr(_context, "correlation_id", None)

        # Add operation context
        record.operation = getattr(_context, "operation", None)
        record.component = getattr(_context, "component", None)

        # Add custom context
        context = getattr(_context, "context", {})
        for key, value in context.items():
            setattr(record, key, value)

        return True


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def __init__(self, include_traceback: bool = True) -> None:
        """Initialize JSON formatter.

        Args:
            include_traceback: Whether to include traceback in error logs
        """
        super().__init__()
        self.include_traceback = include_traceback

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Base log entry
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add correlation ID if present
        if hasattr(record, "correlation_id") and record.correlation_id:
            log_entry["correlation_id"] = record.correlation_id

        # Add operation context if present
        if hasattr(record, "operation") and record.operation:
            log_entry["operation"] = record.operation

        if hasattr(record, "component") and record.component:
            log_entry["component"] = record.component

        # Add any custom context
        context = {}
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "correlation_id",
                "operation",
                "component",
            } and not key.startswith("_"):
                context[key] = value

        if context:
            log_entry["context"] = context

        # Add exception information if present
        if record.exc_info and self.include_traceback:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(log_entry, default=str, ensure_ascii=False)


class SensitiveDataFilter(logging.Filter):
    """Filter to remove sensitive information from logs."""

    SENSITIVE_PATTERNS = {
        "password",
        "token",
        "key",
        "secret",
        "auth",
        "credential",
        "api_key",
        "access_token",
        "refresh_token",
        "session_id",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter sensitive data from log records."""
        # Check message
        message = record.getMessage().lower()
        for pattern in self.SENSITIVE_PATTERNS:
            if pattern in message:
                record.msg = "[SENSITIVE DATA REDACTED]"
                record.args = ()
                break

        # Check context
        if hasattr(record, "context") and isinstance(record.context, dict):
            filtered_context = {}
            for key, value in record.context.items():
                if any(pattern in key.lower() for pattern in self.SENSITIVE_PATTERNS):
                    filtered_context[key] = "[REDACTED]"
                else:
                    filtered_context[key] = value
            record.context = filtered_context

        return True


def setup_logging(
    log_dir: Path,
    log_level: str = "INFO",
    log_file: str = "dvdmaker.log",
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    console_output: bool = True,
    json_format: bool = True,
) -> None:
    """Set up logging configuration.

    Args:
        log_dir: Directory for log files
        log_level: Logging level
        log_file: Name of the main log file
        max_file_size: Maximum size of log files before rotation
        backup_count: Number of backup files to keep
        console_output: Whether to output logs to console
        json_format: Whether to use JSON formatting
    """
    # Create log directory
    log_dir.mkdir(parents=True, exist_ok=True)

    # Convert log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(TRACE_LEVEL)  # Capture all levels

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Context filter
    context_filter = ContextFilter()
    sensitive_filter = SensitiveDataFilter()

    # File handler with rotation
    log_file_path = log_dir / log_file
    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path,
        maxBytes=max_file_size,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)

    if json_format:
        file_formatter: logging.Formatter = JSONFormatter(include_traceback=True)
    else:
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(context_filter)
    file_handler.addFilter(sensitive_filter)
    root_logger.addHandler(file_handler)

    # Console handler (if enabled)
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(numeric_level)

        # Simple format for console
        console_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
        )

        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(sensitive_filter)
        root_logger.addHandler(console_handler)

    # Set up debug directory for TRACE logs
    if numeric_level <= TRACE_LEVEL:
        debug_dir = log_dir / "debug"
        debug_dir.mkdir(exist_ok=True)

        debug_handler = logging.handlers.RotatingFileHandler(
            debug_dir / "trace.log",
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding="utf-8",
        )
        debug_handler.setLevel(TRACE_LEVEL)
        debug_handler.setFormatter(file_formatter)
        debug_handler.addFilter(context_filter)
        debug_handler.addFilter(sensitive_filter)
        root_logger.addHandler(debug_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """Set correlation ID for current thread.

    Args:
        correlation_id: Correlation ID to set (generates UUID if None)

    Returns:
        The correlation ID that was set
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    _context.correlation_id = correlation_id
    return correlation_id


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID."""
    return getattr(_context, "correlation_id", None)


def set_operation_context(operation: str, component: Optional[str] = None) -> None:
    """Set operation context for current thread.

    Args:
        operation: Operation name
        component: Component name
    """
    _context.operation = operation
    _context.component = component


def set_context(**kwargs: Any) -> None:
    """Set custom context for current thread.

    Args:
        **kwargs: Context key-value pairs
    """
    if not hasattr(_context, "context"):
        _context.context = {}

    _context.context.update(kwargs)


def clear_context() -> None:
    """Clear all context for current thread."""
    for attr in ["correlation_id", "operation", "component", "context"]:
        if hasattr(_context, attr):
            delattr(_context, attr)


@contextmanager
def operation_context(
    operation: str,
    component: Optional[str] = None,
    correlation_id: Optional[str] = None,
    **kwargs: Any,
) -> Generator[str, None, None]:
    """Context manager for operation logging.

    Args:
        operation: Operation name
        component: Component name
        correlation_id: Correlation ID (generates UUID if None)
        **kwargs: Additional context

    Yields:
        The correlation ID
    """
    # Save current context
    old_correlation_id = getattr(_context, "correlation_id", None)
    old_operation = getattr(_context, "operation", None)
    old_component = getattr(_context, "component", None)
    old_context = getattr(_context, "context", {}).copy()

    try:
        # Set new context
        actual_correlation_id = set_correlation_id(correlation_id)
        set_operation_context(operation, component)
        set_context(**kwargs)

        yield actual_correlation_id

    finally:
        # Restore old context
        if old_correlation_id:
            _context.correlation_id = old_correlation_id
        elif hasattr(_context, "correlation_id"):
            delattr(_context, "correlation_id")

        if old_operation:
            _context.operation = old_operation
        elif hasattr(_context, "operation"):
            delattr(_context, "operation")

        if old_component:
            _context.component = old_component
        elif hasattr(_context, "component"):
            delattr(_context, "component")

        _context.context = old_context


def timed_operation(
    operation_name: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    log_level: int = logging.INFO,
    include_args: bool = False,
) -> Callable[[F], F]:
    """Decorator to log operation timing.

    Args:
        operation_name: Name of operation (uses function name if None)
        logger: Logger to use (creates one if None)
        log_level: Log level for timing messages
        include_args: Whether to include function arguments in logs

    Returns:
        Decorated function
    """

    def decorator(func: F) -> F:
        nonlocal logger, operation_name

        if logger is None:
            logger = get_logger(func.__module__)

        if operation_name is None:
            operation_name = func.__name__

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()

            # Log start
            log_kwargs = {}
            if include_args:
                log_kwargs.update(
                    {
                        "args": str(args)[:200],  # Truncate long args
                        "kwargs_str": str({k: str(v)[:100] for k, v in kwargs.items()}),
                    }
                )

            with operation_context(operation_name, **log_kwargs):
                logger.log(log_level, f"Starting {operation_name}")

                try:
                    result = func(*args, **kwargs)

                    # Log success
                    duration = time.time() - start_time
                    logger.log(
                        log_level,
                        f"Completed {operation_name}",
                        extra={"duration_seconds": duration},
                    )

                    return result

                except Exception as e:
                    # Log error
                    duration = time.time() - start_time
                    logger.error(
                        f"Failed {operation_name}: {e}",
                        extra={"duration_seconds": duration},
                        exc_info=True,
                    )
                    raise

        return wrapper  # type: ignore[return-value]

    return decorator


class LoggingMixin:
    """Mixin class to add logging capabilities to service classes."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize logging mixin."""
        super().__init__(*args, **kwargs)
        self.logger = get_logger(self.__class__.__module__)

    def log_operation_start(
        self, operation: str, correlation_id: Optional[str] = None, **context: Any
    ) -> str:
        """Log the start of an operation.

        Args:
            operation: Operation name
            correlation_id: Correlation ID (generates UUID if None)
            **context: Additional context

        Returns:
            The correlation ID
        """
        actual_correlation_id = set_correlation_id(correlation_id)
        set_operation_context(operation, self.__class__.__name__)
        set_context(**context)

        self.logger.info(f"Starting {operation}")
        return actual_correlation_id

    def log_operation_complete(
        self, operation: str, duration: Optional[float] = None, **context: Any
    ) -> None:
        """Log the completion of an operation.

        Args:
            operation: Operation name
            duration: Operation duration in seconds
            **context: Additional context
        """
        extra = {}
        if duration is not None:
            extra["duration_seconds"] = duration

        if context:
            set_context(**context)

        self.logger.info(f"Completed {operation}", extra=extra)

    def log_operation_error(
        self,
        operation: str,
        error: Exception,
        duration: Optional[float] = None,
        **context: Any,
    ) -> None:
        """Log an operation error.

        Args:
            operation: Operation name
            error: The exception that occurred
            duration: Operation duration in seconds
            **context: Additional context
        """
        extra = {}
        if duration is not None:
            extra["duration_seconds"] = duration

        if context:
            set_context(**context)

        self.logger.error(f"Failed {operation}: {error}", extra=extra, exc_info=True)


def log_external_command(
    command: Union[str, list[str]],
    logger: Optional[logging.Logger] = None,
    log_output: bool = True,
) -> Callable[[F], F]:
    """Decorator to log external command execution.

    Args:
        command: Command being executed
        logger: Logger to use
        log_output: Whether to log command output

    Returns:
        Decorated function
    """

    def decorator(func: F) -> F:
        nonlocal logger

        if logger is None:
            logger = get_logger(func.__module__)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cmd_str = " ".join(command) if isinstance(command, list) else command

            logger.info(f"Executing command: {cmd_str}")

            try:
                result = func(*args, **kwargs)

                if log_output and hasattr(result, "stdout"):
                    logger.debug(f"Command output: {result.stdout}")

                logger.info(f"Command completed successfully: {cmd_str}")
                return result

            except Exception as e:
                logger.error(f"Command failed: {cmd_str} - {e}", exc_info=True)
                raise

        return wrapper  # type: ignore[return-value]

    return decorator
