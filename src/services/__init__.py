"""Business logic services for DVD Maker."""

from .base import BaseService
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
from .spumux_service import (
    ButtonConfig,
    ButtonGraphicError,
    ButtonOverlay,
    SpumuxError,
    SpumuxNotAvailableError,
    SpumuxService,
    SubtitleFiles,
)
from .tool_manager import (
    ToolDownloadError,
    ToolManager,
    ToolManagerError,
    ToolValidationError,
)

__all__ = [
    # Base Service
    "BaseService",
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
    # Spumux Service
    "SpumuxService",
    "SpumuxError",
    "SpumuxNotAvailableError",
    "ButtonGraphicError",
    "ButtonConfig",
    "ButtonOverlay",
    "SubtitleFiles",
    # Tool Manager
    "ToolManager",
    "ToolManagerError",
    "ToolDownloadError",
    "ToolValidationError",
]
