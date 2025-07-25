"""Platform detection utilities for cross-platform compatibility."""

import platform
from enum import Enum
from typing import Dict, Tuple


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

    if system == "linux":
        return OperatingSystem.LINUX
    elif system == "darwin":
        return OperatingSystem.MACOS
    elif system == "windows":
        return OperatingSystem.WINDOWS
    else:
        return OperatingSystem.UNKNOWN


def detect_architecture() -> Architecture:
    """Detect the current CPU architecture.

    Returns:
        The detected CPU architecture
    """
    machine = platform.machine().lower()

    # Common x64 identifiers
    if machine in ("x86_64", "amd64", "x64"):
        return Architecture.X64

    # Common ARM64 identifiers
    elif machine in ("arm64", "aarch64"):
        return Architecture.ARM64

    else:
        return Architecture.UNKNOWN


def get_platform_info() -> Tuple[OperatingSystem, Architecture]:
    """Get both OS and architecture information.

    Returns:
        Tuple of (operating_system, architecture)
    """
    return detect_os(), detect_architecture()


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
    os_type, arch = get_platform_info()

    if tool == "ffmpeg":
        urls = get_ffmpeg_download_urls()
    elif tool == "yt-dlp":
        urls = get_ytdlp_download_urls()
    else:
        raise ValueError(f"Unsupported tool: {tool}")

    platform_key = (os_type, arch)
    if platform_key not in urls:
        raise RuntimeError(
            f"Platform {os_type.value}/{arch.value} is not supported for {tool}"
        )

    return urls[platform_key]


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
    return platform_key in ffmpeg_urls and platform_key in ytdlp_urls


def get_dvdauthor_install_instructions() -> str:
    """Get installation instructions for dvdauthor on current platform.

    Returns:
        Installation instructions as a string
    """
    os_type = detect_os()

    if os_type == OperatingSystem.MACOS:
        return "Install using: brew install dvdauthor"
    elif os_type == OperatingSystem.LINUX:
        return (
            "Install using:\n"
            "  Ubuntu/Debian: sudo apt install dvdauthor\n"
            "  RHEL/CentOS: sudo yum install dvdauthor\n"
            "  Fedora: sudo dnf install dvdauthor"
        )
    elif os_type == OperatingSystem.WINDOWS:
        return "Windows is not currently supported"
    else:
        return "Unknown platform - manual installation required"
