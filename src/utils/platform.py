"""Platform detection utilities for cross-platform compatibility."""

import platform
from enum import Enum
from typing import Dict, Tuple

from .logging import get_logger

logger = get_logger(__name__)


class OperatingSystem(Enum):
    """Supported operating systems."""

    LINUX = "linux"
    MACOS = "macos"
    WINDOWS = "windows"
    UNKNOWN = "unknown"


class Architecture(Enum):
    """Supported CPU architectures."""

    X64 = "x64"
    ARM64 = "arm64"
    UNKNOWN = "unknown"


def detect_os() -> OperatingSystem:
    """Detect the current operating system.

    Returns:
        The detected operating system
    """
    system = platform.system().lower()
    logger.trace(f"Detected system: {system}")  # type: ignore[attr-defined]

    if system == "linux":
        logger.debug("Operating system detected: Linux")
        return OperatingSystem.LINUX
    elif system == "darwin":
        logger.debug("Operating system detected: macOS")
        return OperatingSystem.MACOS
    elif system == "windows":
        logger.debug("Operating system detected: Windows")
        return OperatingSystem.WINDOWS
    else:
        logger.warning(f"Unknown operating system detected: {system}")
        return OperatingSystem.UNKNOWN


def detect_architecture() -> Architecture:
    """Detect the current CPU architecture.

    Returns:
        The detected CPU architecture
    """
    machine = platform.machine().lower()
    logger.trace(f"Detected machine: {machine}")  # type: ignore[attr-defined]

    # Common x64 identifiers
    if machine in ("x86_64", "amd64", "x64"):
        logger.debug("Architecture detected: x64")
        return Architecture.X64

    # Common ARM64 identifiers
    elif machine in ("arm64", "aarch64"):
        logger.debug("Architecture detected: ARM64")
        return Architecture.ARM64

    else:
        logger.warning(f"Unknown architecture detected: {machine}")
        return Architecture.UNKNOWN


def get_platform_info() -> Tuple[OperatingSystem, Architecture]:
    """Get both OS and architecture information.

    Returns:
        Tuple of (operating_system, architecture)
    """
    os_type = detect_os()
    arch = detect_architecture()
    logger.debug(f"Platform info: {os_type.value}/{arch.value}")
    return os_type, arch


def get_ffmpeg_download_urls() -> Dict[Tuple[OperatingSystem, Architecture], str]:
    """Get platform-specific download URLs for ffmpeg.

    Returns:
        Dictionary mapping (OS, Architecture) to download URLs
    """
    return {
        (
            OperatingSystem.LINUX,
            Architecture.X64,
        ): (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
            "latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
        ),
        (
            OperatingSystem.MACOS,
            Architecture.X64,
        ): "https://evermeet.cx/ffmpeg/ffmpeg-6.0.zip",
        (
            OperatingSystem.MACOS,
            Architecture.ARM64,
        ): "https://evermeet.cx/ffmpeg/ffmpeg-6.0.zip",
    }


def get_ytdlp_download_urls() -> Dict[Tuple[OperatingSystem, Architecture], str]:
    """Get platform-specific download URLs for yt-dlp.

    Returns:
        Dictionary mapping (OS, Architecture) to download URLs
    """
    return {
        (
            OperatingSystem.LINUX,
            Architecture.X64,
        ): "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp",
        (
            OperatingSystem.LINUX,
            Architecture.ARM64,
        ): (
            "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
            "yt-dlp_linux_aarch64"
        ),
        (
            OperatingSystem.MACOS,
            Architecture.X64,
        ): "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos",
        (
            OperatingSystem.MACOS,
            Architecture.ARM64,
        ): "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos",
    }


def get_download_url(tool: str) -> str:
    """Get download URL for a specific tool on the current platform.

    Args:
        tool: The tool name ('ffmpeg' or 'yt-dlp')

    Returns:
        Download URL for the tool on current platform

    Raises:
        ValueError: If tool is not supported
        RuntimeError: If platform is not supported
    """
    logger.trace(f"Getting download URL for tool: {tool}")  # type: ignore[attr-defined]
    os_type, arch = get_platform_info()

    if tool == "ffmpeg":
        urls = get_ffmpeg_download_urls()
    elif tool == "yt-dlp":
        urls = get_ytdlp_download_urls()
    else:
        logger.error(f"Unsupported tool requested: {tool}")
        raise ValueError(f"Unsupported tool: {tool}")

    platform_key = (os_type, arch)
    if platform_key not in urls:
        logger.error(
            f"Platform {os_type.value}/{arch.value} is not supported for {tool}"
        )
        raise RuntimeError(
            f"Platform {os_type.value}/{arch.value} is not supported for {tool}"
        )

    url = urls[platform_key]
    logger.debug(f"Download URL for {tool} on {os_type.value}/{arch.value}: {url}")
    return url


def is_platform_supported() -> bool:
    """Check if the current platform is supported.

    Returns:
        True if platform is supported, False otherwise
    """
    os_type, arch = get_platform_info()

    # Check if we have download URLs for both tools
    ffmpeg_urls = get_ffmpeg_download_urls()
    ytdlp_urls = get_ytdlp_download_urls()

    platform_key = (os_type, arch)
    supported = platform_key in ffmpeg_urls and platform_key in ytdlp_urls

    if supported:
        logger.debug(f"Platform {os_type.value}/{arch.value} is supported")
    else:
        logger.warning(f"Platform {os_type.value}/{arch.value} is not supported")

    return supported


def get_dvdauthor_install_instructions() -> str:
    """Get installation instructions for dvdauthor on current platform.

    Returns:
        Installation instructions as a string
    """
    os_type = detect_os()
    logger.trace(  # type: ignore[attr-defined]
        f"Getting dvdauthor install instructions for {os_type.value}"
    )

    if os_type == OperatingSystem.MACOS:
        instructions = "Install using: brew install dvdauthor"
        logger.debug("Providing macOS dvdauthor installation instructions")
        return instructions
    elif os_type == OperatingSystem.LINUX:
        instructions = (
            "Install using:\n"
            "  Ubuntu/Debian: sudo apt install dvdauthor\n"
            "  RHEL/CentOS: sudo yum install dvdauthor\n"
            "  Fedora: sudo dnf install dvdauthor"
        )
        logger.debug("Providing Linux dvdauthor installation instructions")
        return instructions
    elif os_type == OperatingSystem.WINDOWS:
        instructions = "Windows is not currently supported"
        logger.warning(
            "Windows platform requested dvdauthor instructions (not supported)"
        )
        return instructions
    else:
        instructions = "Unknown platform - manual installation required"
        logger.warning(
            f"Unknown platform {os_type.value} requested dvdauthor instructions"
        )
        return instructions
