"""Tests for platform detection utilities."""

from unittest.mock import patch

import pytest

from src.utils.platform import (
    Architecture,
    OperatingSystem,
    detect_architecture,
    detect_os,
    get_download_url,
    get_dvdauthor_install_instructions,
    get_ffmpeg_download_urls,
    get_platform_info,
    get_ytdlp_download_urls,
    is_platform_supported,
)


class TestOperatingSystemEnum:
    """Test cases for OperatingSystem enum."""

    def test_operating_system_values(self):
        """Test that OS enum has correct values."""
        assert OperatingSystem.LINUX.value == "linux"
        assert OperatingSystem.MACOS.value == "macos"
        assert OperatingSystem.WINDOWS.value == "windows"
        assert OperatingSystem.UNKNOWN.value == "unknown"


class TestArchitectureEnum:
    """Test cases for Architecture enum."""

    def test_architecture_values(self):
        """Test that Architecture enum has correct values."""
        assert Architecture.X64.value == "x64"
        assert Architecture.ARM64.value == "arm64"
        assert Architecture.UNKNOWN.value == "unknown"


class TestDetectOS:
    """Test cases for OS detection."""

    @patch("src.utils.platform.platform.system")
    def test_detect_os_linux(self, mock_system):
        """Test Linux OS detection."""
        mock_system.return_value = "Linux"

        result = detect_os()

        assert result == OperatingSystem.LINUX
        mock_system.assert_called_once()

    @patch("src.utils.platform.platform.system")
    def test_detect_os_macos(self, mock_system):
        """Test macOS detection (Darwin)."""
        mock_system.return_value = "Darwin"

        result = detect_os()

        assert result == OperatingSystem.MACOS
        mock_system.assert_called_once()

    @patch("src.utils.platform.platform.system")
    def test_detect_os_windows(self, mock_system):
        """Test Windows OS detection."""
        mock_system.return_value = "Windows"

        result = detect_os()

        assert result == OperatingSystem.WINDOWS
        mock_system.assert_called_once()

    @patch("src.utils.platform.platform.system")
    def test_detect_os_unknown(self, mock_system):
        """Test unknown OS detection."""
        mock_system.return_value = "FreeBSD"

        result = detect_os()

        assert result == OperatingSystem.UNKNOWN
        mock_system.assert_called_once()

    @patch("src.utils.platform.platform.system")
    def test_detect_os_case_insensitive(self, mock_system):
        """Test that OS detection is case insensitive."""
        mock_system.return_value = "LINUX"

        result = detect_os()

        assert result == OperatingSystem.LINUX


class TestDetectArchitecture:
    """Test cases for architecture detection."""

    @patch("src.utils.platform.platform.machine")
    def test_detect_architecture_x86_64(self, mock_machine):
        """Test x86_64 architecture detection."""
        mock_machine.return_value = "x86_64"

        result = detect_architecture()

        assert result == Architecture.X64
        mock_machine.assert_called_once()

    @patch("src.utils.platform.platform.machine")
    def test_detect_architecture_amd64(self, mock_machine):
        """Test amd64 architecture detection."""
        mock_machine.return_value = "amd64"

        result = detect_architecture()

        assert result == Architecture.X64
        mock_machine.assert_called_once()

    @patch("src.utils.platform.platform.machine")
    def test_detect_architecture_x64(self, mock_machine):
        """Test x64 architecture detection."""
        mock_machine.return_value = "x64"

        result = detect_architecture()

        assert result == Architecture.X64
        mock_machine.assert_called_once()

    @patch("src.utils.platform.platform.machine")
    def test_detect_architecture_arm64(self, mock_machine):
        """Test arm64 architecture detection."""
        mock_machine.return_value = "arm64"

        result = detect_architecture()

        assert result == Architecture.ARM64
        mock_machine.assert_called_once()

    @patch("src.utils.platform.platform.machine")
    def test_detect_architecture_aarch64(self, mock_machine):
        """Test aarch64 architecture detection."""
        mock_machine.return_value = "aarch64"

        result = detect_architecture()

        assert result == Architecture.ARM64
        mock_machine.assert_called_once()

    @patch("src.utils.platform.platform.machine")
    def test_detect_architecture_unknown(self, mock_machine):
        """Test unknown architecture detection."""
        mock_machine.return_value = "sparc"

        result = detect_architecture()

        assert result == Architecture.UNKNOWN
        mock_machine.assert_called_once()

    @patch("src.utils.platform.platform.machine")
    def test_detect_architecture_case_insensitive(self, mock_machine):
        """Test that architecture detection is case insensitive."""
        mock_machine.return_value = "X86_64"

        result = detect_architecture()

        assert result == Architecture.X64


class TestGetPlatformInfo:
    """Test cases for get_platform_info function."""

    @patch("src.utils.platform.detect_architecture")
    @patch("src.utils.platform.detect_os")
    def test_get_platform_info(self, mock_detect_os, mock_detect_arch):
        """Test get_platform_info returns correct tuple."""
        mock_detect_os.return_value = OperatingSystem.LINUX
        mock_detect_arch.return_value = Architecture.X64

        os_type, arch = get_platform_info()

        assert os_type == OperatingSystem.LINUX
        assert arch == Architecture.X64
        mock_detect_os.assert_called_once()
        mock_detect_arch.assert_called_once()


class TestDownloadURLs:
    """Test cases for download URL functions."""

    def test_get_ffmpeg_download_urls(self):
        """Test ffmpeg download URLs are returned."""
        urls = get_ffmpeg_download_urls()

        assert isinstance(urls, dict)
        assert len(urls) > 0

        # Check that we have URLs for expected platforms
        linux_x64_key = (OperatingSystem.LINUX, Architecture.X64)
        macos_x64_key = (OperatingSystem.MACOS, Architecture.X64)
        macos_arm64_key = (OperatingSystem.MACOS, Architecture.ARM64)

        assert linux_x64_key in urls
        assert macos_x64_key in urls
        assert macos_arm64_key in urls

        # Check URLs are strings and not empty
        for url in urls.values():
            assert isinstance(url, str)
            assert len(url) > 0
            assert url.startswith("http")

    def test_get_ytdlp_download_urls(self):
        """Test yt-dlp download URLs are returned."""
        urls = get_ytdlp_download_urls()

        assert isinstance(urls, dict)
        assert len(urls) > 0

        # Check that we have URLs for expected platforms
        linux_x64_key = (OperatingSystem.LINUX, Architecture.X64)
        linux_arm64_key = (OperatingSystem.LINUX, Architecture.ARM64)
        macos_x64_key = (OperatingSystem.MACOS, Architecture.X64)
        macos_arm64_key = (OperatingSystem.MACOS, Architecture.ARM64)

        assert linux_x64_key in urls
        assert linux_arm64_key in urls
        assert macos_x64_key in urls
        assert macos_arm64_key in urls

        # Check URLs are strings and not empty
        for url in urls.values():
            assert isinstance(url, str)
            assert len(url) > 0
            assert url.startswith("http")


class TestGetDownloadURL:
    """Test cases for get_download_url function."""

    @patch("src.utils.platform.get_platform_info")
    def test_get_download_url_ffmpeg_supported_platform(self, mock_platform_info):
        """Test getting ffmpeg download URL for supported platform."""
        mock_platform_info.return_value = (OperatingSystem.LINUX, Architecture.X64)

        url = get_download_url("ffmpeg")

        assert isinstance(url, str)
        assert len(url) > 0
        assert url.startswith("http")
        mock_platform_info.assert_called_once()

    @patch("src.utils.platform.get_platform_info")
    def test_get_download_url_ytdlp_supported_platform(self, mock_platform_info):
        """Test getting yt-dlp download URL for supported platform."""
        mock_platform_info.return_value = (OperatingSystem.MACOS, Architecture.ARM64)

        url = get_download_url("yt-dlp")

        assert isinstance(url, str)
        assert len(url) > 0
        assert url.startswith("http")
        mock_platform_info.assert_called_once()

    @patch("src.utils.platform.get_platform_info")
    def test_get_download_url_unsupported_tool(self, mock_platform_info):
        """Test getting download URL for unsupported tool raises ValueError."""
        mock_platform_info.return_value = (OperatingSystem.LINUX, Architecture.X64)

        with pytest.raises(ValueError, match="Unsupported tool: unsupported-tool"):
            get_download_url("unsupported-tool")

    @patch("src.utils.platform.get_platform_info")
    def test_get_download_url_unsupported_platform(self, mock_platform_info):
        """Test getting download URL for unsupported platform raises RuntimeError."""
        mock_platform_info.return_value = (OperatingSystem.WINDOWS, Architecture.X64)

        with pytest.raises(
            RuntimeError, match="Platform windows/x64 is not supported for ffmpeg"
        ):
            get_download_url("ffmpeg")

    @patch("src.utils.platform.get_platform_info")
    def test_get_download_url_unknown_platform(self, mock_platform_info):
        """Test getting download URL for unknown platform raises RuntimeError."""
        mock_platform_info.return_value = (
            OperatingSystem.UNKNOWN,
            Architecture.UNKNOWN,
        )

        with pytest.raises(
            RuntimeError, match="Platform unknown/unknown is not supported for yt-dlp"
        ):
            get_download_url("yt-dlp")


class TestIsPlatformSupported:
    """Test cases for is_platform_supported function."""

    @patch("src.utils.platform.get_platform_info")
    def test_is_platform_supported_linux_x64(self, mock_platform_info):
        """Test that Linux x64 is supported."""
        mock_platform_info.return_value = (OperatingSystem.LINUX, Architecture.X64)

        result = is_platform_supported()

        assert result is True
        mock_platform_info.assert_called_once()

    @patch("src.utils.platform.get_platform_info")
    def test_is_platform_supported_macos_arm64(self, mock_platform_info):
        """Test that macOS ARM64 is supported."""
        mock_platform_info.return_value = (OperatingSystem.MACOS, Architecture.ARM64)

        result = is_platform_supported()

        assert result is True
        mock_platform_info.assert_called_once()

    @patch("src.utils.platform.get_platform_info")
    def test_is_platform_supported_windows_not_supported(self, mock_platform_info):
        """Test that Windows is not supported."""
        mock_platform_info.return_value = (OperatingSystem.WINDOWS, Architecture.X64)

        result = is_platform_supported()

        assert result is False
        mock_platform_info.assert_called_once()

    @patch("src.utils.platform.get_platform_info")
    def test_is_platform_supported_unknown_not_supported(self, mock_platform_info):
        """Test that unknown platforms are not supported."""
        mock_platform_info.return_value = (
            OperatingSystem.UNKNOWN,
            Architecture.UNKNOWN,
        )

        result = is_platform_supported()

        assert result is False
        mock_platform_info.assert_called_once()


class TestGetDVDAuthorInstallInstructions:
    """Test cases for get_dvdauthor_install_instructions function."""

    @patch("src.utils.platform.detect_os")
    def test_get_dvdauthor_install_instructions_macos(self, mock_detect_os):
        """Test DVD author install instructions for macOS."""
        mock_detect_os.return_value = OperatingSystem.MACOS

        instructions = get_dvdauthor_install_instructions()

        assert "brew install dvdauthor" in instructions
        mock_detect_os.assert_called_once()

    @patch("src.utils.platform.detect_os")
    def test_get_dvdauthor_install_instructions_linux(self, mock_detect_os):
        """Test DVD author install instructions for Linux."""
        mock_detect_os.return_value = OperatingSystem.LINUX

        instructions = get_dvdauthor_install_instructions()

        assert "sudo apt install dvdauthor" in instructions
        assert "sudo yum install dvdauthor" in instructions
        assert "sudo dnf install dvdauthor" in instructions
        mock_detect_os.assert_called_once()

    @patch("src.utils.platform.detect_os")
    def test_get_dvdauthor_install_instructions_windows(self, mock_detect_os):
        """Test DVD author install instructions for Windows."""
        mock_detect_os.return_value = OperatingSystem.WINDOWS

        instructions = get_dvdauthor_install_instructions()

        assert "Windows is not currently supported" in instructions
        mock_detect_os.assert_called_once()

    @patch("src.utils.platform.detect_os")
    def test_get_dvdauthor_install_instructions_unknown(self, mock_detect_os):
        """Test DVD author install instructions for unknown OS."""
        mock_detect_os.return_value = OperatingSystem.UNKNOWN

        instructions = get_dvdauthor_install_instructions()

        assert "Unknown platform - manual installation required" in instructions
        mock_detect_os.assert_called_once()


class TestPlatformLogging:
    """Test cases for platform logging behavior."""

    @patch("src.utils.platform.platform.system")
    def test_detect_os_logs_debug_for_known_os(self, mock_system, caplog):
        """Test that detect_os logs debug message for known OS."""
        caplog.set_level("DEBUG")
        mock_system.return_value = "Linux"

        detect_os()

        debug_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "DEBUG" and "src.utils.platform" in record.name
        ]
        assert any("Operating system detected: Linux" in msg for msg in debug_messages)

    @patch("src.utils.platform.platform.system")
    def test_detect_os_logs_warning_for_unknown_os(self, mock_system, caplog):
        """Test that detect_os logs warning for unknown OS."""
        caplog.set_level("WARNING")
        mock_system.return_value = "FreeBSD"

        detect_os()

        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "WARNING" and "src.utils.platform" in record.name
        ]
        assert any(
            "Unknown operating system detected: freebsd" in msg
            for msg in warning_messages
        )

    @patch("src.utils.platform.platform.machine")
    def test_detect_architecture_logs_debug_for_known_arch(self, mock_machine, caplog):
        """Test that detect_architecture logs debug message for known architecture."""
        caplog.set_level("DEBUG")
        mock_machine.return_value = "x86_64"

        detect_architecture()

        debug_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "DEBUG" and "src.utils.platform" in record.name
        ]
        assert any("Architecture detected: x64" in msg for msg in debug_messages)

    @patch("src.utils.platform.platform.machine")
    def test_detect_architecture_logs_warning_for_unknown_arch(
        self, mock_machine, caplog
    ):
        """Test that detect_architecture logs warning for unknown architecture."""
        caplog.set_level("WARNING")
        mock_machine.return_value = "sparc"

        detect_architecture()

        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "WARNING" and "src.utils.platform" in record.name
        ]
        assert any(
            "Unknown architecture detected: sparc" in msg for msg in warning_messages
        )
