"""Tests for tool manager service."""

import json
import stat
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest
import requests

from src.config.settings import Settings
from src.services.tool_manager import (
    ToolDownloadError,
    ToolManager,
    ToolManagerError,
    ToolValidationError,
)


class TestToolManager:
    """Test cases for ToolManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.settings = Settings(
            bin_dir=Path("/tmp/test_bin"),
            download_tools=True,
            use_system_tools=False,
            generate_iso=False,  # Disable ISO generation for basic tests
        )
        self.progress_callback = Mock()
        self.tool_manager = ToolManager(self.settings, self.progress_callback)

    def test_init(self):
        """Test ToolManager initialization."""
        assert self.tool_manager.settings == self.settings
        assert self.tool_manager.progress_callback == self.progress_callback
        assert self.tool_manager.bin_dir == self.settings.bin_dir
        assert (
            self.tool_manager.tool_versions_file
            == self.settings.bin_dir / "tool_versions.json"
        )

    @patch("src.services.tool_manager.Path.mkdir")
    def test_init_creates_bin_directory(self, mock_mkdir):
        """Test that initialization creates bin directory."""
        ToolManager(self.settings)
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch("pathlib.Path.exists")
    def test_get_tool_versions_no_file(self, mock_exists):
        """Test getting tool versions when file doesn't exist."""
        mock_exists.return_value = False
        versions = self.tool_manager.get_tool_versions()
        assert versions == {}

    @patch("pathlib.Path.exists")
    def test_get_tool_versions_valid_file(self, mock_exists):
        """Test getting tool versions from valid file."""
        test_versions = {"ffmpeg": "4.4.0", "yt-dlp": "2023.01.06"}
        mock_exists.return_value = True

        with patch("builtins.open", mock_open(read_data=json.dumps(test_versions))):
            versions = self.tool_manager.get_tool_versions()
            assert versions == test_versions

    @patch("pathlib.Path.exists")
    def test_get_tool_versions_invalid_file(self, mock_exists):
        """Test getting tool versions from invalid JSON file."""
        mock_exists.return_value = True

        with patch("builtins.open", mock_open(read_data="invalid json")):
            versions = self.tool_manager.get_tool_versions()
            assert versions == {}

    def test_save_tool_versions(self):
        """Test saving tool versions."""
        test_versions = {"ffmpeg": "4.4.0", "yt-dlp": "2023.01.06"}

        mock_file = mock_open()
        with patch("builtins.open", mock_file):
            self.tool_manager.save_tool_versions(test_versions)

        mock_file.assert_called_once_with(self.tool_manager.tool_versions_file, "w")
        written_data = "".join(
            call.args[0] for call in mock_file().write.call_args_list
        )
        assert json.loads(written_data) == test_versions

    def test_save_tool_versions_io_error(self):
        """Test saving tool versions with IO error."""
        with patch("builtins.open", side_effect=IOError("Permission denied")):
            with pytest.raises(ToolManagerError):
                self.tool_manager.save_tool_versions({})

    def test_get_tool_path(self):
        """Test getting tool paths."""
        assert (
            self.tool_manager.get_tool_path("ffmpeg")
            == self.settings.bin_dir / "ffmpeg"
        )
        assert (
            self.tool_manager.get_tool_path("yt-dlp")
            == self.settings.bin_dir / "yt-dlp"
        )

        with pytest.raises(ValueError):
            self.tool_manager.get_tool_path("unknown_tool")

    def test_is_tool_available_locally_exists(self):
        """Test local tool availability when tool exists."""
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_file", return_value=True):
                with patch("os.access", return_value=True):
                    assert self.tool_manager.is_tool_available_locally("ffmpeg") is True

    def test_is_tool_available_locally_not_exists(self):
        """Test local tool availability when tool doesn't exist."""
        with patch.object(Path, "exists", return_value=False):
            assert self.tool_manager.is_tool_available_locally("ffmpeg") is False

    def test_is_tool_available_locally_not_executable(self):
        """Test local tool availability when tool is not executable."""
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_file", return_value=True):
                with patch("os.access", return_value=False):
                    assert (
                        self.tool_manager.is_tool_available_locally("ffmpeg") is False
                    )

    @patch("shutil.which")
    def test_is_tool_available_system(self, mock_which):
        """Test system tool availability."""
        # Test regular tool
        mock_which.return_value = "/usr/bin/ffmpeg"
        assert self.tool_manager.is_tool_available_system("ffmpeg") is True
        mock_which.assert_called_with("ffmpeg")

        # Test dvdauthor
        mock_which.return_value = "/usr/bin/dvdauthor"
        assert self.tool_manager.is_tool_available_system("dvdauthor") is True
        mock_which.assert_called_with("dvdauthor")

        # Test missing tool
        mock_which.return_value = None
        assert self.tool_manager.is_tool_available_system("ffmpeg") is False

    @patch("shutil.which")
    def test_is_tool_available_system_mkisofs(self, mock_which):
        """Test system tool availability for mkisofs."""
        # Test mkisofs available
        mock_which.side_effect = lambda tool: (
            "/usr/bin/mkisofs" if tool == "mkisofs" else None
        )
        assert self.tool_manager.is_tool_available_system("mkisofs") is True

        # Test genisoimage available (fallback)
        mock_which.side_effect = lambda tool: (
            "/usr/bin/genisoimage" if tool == "genisoimage" else None
        )
        assert self.tool_manager.is_tool_available_system("mkisofs") is True

        # Test neither available - reset side_effect
        mock_which.side_effect = None
        mock_which.return_value = None
        assert self.tool_manager.is_tool_available_system("mkisofs") is False

    @patch("subprocess.run")
    def test_validate_tool_functionality_ffmpeg(self, mock_run):
        """Test tool functionality validation for ffmpeg."""
        mock_run.return_value = Mock(
            returncode=0, stdout="ffmpeg version 4.4.0", stderr=""
        )

        assert self.tool_manager.validate_tool_functionality("ffmpeg") is True
        mock_run.assert_called_once_with(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10
        )

    @patch("subprocess.run")
    def test_validate_tool_functionality_ytdlp(self, mock_run):
        """Test tool functionality validation for yt-dlp."""
        mock_run.return_value = Mock(returncode=0, stdout="2023.01.06", stderr="")

        assert self.tool_manager.validate_tool_functionality("yt-dlp") is True
        mock_run.assert_called_once_with(
            ["yt-dlp", "--version"], capture_output=True, text=True, timeout=30
        )

    @patch("subprocess.run")
    def test_validate_tool_functionality_dvdauthor(self, mock_run):
        """Test tool functionality validation for dvdauthor."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="DVDAuthor 0.7.2",
            stderr="DVDAuthor::dvdauthor, version 0.7.2.",
        )

        assert self.tool_manager.validate_tool_functionality("dvdauthor") is True
        mock_run.assert_called_once_with(
            ["dvdauthor", "--help"], capture_output=True, text=True, timeout=10
        )

    @patch("subprocess.run")
    def test_validate_tool_functionality_mkisofs(self, mock_run):
        """Test tool functionality validation for mkisofs."""
        mock_run.return_value = Mock(
            returncode=0, stdout="mkisofs 1.1.11 (Linux)", stderr=""
        )

        assert self.tool_manager.validate_tool_functionality("mkisofs") is True
        mock_run.assert_called_once_with(
            ["mkisofs", "--version"], capture_output=True, text=True, timeout=10
        )

    @patch("subprocess.run")
    def test_validate_tool_functionality_mkisofs_fallback(self, mock_run):
        """Test tool functionality validation for mkisofs with genisoimage fallback."""
        # First call (mkisofs) fails, second call (genisoimage) succeeds
        mock_run.side_effect = [
            Mock(returncode=1, stderr="mkisofs not found"),
            Mock(returncode=0, stdout="genisoimage version info"),
        ]

        assert self.tool_manager.validate_tool_functionality("mkisofs") is True
        assert mock_run.call_count == 2
        # Check that both commands were tried
        mock_run.assert_any_call(
            ["mkisofs", "--version"], capture_output=True, text=True, timeout=10
        )
        mock_run.assert_any_call(
            ["genisoimage", "--version"], capture_output=True, text=True, timeout=10
        )

    @patch("subprocess.run")
    def test_validate_tool_functionality_with_path(self, mock_run):
        """Test tool functionality validation with specific path."""
        mock_run.return_value = Mock(
            returncode=0, stdout="ffmpeg version 4.4.0", stderr=""
        )
        tool_path = Path("/custom/path/ffmpeg")

        assert (
            self.tool_manager.validate_tool_functionality("ffmpeg", tool_path) is True
        )
        mock_run.assert_called_once_with(
            ["/custom/path/ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )

    @patch("subprocess.run")
    def test_validate_tool_functionality_failure(self, mock_run):
        """Test tool functionality validation failure."""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Error")

        assert self.tool_manager.validate_tool_functionality("ffmpeg") is False

    @patch("subprocess.run")
    def test_validate_tool_functionality_exception(self, mock_run):
        """Test tool functionality validation with exception."""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)

        assert self.tool_manager.validate_tool_functionality("ffmpeg") is False

    def test_validate_tool_functionality_unknown_tool(self):
        """Test tool functionality validation for unknown tool."""
        assert self.tool_manager.validate_tool_functionality("unknown") is False

    @patch("subprocess.run")
    def test_get_tool_version_ffmpeg(self, mock_run):
        """Test getting ffmpeg version."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="ffmpeg version 4.4.0-0ubuntu1 Copyright (c) 2000-2021",
            stderr="",
        )

        version = self.tool_manager.get_tool_version("ffmpeg")
        assert version == "4.4.0-0ubuntu1"

    @patch("subprocess.run")
    def test_get_tool_version_ytdlp(self, mock_run):
        """Test getting yt-dlp version."""
        mock_run.return_value = Mock(returncode=0, stdout="2023.01.06\n", stderr="")

        version = self.tool_manager.get_tool_version("yt-dlp")
        assert version == "2023.01.06"

    @patch("subprocess.run")
    def test_get_tool_version_dvdauthor(self, mock_run):
        """Test getting dvdauthor version."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="DVDAuthor 0.7.2, Build 20180905",
            stderr="DVDAuthor::dvdauthor, version 0.7.2.",
        )

        version = self.tool_manager.get_tool_version("dvdauthor")
        assert version == "0.7.2"

    @patch("subprocess.run")
    def test_get_tool_version_mkisofs(self, mock_run):
        """Test getting mkisofs version."""
        mock_run.return_value = Mock(
            returncode=0, stdout="mkisofs 1.1.11 (Linux)", stderr=""
        )

        version = self.tool_manager.get_tool_version("mkisofs")
        assert version == "1.1.11"

    @patch("subprocess.run")
    def test_get_tool_version_mkisofs_fallback(self, mock_run):
        """Test getting mkisofs version with genisoimage fallback."""
        # First call (mkisofs) fails, second call (genisoimage) succeeds
        mock_run.side_effect = [
            Mock(returncode=1, stdout="", stderr="mkisofs not found"),
            Mock(returncode=0, stdout="genisoimage 1.1.11 (Linux)", stderr=""),
        ]

        version = self.tool_manager.get_tool_version("mkisofs")
        assert version == "1.1.11"
        assert mock_run.call_count == 2

    @patch("subprocess.run")
    def test_get_tool_version_failure(self, mock_run):
        """Test getting tool version failure."""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="")

        version = self.tool_manager.get_tool_version("ffmpeg")
        assert version is None

    @patch("subprocess.run")
    def test_get_tool_version_exception(self, mock_run):
        """Test getting tool version with exception."""
        mock_run.side_effect = FileNotFoundError()

        version = self.tool_manager.get_tool_version("ffmpeg")
        assert version is None

    def test_get_tool_version_unknown_tool(self):
        """Test getting version for unknown tool."""
        version = self.tool_manager.get_tool_version("unknown")
        assert version is None

    @patch("requests.get")
    def test_download_file_success(self, mock_get):
        """Test successful file download."""
        mock_response = Mock()
        mock_response.headers = {"content-length": "1000"}
        mock_response.iter_content.return_value = [b"data1", b"data2"]
        mock_get.return_value = mock_response

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "test_file"

            self.tool_manager.download_file("http://example.com/file", destination)

            assert destination.exists()
            with open(destination, "rb") as f:
                assert f.read() == b"data1data2"

    @patch("requests.get")
    def test_download_file_http_error(self, mock_get):
        """Test file download with HTTP error."""
        mock_get.side_effect = requests.RequestException("Network error")

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "test_file"

            with pytest.raises(ToolDownloadError):
                self.tool_manager.download_file("http://example.com/file", destination)

    @patch("requests.get")
    def test_download_file_with_progress(self, mock_get):
        """Test file download with progress callback."""
        mock_response = Mock()
        mock_response.headers = {"content-length": "100"}
        mock_response.iter_content.return_value = [b"x" * 50, b"x" * 50]
        mock_get.return_value = mock_response

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "test_file"

            self.tool_manager.download_file("http://example.com/file", destination)

            # Check that progress callback was called
            assert self.progress_callback.call_count == 2

    def test_extract_archive_zip(self):
        """Test ZIP archive extraction."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a test ZIP file
            import zipfile

            zip_path = temp_path / "test.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("test_file.txt", "test content")

            extract_dir = temp_path / "extracted"
            extract_dir.mkdir()

            self.tool_manager.extract_archive(zip_path, extract_dir)

            assert (extract_dir / "test_file.txt").exists()
            with open(extract_dir / "test_file.txt") as f:
                assert f.read() == "test content"

    def test_extract_archive_unsupported(self):
        """Test extraction of unsupported archive format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            unsupported_file = temp_path / "test.rar"
            unsupported_file.touch()

            with pytest.raises(ToolDownloadError):
                self.tool_manager.extract_archive(unsupported_file, temp_path)

    def test_make_executable(self):
        """Test making file executable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test_file"
            test_file.touch()

            # Remove execute permissions first
            test_file.chmod(0o644)

            self.tool_manager.make_executable(test_file)

            # Check that file is now executable
            file_stat = test_file.stat()
            assert file_stat.st_mode & stat.S_IXUSR
            assert file_stat.st_mode & stat.S_IXGRP
            assert file_stat.st_mode & stat.S_IXOTH

    @patch("src.services.tool_manager.is_platform_supported")
    def test_download_tool_unsupported_platform(self, mock_platform_supported):
        """Test tool download on unsupported platform."""
        mock_platform_supported.return_value = False

        with pytest.raises(ToolDownloadError):
            self.tool_manager.download_tool("ffmpeg")

    @patch("src.services.tool_manager.get_download_url")
    @patch("src.services.tool_manager.is_platform_supported")
    def test_download_tool_invalid_url(self, mock_platform_supported, mock_get_url):
        """Test tool download with invalid URL."""
        mock_platform_supported.return_value = True
        mock_get_url.side_effect = ValueError("Invalid tool")

        with pytest.raises(ToolDownloadError):
            self.tool_manager.download_tool("invalid_tool")

    @patch("src.services.tool_manager.is_platform_supported")
    @patch("src.services.tool_manager.get_download_url")
    @patch.object(ToolManager, "download_file")
    @patch.object(ToolManager, "_validate_and_get_version")
    @patch.object(ToolManager, "save_tool_versions")
    @patch("shutil.copy2")
    @patch.object(ToolManager, "make_executable")
    def test_download_tool_direct_binary(
        self,
        mock_make_exec,
        mock_copy,
        mock_save_versions,
        mock_validate_and_version,
        mock_download,
        mock_get_url,
        mock_platform_supported,
    ):
        """Test downloading tool as direct binary."""
        mock_platform_supported.return_value = True
        mock_get_url.return_value = "http://example.com/ffmpeg"
        mock_validate_and_version.return_value = (True, "4.4.0")

        result = self.tool_manager.download_tool("ffmpeg")

        assert result is True
        mock_download.assert_called_once()
        mock_copy.assert_called_once()
        mock_make_exec.assert_called_once()
        mock_validate_and_version.assert_called_once()
        mock_save_versions.assert_called_once()

    def test_find_binary_in_extracted_found(self):
        """Test finding binary in extracted files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            extract_dir = Path(temp_dir)

            # Create nested directory structure with binary
            bin_dir = extract_dir / "some" / "nested" / "path"
            bin_dir.mkdir(parents=True)
            binary_path = bin_dir / "ffmpeg"
            binary_path.touch()
            binary_path.chmod(0o755)

            found_path = self.tool_manager._find_binary_in_extracted(
                extract_dir, "ffmpeg"
            )

            assert found_path == binary_path

    def test_find_binary_in_extracted_not_found(self):
        """Test finding binary in extracted files when not found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            extract_dir = Path(temp_dir)

            found_path = self.tool_manager._find_binary_in_extracted(
                extract_dir, "ffmpeg"
            )

            assert found_path is None

    @patch.object(ToolManager, "is_tool_available_locally")
    @patch.object(ToolManager, "is_tool_available_system")
    @patch.object(ToolManager, "_validate_and_get_version")
    @patch("shutil.which")
    def test_check_tools(
        self,
        mock_which,
        mock_validate_and_version,
        mock_system_available,
        mock_local_available,
    ):
        """Test checking all tools status."""
        # Mock return values
        mock_local_available.return_value = True
        mock_system_available.return_value = True
        mock_validate_and_version.return_value = (True, "1.0.0")
        mock_which.return_value = "/usr/bin/tool"

        status = self.tool_manager.check_tools()

        assert len(status) == 3
        assert "ffmpeg" in status
        assert "yt-dlp" in status
        assert "dvdauthor" in status

        for tool_status in status.values():
            assert "available_locally" in tool_status
            assert "available_system" in tool_status
            assert "functional" in tool_status
            assert "version" in tool_status
            assert "path" in tool_status

    @patch.object(ToolManager, "is_tool_available_locally")
    @patch.object(ToolManager, "is_tool_available_system")
    @patch.object(ToolManager, "_validate_and_get_version")
    @patch("shutil.which")
    def test_check_tools_with_iso_generation(
        self,
        mock_which,
        mock_validate_and_version,
        mock_system_available,
        mock_local_available,
    ):
        """Test checking tools when ISO generation is enabled."""
        # Enable ISO generation
        self.tool_manager.settings.generate_iso = True

        # Mock return values
        mock_local_available.return_value = True
        mock_system_available.return_value = True
        mock_validate_and_version.return_value = (True, "1.0.0")
        mock_which.return_value = "/usr/bin/tool"

        status = self.tool_manager.check_tools()

        # Should include mkisofs when ISO generation is enabled
        assert len(status) == 4
        assert "ffmpeg" in status
        assert "yt-dlp" in status
        assert "dvdauthor" in status
        assert "mkisofs" in status

    @patch.object(ToolManager, "check_tools")
    @patch.object(ToolManager, "download_tool")
    @patch("src.services.tool_manager.get_dvdauthor_install_instructions")
    def test_ensure_tools_available_all_present(
        self, mock_instructions, mock_download, mock_check
    ):
        """Test ensuring tools when all are available."""
        mock_check.return_value = {
            "ffmpeg": {"functional": True},
            "yt-dlp": {"functional": True},
            "dvdauthor": {"functional": True},
        }

        success, missing = self.tool_manager.ensure_tools_available()

        assert success is True
        assert missing == []
        mock_download.assert_not_called()

    @patch.object(ToolManager, "check_tools")
    @patch.object(ToolManager, "download_tool")
    @patch("src.services.tool_manager.get_dvdauthor_install_instructions")
    def test_ensure_tools_available_download_needed(
        self, mock_instructions, mock_download, mock_check
    ):
        """Test ensuring tools when download is needed."""
        # First call returns non-functional, second call (after download)
        # returns functional
        mock_check.side_effect = [
            {
                "ffmpeg": {"functional": False},
                "yt-dlp": {"functional": True},
                "dvdauthor": {"functional": True},
            },
            {
                "ffmpeg": {"functional": True},
                "yt-dlp": {"functional": True},
                "dvdauthor": {"functional": True},
            },
        ]
        mock_download.return_value = True

        success, missing = self.tool_manager.ensure_tools_available()

        assert success is True
        assert missing == []
        mock_download.assert_called_once_with("ffmpeg")

    @patch.object(ToolManager, "check_tools")
    @patch.object(ToolManager, "download_tool")
    @patch("src.services.tool_manager.get_dvdauthor_install_instructions")
    def test_ensure_tools_available_dvdauthor_missing(
        self, mock_instructions, mock_download, mock_check
    ):
        """Test ensuring tools when dvdauthor is missing."""
        mock_check.return_value = {
            "ffmpeg": {"functional": True},
            "yt-dlp": {"functional": True},
            "dvdauthor": {"functional": False},
        }
        mock_instructions.return_value = "Install with: brew install dvdauthor"

        success, missing = self.tool_manager.ensure_tools_available()

        assert success is False
        assert len(missing) == 1
        assert "dvdauthor" in missing[0]
        assert "brew install dvdauthor" in missing[0]

    @patch.object(ToolManager, "check_tools")
    @patch.object(ToolManager, "download_tool")
    @patch("src.services.tool_manager.get_dvdauthor_install_instructions")
    def test_ensure_tools_available_mkisofs_missing(
        self, mock_instructions, mock_download, mock_check
    ):
        """Test ensuring tools when mkisofs is missing and ISO generation is enabled."""
        # Enable ISO generation
        self.tool_manager.settings.generate_iso = True

        mock_check.return_value = {
            "ffmpeg": {"functional": True},
            "yt-dlp": {"functional": True},
            "dvdauthor": {"functional": True},
            "mkisofs": {"functional": False},
        }

        success, missing = self.tool_manager.ensure_tools_available()

        assert success is False
        assert len(missing) == 1
        assert "mkisofs" in missing[0]
        assert "Install with:" in missing[0]

    @patch.object(ToolManager, "check_tools")
    def test_get_tool_command_available(self, mock_check):
        """Test getting tool command when tool is available."""
        mock_check.return_value = {
            "ffmpeg": {"functional": True, "path": "/usr/bin/ffmpeg"}
        }

        command = self.tool_manager.get_tool_command("ffmpeg")
        assert command == ["/usr/bin/ffmpeg"]

    @patch.object(ToolManager, "check_tools")
    def test_get_tool_command_not_available(self, mock_check):
        """Test getting tool command when tool is not available."""
        mock_check.return_value = {"ffmpeg": {"functional": False, "path": None}}

        with pytest.raises(ToolValidationError):
            self.tool_manager.get_tool_command("ffmpeg")

    @patch.object(ToolManager, "check_tools")
    def test_get_tool_command_no_path(self, mock_check):
        """Test getting tool command when no path is available."""
        mock_check.return_value = {"ffmpeg": {"functional": True, "path": None}}

        command = self.tool_manager.get_tool_command("ffmpeg")
        assert command == ["ffmpeg"]


class TestToolManagerSettings:
    """Test ToolManager behavior with different settings."""

    def test_use_system_tools(self):
        """Test behavior when use_system_tools is enabled."""
        settings = Settings(bin_dir=Path("/tmp/test_bin"), use_system_tools=True)
        tool_manager = ToolManager(settings)

        with patch.object(tool_manager, "is_tool_available_system", return_value=True):
            with patch.object(
                tool_manager, "_validate_and_get_version", return_value=(True, "1.0.0")
            ):
                status = tool_manager.check_tools()

                # Should not check local availability for downloadable tools
                for tool_name in ["ffmpeg", "yt-dlp"]:
                    assert status[tool_name]["available_locally"] is False

    def test_download_tools_disabled(self):
        """Test behavior when download_tools is disabled."""
        settings = Settings(
            bin_dir=Path("/tmp/test_bin"), download_tools=False, use_system_tools=True
        )
        tool_manager = ToolManager(settings)

        with patch.object(tool_manager, "check_tools") as mock_check:
            mock_check.return_value = {
                "ffmpeg": {
                    "functional": False,
                    "available_locally": False,
                    "available_system": False,
                    "path": None,
                },
                "yt-dlp": {"functional": True},
                "dvdauthor": {"functional": True},
            }

            success, missing = tool_manager.ensure_tools_available()

            assert success is False
            assert len(missing) == 1
            assert "auto-download disabled" in missing[0]


class TestToolManagerErrorHandling:
    """Test ToolManager error handling and edge cases."""

    def setup_method(self):
        """Set up test fixtures."""
        self.settings = Settings(
            bin_dir=Path("/tmp/test_bin"),
            download_tools=True,
            use_system_tools=False,
        )
        self.tool_manager = ToolManager(self.settings)

    @patch("src.services.tool_manager.ToolManager._run_logged_subprocess")
    def test_validate_and_get_version_subprocess_error_with_output(self, mock_run):
        """Test _validate_and_get_version with subprocess error with stdout/stderr."""
        # Mock subprocess.CalledProcessError with stdout and stderr
        error = subprocess.CalledProcessError(1, ["ffmpeg", "--version"])
        error.stdout = "Some stdout output"
        error.stderr = "Some stderr output"
        mock_run.side_effect = error

        is_functional, version = self.tool_manager._validate_and_get_version("ffmpeg")

        assert is_functional is False
        assert version is None

    @patch("src.services.tool_manager.ToolManager._run_logged_subprocess")
    def test_validate_and_get_version_mkisofs_fallback_success(self, mock_run):
        """Test mkisofs fallback to genisoimage when mkisofs fails."""
        # First call (mkisofs) fails, second call (genisoimage) succeeds
        mock_run.side_effect = [
            Mock(returncode=1),  # mkisofs fails
            Mock(returncode=0, stdout="genisoimage 1.1.11"),  # genisoimage succeeds
        ]

        is_functional, version = self.tool_manager._validate_and_get_version("mkisofs")

        assert is_functional is True
        assert version == "1.1.11"  # Version number is extracted, not the full string
        assert mock_run.call_count == 2

    @patch("src.services.tool_manager.ToolManager._run_logged_subprocess")
    def test_validate_and_get_version_mkisofs_both_fail(self, mock_run):
        """Test mkisofs when both mkisofs and genisoimage fail."""
        # Both calls fail
        mock_run.side_effect = [
            Mock(returncode=1),  # mkisofs fails
            Mock(returncode=1),  # genisoimage also fails
        ]

        is_functional, version = self.tool_manager._validate_and_get_version("mkisofs")

        assert is_functional is False
        assert version is None
        assert mock_run.call_count == 2

    @patch("src.services.tool_manager.ToolManager._run_logged_subprocess")
    def test_validate_and_get_version_mkisofs_fallback_exception(self, mock_run):
        """Test mkisofs when fallback to genisoimage raises exception."""
        # First call fails, second call raises exception
        mock_run.side_effect = [
            Mock(returncode=1),  # mkisofs fails
            Exception("Network error"),  # genisoimage raises exception
        ]

        is_functional, version = self.tool_manager._validate_and_get_version("mkisofs")

        assert is_functional is False
        assert version is None
        assert mock_run.call_count == 2

    def test_save_tool_versions_io_error(self):
        """Test save_tool_versions handles IO errors by raising ToolManagerError."""
        versions = {"ffmpeg": "4.4.0", "yt-dlp": "2023.01.06"}

        # Mock open to raise IOError
        with patch("builtins.open", side_effect=IOError("Permission denied")):
            # Should raise ToolManagerError and log the error
            with pytest.raises(ToolManagerError, match="Failed to save tool versions"):
                self.tool_manager.save_tool_versions(versions)

    def test_get_tool_versions_io_error(self):
        """Test get_tool_versions handles IO errors gracefully."""
        # Mock pathlib.Path.exists to return True, but open fails
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", side_effect=IOError("Permission denied")),
        ):

            versions = self.tool_manager.get_tool_versions()
            assert versions == {}

    def test_get_tool_versions_json_decode_error(self):
        """Test get_tool_versions handles JSON decode errors gracefully."""
        # Mock file existence and invalid JSON content
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data="invalid json content")),
        ):

            versions = self.tool_manager.get_tool_versions()
            assert versions == {}

    def test_unknown_tool_validation(self):
        """Test _validate_and_get_version with unknown tool name."""
        is_functional, version = self.tool_manager._validate_and_get_version(
            "unknown_tool"
        )

        assert is_functional is False
        assert version is None

    @patch("src.services.tool_manager.ToolManager._run_logged_subprocess")
    def test_dvdauthor_version_extraction_system_fallback(self, mock_run):
        """Test dvdauthor version extraction when standard parsing fails."""
        # Mock successful run but with non-standard version output
        mock_run.return_value = Mock(
            returncode=0,
            stdout="dvdauthor (other info)\nSome other line",
            stderr="",  # Ensure stderr is a string, not a mock
        )

        is_functional, version = self.tool_manager._validate_and_get_version(
            "dvdauthor"
        )

        assert is_functional is True
        assert version is None  # Returns None when can't parse version

    def test_run_logged_subprocess_calledprocesserror_with_output(self):
        """Test _run_logged_subprocess handling CalledProcessError with output."""
        error = subprocess.CalledProcessError(1, ["test", "command"])
        error.stdout = "stdout content"
        error.stderr = "stderr content"

        # Patch the actual subprocess.run call
        with patch("subprocess.run", side_effect=error):
            try:
                self.tool_manager._run_logged_subprocess(["test", "command"])
                assert False, "Should have raised CalledProcessError"
            except subprocess.CalledProcessError:
                pass  # Expected

    def test_get_tool_versions_nonexistent_file(self):
        """Test get_tool_versions when file doesn't exist."""
        # Ensure file doesn't exist
        if self.tool_manager.tool_versions_file.exists():
            self.tool_manager.tool_versions_file.unlink()

        versions = self.tool_manager.get_tool_versions()
        assert versions == {}


class TestToolManagerExceptions:
    """Test ToolManager exception handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.settings = Settings(bin_dir=Path("/tmp/test_bin"))
        self.tool_manager = ToolManager(self.settings)

    def test_tool_manager_error(self):
        """Test ToolManagerError exception."""
        error = ToolManagerError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_tool_download_error(self):
        """Test ToolDownloadError exception."""
        error = ToolDownloadError("Download failed")
        assert str(error) == "Download failed"
        assert isinstance(error, ToolManagerError)

    def test_tool_validation_error(self):
        """Test ToolValidationError exception."""
        error = ToolValidationError("Validation failed")
        assert str(error) == "Validation failed"
        assert isinstance(error, ToolManagerError)


class TestYtDlpUpdateFunctionality:
    """Test cases for yt-dlp update functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.settings = Settings(
            bin_dir=Path("/tmp/test_bin"),
            download_tools=True,
            use_system_tools=False,
            generate_iso=False,
        )
        self.progress_callback = Mock()
        self.tool_manager = ToolManager(self.settings, self.progress_callback)

    @patch("src.services.tool_manager.requests.get")
    def test_get_latest_ytdlp_version_success(self, mock_get):
        """Test successfully getting latest yt-dlp version."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = {"tag_name": "2024.01.04"}
        mock_get.return_value = mock_response

        version = self.tool_manager.get_latest_ytdlp_version()

        assert version == "2024.01.04"
        mock_get.assert_called_once_with(
            "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest", timeout=10
        )

    @patch("src.services.tool_manager.requests.get")
    def test_get_latest_ytdlp_version_request_failure(self, mock_get):
        """Test handling of request failure when getting latest version."""
        import requests

        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        version = self.tool_manager.get_latest_ytdlp_version()

        assert version is None

    @patch("src.services.tool_manager.requests.get")
    def test_get_latest_ytdlp_version_invalid_response(self, mock_get):
        """Test handling of invalid API response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"name": "invalid"}  # Missing tag_name
        mock_get.return_value = mock_response

        version = self.tool_manager.get_latest_ytdlp_version()

        assert version is None

    def test_compare_versions_newer_available(self):
        """Test version comparison when newer version is available."""
        result = self.tool_manager.compare_versions("2023.12.30", "2024.01.04")
        assert result is True

    def test_compare_versions_current_is_latest(self):
        """Test version comparison when current version is latest."""
        result = self.tool_manager.compare_versions("2024.01.04", "2024.01.04")
        assert result is False

    def test_compare_versions_current_is_newer(self):
        """Test version comparison when current version is newer than available."""
        result = self.tool_manager.compare_versions("2024.01.05", "2024.01.04")
        assert result is False

    def test_compare_versions_with_v_prefix(self):
        """Test version comparison with 'v' prefix."""
        result = self.tool_manager.compare_versions("v2023.12.30", "v2024.01.04")
        assert result is True

    def test_compare_versions_different_formats(self):
        """Test version comparison with different version formats."""
        result = self.tool_manager.compare_versions("2023.12.30", "2024.1.4")
        assert result is True

    def test_compare_versions_with_suffixes(self):
        """Test version comparison with version suffixes."""
        result = self.tool_manager.compare_versions("2024.01.04-dev", "2024.01.04")
        assert result is False

    def test_compare_versions_invalid_versions(self):
        """Test version comparison with invalid version strings."""
        result = self.tool_manager.compare_versions("invalid", "2024.01.04")
        assert result is False

        result = self.tool_manager.compare_versions("2024.01.04", "invalid")
        assert result is False

    @patch.object(ToolManager, "get_tool_version")
    @patch.object(ToolManager, "get_latest_ytdlp_version")
    @patch.object(ToolManager, "download_tool")
    def test_check_and_update_ytdlp_no_current_version(
        self, mock_download, mock_latest, mock_current
    ):
        """Test yt-dlp update when no current version exists."""
        mock_current.return_value = None
        mock_download.return_value = True

        result = self.tool_manager.check_and_update_ytdlp()

        assert result is True
        mock_download.assert_called_once_with("yt-dlp")

    @patch.object(ToolManager, "get_tool_version")
    @patch.object(ToolManager, "get_latest_ytdlp_version")
    def test_check_and_update_ytdlp_no_latest_version(self, mock_latest, mock_current):
        """Test yt-dlp update when latest version cannot be determined."""
        mock_current.return_value = "2024.01.04"
        mock_latest.return_value = None

        result = self.tool_manager.check_and_update_ytdlp()

        assert result is True  # Should not fail if can't check for updates

    @patch.object(ToolManager, "get_tool_version")
    @patch.object(ToolManager, "get_latest_ytdlp_version")
    @patch.object(ToolManager, "compare_versions")
    def test_check_and_update_ytdlp_already_current(
        self, mock_compare, mock_latest, mock_current
    ):
        """Test yt-dlp update when current version is already latest."""
        mock_current.return_value = "2024.01.04"
        mock_latest.return_value = "2024.01.04"
        mock_compare.return_value = False  # No update needed

        result = self.tool_manager.check_and_update_ytdlp()

        assert result is True

    @patch.object(ToolManager, "is_tool_available_locally")
    @patch.object(ToolManager, "get_tool_version")
    @patch.object(ToolManager, "get_latest_ytdlp_version")
    @patch.object(ToolManager, "compare_versions")
    @patch.object(ToolManager, "get_tool_path")
    @patch.object(ToolManager, "download_tool")
    @patch("src.services.tool_manager.shutil.copy2")
    def test_check_and_update_ytdlp_successful_update(
        self,
        mock_copy,
        mock_download,
        mock_path,
        mock_compare,
        mock_latest,
        mock_current,
        mock_available,
        tmp_path,
    ):
        """Test successful yt-dlp update."""
        # Setup mocks
        current_path = tmp_path / "yt-dlp"
        current_path.write_text("fake binary")

        mock_available.return_value = True  # Tool is available locally
        mock_current.side_effect = [
            "2023.12.30",
            "2024.01.04",
        ]  # Before and after update
        mock_latest.return_value = "2024.01.04"
        mock_compare.return_value = True  # Update needed
        mock_path.return_value = current_path
        mock_download.return_value = True

        result = self.tool_manager.check_and_update_ytdlp()

        assert result is True
        mock_download.assert_called_once_with("yt-dlp")
        mock_copy.assert_called_once()  # Backup created

    @patch.object(ToolManager, "get_tool_version")
    @patch.object(ToolManager, "get_latest_ytdlp_version")
    @patch.object(ToolManager, "compare_versions")
    @patch.object(ToolManager, "get_tool_path")
    @patch.object(ToolManager, "download_tool")
    @patch("src.services.tool_manager.shutil.copy2")
    def test_check_and_update_ytdlp_download_failure(
        self,
        mock_copy,
        mock_download,
        mock_path,
        mock_compare,
        mock_latest,
        mock_current,
        tmp_path,
    ):
        """Test yt-dlp update when download fails."""
        # Setup mocks
        current_path = tmp_path / "yt-dlp"
        current_path.write_text("fake binary")
        backup_path = current_path.with_suffix(".backup-2023.12.30")

        mock_current.return_value = "2023.12.30"
        mock_latest.return_value = "2024.01.04"
        mock_compare.return_value = True  # Update needed
        mock_path.return_value = current_path
        mock_download.return_value = False  # Download fails

        # Create backup file to test restoration
        backup_path.write_text("backup binary")

        result = self.tool_manager.check_and_update_ytdlp()

        assert result is False
        mock_download.assert_called_once_with("yt-dlp")

    @patch.object(ToolManager, "get_tool_version")
    def test_check_and_update_ytdlp_exception_handling(self, mock_current):
        """Test yt-dlp update exception handling."""
        mock_current.side_effect = Exception("Unexpected error")

        result = self.tool_manager.check_and_update_ytdlp()

        assert result is False


class TestToolManagerLogging:
    """Test cases for ToolManager logging behavior."""

    def setup_method(self):
        """Set up test fixtures."""
        self.settings = Settings(
            bin_dir=Path("/tmp/test_bin"),
            download_tools=True,
            use_system_tools=False,
            generate_iso=False,
        )
        self.progress_callback = Mock()
        self.tool_manager = ToolManager(self.settings, self.progress_callback)

    @patch("src.services.tool_manager.requests.get")
    def test_download_file_logging(self, mock_get, caplog):
        """Test download_file logs info messages."""
        # Set caplog to capture INFO level logs
        caplog.set_level("INFO")

        # Mock successful download
        mock_response = MagicMock()
        mock_response.headers.get.return_value = "1024"
        mock_response.iter_content.return_value = [b"test content"]
        mock_get.return_value = mock_response

        destination = Path("/tmp/test_file")

        with patch("builtins.open", mock_open()):
            self.tool_manager.download_file("http://example.com/file", destination)

        # Check for info log messages
        info_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "INFO" and "src.services.tool_manager" in record.name
        ]
        assert len(info_messages) >= 2
        assert any(
            "Downloading http://example.com/file to /tmp/test_file" in msg
            for msg in info_messages
        )
        assert any("Successfully downloaded test_file" in msg for msg in info_messages)

    @patch("src.services.tool_manager.get_download_url")
    @patch("src.services.tool_manager.is_platform_supported")
    def test_download_tool_logging(self, mock_platform, mock_url, caplog):
        """Test download_tool logs info messages."""
        caplog.set_level("INFO")

        mock_platform.return_value = True
        mock_url.return_value = "http://example.com/tool"

        with patch.object(self.tool_manager, "download_file"):
            with patch.object(self.tool_manager, "_find_binary_in_extracted"):
                with patch("src.services.tool_manager.shutil.copy2"):
                    with patch.object(self.tool_manager, "make_executable"):
                        with patch.object(
                            self.tool_manager, "_validate_and_get_version"
                        ) as mock_validate:
                            with patch.object(
                                self.tool_manager, "get_tool_versions"
                            ) as mock_get_versions:
                                with patch.object(
                                    self.tool_manager, "save_tool_versions"
                                ):
                                    # Setup mocks
                                    mock_validate.return_value = (True, "1.0.0")
                                    mock_get_versions.return_value = {}

                                    # Test with valid tool name
                                    result = self.tool_manager.download_tool("ffmpeg")

        assert result is True

        # Check for info log messages
        info_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "INFO" and "src.services.tool_manager" in record.name
        ]
        assert any("Starting download of ffmpeg" in msg for msg in info_messages)
        assert any(
            "Successfully downloaded and installed ffmpeg" in msg
            for msg in info_messages
        )

    def test_ensure_tools_available_download_logging(self, caplog):
        """Test ensure_tools_available logs info messages during download."""
        caplog.set_level("INFO")

        with patch.object(self.tool_manager, "check_tools") as mock_check:
            with patch.object(self.tool_manager, "download_tool") as mock_download:
                with patch.object(self.tool_manager, "_invalidate_cache"):
                    # Setup mock to show tool not functional initially
                    mock_check.side_effect = [
                        {
                            "ffmpeg": {
                                "available_locally": False,
                                "available_system": False,
                                "functional": False,
                                "version": None,
                                "path": None,
                            }
                        },
                        {
                            "ffmpeg": {
                                "available_locally": True,
                                "available_system": False,
                                "functional": True,
                                "version": "4.4.0",
                                "path": "/tmp/test_bin/ffmpeg",
                            }
                        },
                    ]
                    mock_download.return_value = True

                    success, missing = self.tool_manager.ensure_tools_available()

        assert success is True
        assert missing == []

        # Check for info log messages
        info_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "INFO" and "src.services.tool_manager" in record.name
        ]
        assert any("Attempting to download ffmpeg" in msg for msg in info_messages)
        assert any("Successfully downloaded ffmpeg" in msg for msg in info_messages)

    @patch.object(ToolManager, "is_tool_available_locally")
    @patch.object(ToolManager, "get_tool_path")
    @patch.object(ToolManager, "get_tool_version")
    @patch.object(ToolManager, "get_latest_ytdlp_version")
    def test_check_and_update_ytdlp_logging_info_messages(
        self, mock_latest, mock_current, mock_path, mock_available, caplog
    ):
        """Test check_and_update_ytdlp logs all info messages."""
        caplog.set_level("INFO")

        # Test scenario: yt-dlp not found locally
        mock_available.return_value = False
        mock_current.return_value = None

        with patch.object(self.tool_manager, "download_tool") as mock_download:
            mock_download.return_value = True

            result = self.tool_manager.check_and_update_ytdlp()

        assert result is True

        # Check for info log messages
        info_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "INFO" and "src.services.tool_manager" in record.name
        ]
        assert any("Checking for yt-dlp updates..." in msg for msg in info_messages)
        assert any(
            "yt-dlp not found locally, will download latest version" in msg
            for msg in info_messages
        )

    @patch.object(ToolManager, "is_tool_available_locally")
    @patch.object(ToolManager, "get_tool_path")
    @patch.object(ToolManager, "get_tool_version")
    @patch.object(ToolManager, "get_latest_ytdlp_version")
    @patch.object(ToolManager, "compare_versions")
    def test_check_and_update_ytdlp_up_to_date_logging(
        self, mock_compare, mock_latest, mock_current, mock_path, mock_available, caplog
    ):
        """Test check_and_update_ytdlp logs when already up to date."""
        caplog.set_level("INFO")

        mock_available.return_value = True
        mock_path.return_value = Path("/tmp/yt-dlp")
        mock_current.return_value = "2024.01.04"
        mock_latest.return_value = "2024.01.04"
        mock_compare.return_value = False  # No update needed

        result = self.tool_manager.check_and_update_ytdlp()

        assert result is True

        # Check for info log messages
        info_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "INFO" and "src.services.tool_manager" in record.name
        ]
        assert any("Checking for yt-dlp updates..." in msg for msg in info_messages)
        assert any(
            "yt-dlp is already up to date (current: 2024.01.04)" in msg
            for msg in info_messages
        )

    @patch.object(ToolManager, "is_tool_available_locally")
    @patch.object(ToolManager, "get_tool_path")
    @patch.object(ToolManager, "get_tool_version")
    @patch.object(ToolManager, "get_latest_ytdlp_version")
    @patch.object(ToolManager, "compare_versions")
    @patch.object(ToolManager, "download_tool")
    def test_check_and_update_ytdlp_successful_update_logging(
        self,
        mock_download,
        mock_compare,
        mock_latest,
        mock_current,
        mock_path,
        mock_available,
        caplog,
        tmp_path,
    ):
        """Test check_and_update_ytdlp logs successful update messages."""
        caplog.set_level("INFO")

        # Setup mocks for successful update scenario
        current_path = tmp_path / "yt-dlp"
        current_path.write_text("old version")

        mock_available.return_value = True
        mock_path.return_value = current_path
        mock_current.side_effect = [
            "2023.12.30",
            "2024.01.04",
        ]  # Before and after update
        mock_latest.return_value = "2024.01.04"
        mock_compare.return_value = True  # Update needed
        mock_download.return_value = True

        result = self.tool_manager.check_and_update_ytdlp()

        assert result is True

        # Check for info log messages
        info_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "INFO" and "src.services.tool_manager" in record.name
        ]
        assert any("Checking for yt-dlp updates..." in msg for msg in info_messages)
        assert any(
            "yt-dlp update available: 2023.12.30 -> 2024.01.04" in msg
            for msg in info_messages
        )
        assert any(
            "Successfully updated yt-dlp from 2023.12.30 to 2024.01.04" in msg
            for msg in info_messages
        )
        assert any(
            "yt-dlp update verified (new version: 2024.01.04)" in msg
            for msg in info_messages
        )

    @patch.object(ToolManager, "is_tool_available_locally")
    @patch.object(ToolManager, "get_tool_path")
    @patch.object(ToolManager, "get_tool_version")
    @patch.object(ToolManager, "get_latest_ytdlp_version")
    @patch.object(ToolManager, "compare_versions")
    @patch.object(ToolManager, "download_tool")
    def test_check_and_update_ytdlp_failed_update_with_restore_logging(
        self,
        mock_download,
        mock_compare,
        mock_latest,
        mock_current,
        mock_path,
        mock_available,
        caplog,
        tmp_path,
    ):
        """Test check_and_update_ytdlp logs restore message when update fails."""
        caplog.set_level("INFO")

        # Setup files for backup/restore scenario
        current_path = tmp_path / "yt-dlp"
        backup_path = current_path.with_suffix(".backup-2023.12.30")
        current_path.write_text("old version")
        backup_path.write_text("backup version")

        mock_available.return_value = True
        mock_path.return_value = current_path
        mock_current.return_value = "2023.12.30"
        mock_latest.return_value = "2024.01.04"
        mock_compare.return_value = True  # Update needed
        mock_download.return_value = False  # Download fails

        result = self.tool_manager.check_and_update_ytdlp()

        assert result is False

        # Check for info log messages
        info_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "INFO" and "src.services.tool_manager" in record.name
        ]
        assert any("Checking for yt-dlp updates..." in msg for msg in info_messages)
        assert any(
            "yt-dlp update available: 2023.12.30 -> 2024.01.04" in msg
            for msg in info_messages
        )
        assert any(
            "Restored previous yt-dlp version after failed update" in msg
            for msg in info_messages
        )
