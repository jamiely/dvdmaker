"""Utility functions for DVD Maker."""

from .filename import (
    FilenameMapper,
    generate_unique_filename,
    is_valid_filename,
    normalize_filename,
    normalize_to_ascii,
    sanitize_filename,
)
from .logging import (
    LoggingMixin,
    get_logger,
    operation_context,
    setup_logging,
    timed_operation,
)
from .platform import (
    detect_architecture,
    detect_os,
    get_download_url,
    get_dvdauthor_install_instructions,
    get_platform_info,
    is_platform_supported,
)
from .progress import (
    CallbackProgressCallback,
    ConsoleProgressCallback,
    MultiStepProgressTracker,
    ProgressCallback,
    ProgressInfo,
    ProgressTracker,
    SilentProgressCallback,
)

__all__ = [
    # Filename utilities
    "normalize_to_ascii",
    "sanitize_filename",
    "normalize_filename",
    "generate_unique_filename",
    "is_valid_filename",
    "FilenameMapper",
    # Logging utilities
    "get_logger",
    "operation_context",
    "timed_operation",
    "setup_logging",
    "LoggingMixin",
    # Platform utilities
    "detect_architecture",
    "detect_os",
    "get_platform_info",
    "get_download_url",
    "is_platform_supported",
    "get_dvdauthor_install_instructions",
    # Progress utilities
    "ProgressInfo",
    "ProgressCallback",
    "ConsoleProgressCallback",
    "SilentProgressCallback",
    "CallbackProgressCallback",
    "ProgressTracker",
    "MultiStepProgressTracker",
]
