"""Business logic services for DVD Maker."""

from .cache_manager import CacheManager
from .converter import ConversionError, VideoConverter, VideoConverterError
from .downloader import VideoDownloader, YtDlpError
from .dvd_author import (
    DVDAuthor,
    DVDAuthorError,
    DVDAuthoringError,
    DVDCapacityExceededError,
    DVDStructureCreationError,
)
from .tool_manager import (
    ToolDownloadError,
    ToolManager,
    ToolManagerError,
    ToolValidationError,
)

__all__ = [
    # Cache Manager
    "CacheManager",
    # Video Converter
    "VideoConverter",
    "VideoConverterError",
    "ConversionError",
    # Video Downloader
    "VideoDownloader",
    "YtDlpError",
    # DVD Author
    "DVDAuthor",
    "DVDAuthorError",
    "DVDAuthoringError",
    "DVDCapacityExceededError",
    "DVDStructureCreationError",
    # Tool Manager
    "ToolManager",
    "ToolManagerError",
    "ToolDownloadError",
    "ToolValidationError",
]
