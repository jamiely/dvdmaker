"""Tool management service for DVD Maker.

This module handles downloading, validating, and managing external tools
required for DVD creation including ffmpeg, yt-dlp, and dvdauthor.
"""

import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from ..config.settings import Settings
from ..exceptions import DVDMakerError
from ..utils.platform import (
    get_download_url,
    get_dvdauthor_install_instructions,
    is_platform_supported,
)
from .base import BaseService

# Simple progress callback type
ProgressCallback = Callable[[str, float], None]


class ToolManagerError(DVDMakerError):
    """Base exception for tool manager errors."""

    pass


class ToolDownloadError(ToolManagerError):
    """Exception raised when tool download fails."""

    pass


class ToolValidationError(ToolManagerError):
    """Exception raised when tool validation fails."""

    pass


class ToolManager(BaseService):
    """Manages external tools required for DVD creation.

    This class handles:
    - Tool version checking and validation
    - Automatic downloading of ffmpeg and yt-dlp
    - System tool detection and validation
    - Installation instruction provision for dvdauthor
    """

    def __init__(
        self, settings: Settings, progress_callback: Optional[ProgressCallback] = None
    ):
        """Initialize the tool manager.

        Args:
            settings: Application settings
            progress_callback: Optional callback for progress reporting
        """
        super().__init__(settings)
        self.progress_callback = progress_callback
        self.bin_dir = settings.bin_dir
        self.tool_versions_file = self.bin_dir / "tool_versions.json"

        # Cache for tool status to avoid repeated expensive validation calls
        self._tools_status_cache: Optional[Dict[str, Dict[str, Any]]] = None

        # Ensure bin directory exists
        self.bin_dir.mkdir(parents=True, exist_ok=True)

    def _run_logged_subprocess(
        self,
        cmd: List[str],
        timeout: Optional[int] = None,
        capture_output: bool = True,
        text: bool = True,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        """Run subprocess with comprehensive logging.

        Args:
            cmd: Command to execute
            timeout: Optional timeout in seconds
            capture_output: Whether to capture output
            text: Whether to return text output
            **kwargs: Additional arguments for subprocess.run

        Returns:
            CompletedProcess result
        """
        cmd_str = " ".join(str(arg) for arg in cmd)
        self.logger.debug(f"Executing command: {cmd_str}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=text,
                timeout=timeout,
                **kwargs,
            )

            # Log command completion and output
            self.logger.debug(
                f"Command completed with return code {result.returncode}: {cmd_str}"
            )

            if capture_output and result.stdout:
                self.logger.debug(f"Command stdout: {result.stdout.strip()}")

            if capture_output and result.stderr:
                # Special case: dvdauthor --help returns exit code 1 but is successful
                is_dvdauthor_help = (
                    "dvdauthor" in cmd_str
                    and "--help" in cmd_str
                    and result.returncode == 1
                )
                if result.returncode == 0 or is_dvdauthor_help:
                    self.logger.debug(f"Command stderr: {result.stderr.strip()}")
                else:
                    self.logger.warning(f"Command stderr: {result.stderr.strip()}")

            return result

        except subprocess.TimeoutExpired:
            self.logger.error(f"Command timed out after {timeout}s: {cmd_str}")
            raise
        except subprocess.CalledProcessError as e:
            self.logger.error(
                f"Command failed with return code {e.returncode}: {cmd_str}"
            )
            if e.stdout:
                self.logger.debug(f"Failed command stdout: {e.stdout.strip()}")
            if e.stderr:
                self.logger.debug(f"Failed command stderr: {e.stderr.strip()}")
            raise
        except Exception as e:
            self.logger.error(f"Command execution failed: {cmd_str} - {e}")
            raise

    def get_tool_versions(self) -> Dict[str, str]:
        """Load tool versions from tool_versions.json.

        Returns:
            Dictionary mapping tool names to versions
        """
        if not self.tool_versions_file.exists():
            self.logger.debug("No tool_versions.json found, returning empty dict")
            return {}

        try:
            with open(self.tool_versions_file, "r") as f:
                versions: Dict[str, str] = json.load(f)
            self.logger.debug(f"Loaded tool versions: {versions}")
            return versions
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Failed to load tool versions: {e}")
            return {}

    def save_tool_versions(self, versions: Dict[str, str]) -> None:
        """Save tool versions to tool_versions.json.

        Args:
            versions: Dictionary mapping tool names to versions
        """
        try:
            with open(self.tool_versions_file, "w") as f:
                json.dump(versions, f, indent=2)
            self.logger.debug(f"Saved tool versions: {versions}")
        except IOError as e:
            self.logger.error(f"Failed to save tool versions: {e}")
            raise ToolManagerError(f"Failed to save tool versions: {e}")

    def get_tool_path(self, tool_name: str) -> Path:
        """Get the expected path for a tool binary.

        Args:
            tool_name: Name of the tool

        Returns:
            Path to the tool binary
        """
        if tool_name == "ffmpeg":
            return self.bin_dir / "ffmpeg"
        elif tool_name == "yt-dlp":
            return self.bin_dir / "yt-dlp"
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def is_tool_available_locally(self, tool_name: str) -> bool:
        """Check if a tool is available in the local bin directory.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool is available locally
        """
        tool_path = self.get_tool_path(tool_name)
        available = tool_path.exists() and tool_path.is_file()

        if available:
            # Check if file is executable
            available = os.access(tool_path, os.X_OK)

        self.logger.debug(f"Tool {tool_name} local availability: {available}")
        return available

    def is_tool_available_system(self, tool_name: str) -> bool:
        """Check if a tool is available in the system PATH.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool is available in system PATH
        """
        # Special handling for dvdauthor since it's system-only
        if tool_name == "dvdauthor":
            available = shutil.which("dvdauthor") is not None
        elif tool_name == "mkisofs":
            # Check for mkisofs or genisoimage (either can be used)
            available = (
                shutil.which("mkisofs") is not None
                or shutil.which("genisoimage") is not None
            )
        else:
            available = shutil.which(tool_name) is not None

        self.logger.debug(f"Tool {tool_name} system availability: {available}")
        return available

    def _validate_and_get_version(
        self, tool_name: str, tool_path: Optional[Path] = None
    ) -> Tuple[bool, Optional[str]]:
        """Validate tool functionality and get version in a single operation.

        Args:
            tool_name: Name of the tool to validate
            tool_path: Optional specific path to the tool

        Returns:
            Tuple of (is_functional, version_string)
        """
        self.logger.debug(
            f"Validating functionality and getting version for {tool_name}"
        )

        try:
            if tool_name == "ffmpeg":
                cmd = [str(tool_path) if tool_path else "ffmpeg", "-version"]
            elif tool_name == "yt-dlp":
                cmd = [str(tool_path) if tool_path else "yt-dlp", "--version"]
            elif tool_name == "dvdauthor":
                cmd = ["dvdauthor", "--help"]
            elif tool_name == "mkisofs":
                cmd = ["mkisofs", "--version"]
            else:
                self.logger.error(f"Unknown tool for validation: {tool_name}")
                return False, None

            # Use longer timeout for yt-dlp as it can be slow on first run
            timeout = 30 if tool_name == "yt-dlp" else 10
            result = self._run_logged_subprocess(cmd, timeout=timeout)

            # Handle mkisofs fallback to genisoimage
            if tool_name == "mkisofs" and result.returncode != 0:
                self.logger.debug("mkisofs version check failed, trying genisoimage")
                try:
                    fallback_cmd = ["genisoimage", "--version"]
                    fallback_result = self._run_logged_subprocess(
                        fallback_cmd, timeout=timeout
                    )
                    if fallback_result.returncode == 0:
                        result = fallback_result
                        self.logger.debug("Using genisoimage version info")
                    else:
                        self.logger.warning(
                            "Both mkisofs and genisoimage version checks failed"
                        )
                        return False, None
                except Exception:
                    self.logger.warning(
                        "Both mkisofs and genisoimage version checks failed"
                    )
                    return False, None

            # Determine if tool is functional
            if (
                tool_name == "dvdauthor"
                and result.returncode == 1
                and (result.stdout or result.stderr)
            ):
                # dvdauthor --help returns exit code 1 but is still functional
                functional = True
            elif result.returncode != 0:
                self.logger.warning(
                    f"Tool {tool_name} validation failed: {result.stderr}"
                )
                return False, None
            else:
                functional = True

            # Extract version from output
            version = self._extract_version_from_output(
                tool_name, result.stdout, result.stderr
            )

            if functional:
                self.logger.debug(f"Tool {tool_name} is functional, version: {version}")

            return functional, version

        except (
            subprocess.TimeoutExpired,
            subprocess.SubprocessError,
            FileNotFoundError,
        ) as e:
            self.logger.warning(
                f"Tool {tool_name} validation failed with exception: {e}"
            )
            return False, None

    def _extract_version_from_output(
        self, tool_name: str, stdout: str, stderr: str = ""
    ) -> Optional[str]:
        """Extract version information from command output.

        Args:
            tool_name: Name of the tool
            stdout: Standard output from version command
            stderr: Standard error from version command

        Returns:
            Extracted version string or None
        """
        output = stdout

        if tool_name == "ffmpeg":
            # ffmpeg version output format: "ffmpeg version 4.4.0-0ubuntu1"
            for line in output.split("\n"):
                if line.startswith("ffmpeg version"):
                    version = line.split()[2]
                    self.logger.debug(f"Extracted {tool_name} version: {version}")
                    return version
        elif tool_name == "yt-dlp":
            # yt-dlp outputs just the version string
            version = output.strip()
            self.logger.debug(f"Extracted {tool_name} version: {version}")
            return version
        elif tool_name == "dvdauthor":
            # dvdauthor help output contains version info in stderr
            output_to_check = stderr if stderr else output
            for line in output_to_check.split("\n"):
                if "dvdauthor" in line.lower() and "version" in line.lower():
                    # Extract version from line like
                    # "DVDAuthor::dvdauthor, version 0.7.2."
                    parts = line.split("version")
                    if len(parts) > 1:
                        version = parts[1].strip().rstrip(".").split()[0]
                        self.logger.debug(f"Extracted {tool_name} version: {version}")
                        return version
                    else:
                        version = "system"
                        self.logger.debug(f"Detected {tool_name} version: {version}")
                        return version
        elif tool_name == "mkisofs":
            # mkisofs/genisoimage version output varies
            # Look for version pattern in any line
            import re

            for line in output.split("\n"):
                # Pattern matches tool versions like "mkisofs 1.1.11"
                version_match = re.search(
                    r"(?:mkisofs|genisoimage|version)\s+(\d+\.\d+(?:\.\d+)?)",
                    line,
                    re.IGNORECASE,
                )
                if version_match:
                    version = version_match.group(1)
                    self.logger.debug(f"Extracted {tool_name} version: {version}")
                    return version
            # Fallback for minimal version info
            version = "system"
            self.logger.debug(f"Detected {tool_name} version: {version}")
            return version

        self.logger.warning(f"Could not extract version from {tool_name} output")
        return None

    def validate_tool_functionality(
        self, tool_name: str, tool_path: Optional[Path] = None
    ) -> bool:
        """Validate that a tool is functional by running a basic command.

        Args:
            tool_name: Name of the tool to validate
            tool_path: Optional specific path to the tool

        Returns:
            True if tool is functional
        """
        functional, _ = self._validate_and_get_version(tool_name, tool_path)
        return functional

    def get_tool_version(
        self, tool_name: str, tool_path: Optional[Path] = None
    ) -> Optional[str]:
        """Get the version of a tool.

        Args:
            tool_name: Name of the tool
            tool_path: Optional specific path to the tool

        Returns:
            Version string or None if unable to determine
        """
        _, version = self._validate_and_get_version(tool_name, tool_path)
        return version

    def download_file(self, url: str, destination: Path) -> None:
        """Download a file from a URL.

        Args:
            url: URL to download from
            destination: Path to save the file

        Raises:
            ToolDownloadError: If download fails
        """
        self.logger.info(f"Downloading {url} to {destination}")

        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(destination, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if self.progress_callback and total_size > 0:
                            progress = (downloaded / total_size) * 100
                            self.progress_callback(
                                f"Downloading {destination.name}", progress
                            )

            self.logger.info(f"Successfully downloaded {destination.name}")

        except requests.RequestException as e:
            self.logger.error(f"Failed to download {url}: {e}")
            raise ToolDownloadError(f"Failed to download {url}: {e}")

    def extract_archive(self, archive_path: Path, extract_to: Path) -> None:
        """Extract an archive file.

        Args:
            archive_path: Path to the archive file
            extract_to: Directory to extract to

        Raises:
            ToolDownloadError: If extraction fails
        """
        self.logger.debug(f"Extracting {archive_path} to {extract_to}")

        try:
            if archive_path.suffix.lower() == ".zip":
                with zipfile.ZipFile(archive_path, "r") as zip_file:
                    zip_file.extractall(extract_to)
            elif archive_path.suffix.lower() in (".tar", ".tar.gz", ".tar.xz", ".tgz"):
                with tarfile.open(archive_path, "r:*") as tar_file:
                    tar_file.extractall(extract_to)
            else:
                raise ToolDownloadError(
                    f"Unsupported archive format: {archive_path.suffix}"
                )

            self.logger.debug(f"Successfully extracted {archive_path.name}")

        except (zipfile.BadZipFile, tarfile.TarError) as e:
            self.logger.error(f"Failed to extract {archive_path}: {e}")
            raise ToolDownloadError(f"Failed to extract {archive_path}: {e}")

    def make_executable(self, file_path: Path) -> None:
        """Make a file executable.

        Args:
            file_path: Path to the file to make executable
        """
        self.logger.debug(f"Making {file_path} executable")

        # Add execute permissions for user, group, and others
        current_mode = file_path.stat().st_mode
        new_mode = current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        file_path.chmod(new_mode)

        self.logger.debug(f"Made {file_path} executable")

    def download_tool(self, tool_name: str) -> bool:
        """Download a specific tool.

        Args:
            tool_name: Name of the tool to download

        Returns:
            True if download was successful

        Raises:
            ToolDownloadError: If download fails
        """
        self.logger.info(f"Starting download of {tool_name}")

        if not is_platform_supported():
            raise ToolDownloadError("Platform not supported for tool downloads")

        try:
            url = get_download_url(tool_name)
        except (ValueError, RuntimeError) as e:
            raise ToolDownloadError(f"Cannot get download URL for {tool_name}: {e}")

        # Create temporary directory for download
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Determine file extension from URL
            if url.endswith(".zip"):
                download_file = temp_path / f"{tool_name}.zip"
            elif url.endswith((".tar.gz", ".tgz")):
                download_file = temp_path / f"{tool_name}.tar.gz"
            elif url.endswith(".tar.xz"):
                download_file = temp_path / f"{tool_name}.tar.xz"
            else:
                # Direct binary download
                download_file = temp_path / tool_name

            # Download the file
            self.download_file(url, download_file)

            # Extract if it's an archive
            if download_file.suffix.lower() in (".zip", ".tar", ".gz", ".xz", ".tgz"):
                extract_dir = temp_path / "extracted"
                extract_dir.mkdir()
                self.extract_archive(download_file, extract_dir)

                # Find the actual binary in the extracted files
                binary_path = self._find_binary_in_extracted(extract_dir, tool_name)
                if not binary_path:
                    raise ToolDownloadError(
                        f"Could not find {tool_name} binary in extracted files"
                    )
            else:
                binary_path = download_file

            # Copy to final destination
            final_path = self.get_tool_path(tool_name)
            shutil.copy2(binary_path, final_path)

            # Make executable
            self.make_executable(final_path)

            # Validate the downloaded tool and get version in one operation
            functional, version = self._validate_and_get_version(tool_name, final_path)
            if not functional:
                final_path.unlink()  # Clean up
                raise ToolDownloadError(f"Downloaded {tool_name} failed validation")

            # Use the version we already got, or fallback
            version = version or "downloaded"
            versions = self.get_tool_versions()
            versions[tool_name] = version
            self.save_tool_versions(versions)

            self.logger.info(f"Successfully downloaded and installed {tool_name}")
            # Cache will be invalidated by caller if needed
            return True

    def _find_binary_in_extracted(
        self, extract_dir: Path, tool_name: str
    ) -> Optional[Path]:
        """Find the actual binary in extracted files.

        Args:
            extract_dir: Directory containing extracted files
            tool_name: Name of the tool to find

        Returns:
            Path to the binary or None if not found
        """
        self.logger.debug(f"Looking for {tool_name} binary in {extract_dir}")

        # Common patterns for finding binaries
        patterns = [
            tool_name,  # Direct match
            f"{tool_name}.exe",  # Windows executable
        ]

        # Search recursively
        for pattern in patterns:
            for file_path in extract_dir.rglob(pattern):
                if file_path.is_file() and (
                    os.access(file_path, os.X_OK) or file_path.suffix.lower() == ".exe"
                ):
                    self.logger.debug(f"Found {tool_name} binary at {file_path}")
                    return file_path

        self.logger.warning(f"Could not find {tool_name} binary in extracted files")
        return None

    def check_tools(self, use_cache: bool = True) -> Dict[str, Dict[str, Any]]:
        """Check the status of all required tools.

        Args:
            use_cache: Whether to use cached status if available

        Returns:
            Dictionary with tool status information
        """
        # Return cached status if available and requested
        if use_cache and self._tools_status_cache is not None:
            self.logger.debug("Using cached tool status")
            return self._tools_status_cache

        self.logger.debug("Checking tool availability and status")

        tools_status = {}

        # Base required tools
        required_tools = ["ffmpeg", "yt-dlp", "dvdauthor"]

        # Add ISO creation tools if ISO generation is enabled
        if self.settings.generate_iso:
            # Check for mkisofs or genisoimage (either can be used)
            required_tools.append("mkisofs")

        for tool_name in required_tools:
            self.logger.debug(f"Checking status of {tool_name}")

            status: Dict[str, Any] = {
                "available_locally": False,
                "available_system": False,
                "functional": False,
                "version": None,
                "path": None,
            }

            # Check local availability (unless using system tools)
            system_only_tools = ["dvdauthor", "mkisofs"]
            if (
                not self.settings.use_system_tools
                and tool_name not in system_only_tools
            ):
                status["available_locally"] = self.is_tool_available_locally(tool_name)
                if status["available_locally"]:
                    tool_path = self.get_tool_path(tool_name)
                    # Use combined validation and version check to avoid duplicates
                    functional, version = self._validate_and_get_version(
                        tool_name, tool_path
                    )
                    status["functional"] = functional
                    status["version"] = version
                    status["path"] = str(tool_path)

            # Check system availability only if local tool not functional
            status["available_system"] = self.is_tool_available_system(tool_name)
            if status["available_system"] and not status["functional"]:
                # Use combined validation and version check to avoid duplicates
                functional, version = self._validate_and_get_version(tool_name)
                status["functional"] = functional
                status["version"] = version
                if tool_name == "mkisofs":
                    # Check for mkisofs or genisoimage
                    status["path"] = shutil.which("mkisofs") or shutil.which(
                        "genisoimage"
                    )
                else:
                    status["path"] = shutil.which(tool_name)

            tools_status[tool_name] = status
            self.logger.debug(f"Status for {tool_name}: {status}")

        # Cache the results for future use
        self._tools_status_cache = tools_status
        return tools_status

    def _invalidate_cache(self) -> None:
        """Invalidate the tools status cache."""
        self.logger.debug("Invalidating tools status cache")
        self._tools_status_cache = None

    def ensure_tools_available(self) -> Tuple[bool, List[str]]:
        """Ensure all required tools are available.

        Returns:
            Tuple of (success, list of missing tools with instructions)
        """
        self.logger.debug("Ensuring all required tools are available")

        tools_status = self.check_tools(use_cache=False)  # Force fresh check
        missing_tools: List[str] = []
        needs_recheck = False

        for tool_name, status in tools_status.items():
            self.logger.debug(f"Processing tool {tool_name} with status: {status}")

            if not status["functional"]:
                if tool_name == "dvdauthor":
                    # dvdauthor must be installed by user
                    instructions = get_dvdauthor_install_instructions()
                    missing_tools.append(f"{tool_name}: {instructions}")
                    self.logger.warning(f"dvdauthor not available: {instructions}")
                elif tool_name == "mkisofs":
                    # mkisofs is system-only, provide installation instructions
                    missing_tools.append(
                        f"{tool_name}: Not available. Install with:\n"
                        "  macOS: brew install dvdrtools\n"
                        "  Ubuntu/Debian: sudo apt install genisoimage\n"
                        "  RHEL/CentOS: sudo yum install genisoimage"
                    )
                    self.logger.warning(
                        "mkisofs/genisoimage not available for ISO creation"
                    )
                elif self.settings.download_tools:
                    # Try to download the tool
                    try:
                        self.logger.info(f"Attempting to download {tool_name}")
                        self.download_tool(tool_name)
                        self.logger.info(f"Successfully downloaded {tool_name}")
                        needs_recheck = True
                    except ToolDownloadError as e:
                        missing_tools.append(f"{tool_name}: Download failed - {e}")
                        self.logger.error(f"Failed to download {tool_name}: {e}")
                    except Exception as e:
                        missing_tools.append(f"{tool_name}: Unexpected error - {e}")
                        self.logger.error(
                            f"Unexpected error downloading {tool_name}: {e}"
                        )
                else:
                    missing_tools.append(
                        f"{tool_name}: Not available and auto-download disabled"
                    )
                    self.logger.warning(
                        f"{tool_name} not available and auto-download disabled. "
                        f"Status: available_locally={status['available_locally']}, "
                        f"available_system={status['available_system']}, "
                        f"functional={status['functional']}, path={status['path']}"
                    )

        # Only recheck tools once if any downloads occurred
        if needs_recheck:
            self.logger.debug("Rechecking tools after downloads")
            # Invalidate cache before rechecking since tools were downloaded
            self._invalidate_cache()
            tools_status = self.check_tools(use_cache=False)

            # Verify downloaded tools are functional
            for tool_name, status in tools_status.items():
                if not status["functional"] and tool_name not in [
                    "dvdauthor",
                    "mkisofs",
                ]:
                    # Tool was attempted to be downloaded but still not functional
                    if f"{tool_name}: Download failed" not in str(missing_tools):
                        missing_tools.append(
                            f"{tool_name}: Downloaded but not functional"
                        )
                        self.logger.error(
                            f"{tool_name} downloaded but validation failed: {status}"
                        )

        success = len(missing_tools) == 0

        if success:
            self.logger.debug("All required tools are available")
        else:
            self.logger.warning(f"Missing tools: {missing_tools}")

        return success, missing_tools

    def get_tool_command(self, tool_name: str) -> List[str]:
        """Get the command to run a specific tool.

        Args:
            tool_name: Name of the tool

        Returns:
            List containing the command components

        Raises:
            ToolValidationError: If tool is not available
        """
        tools_status = self.check_tools()
        status = tools_status.get(tool_name)

        if not status or not status["functional"]:
            raise ToolValidationError(
                f"Tool {tool_name} is not available or functional"
            )

        if status["path"]:
            command = [status["path"]]
        else:
            command = [tool_name]

        self.logger.debug(f"Command for {tool_name}: {command}")
        return command

    def get_latest_ytdlp_version(self) -> Optional[str]:
        """Get the latest yt-dlp version from GitHub releases.

        Returns:
            Latest version string or None if unable to determine
        """
        try:
            self.logger.debug("Checking for latest yt-dlp version from GitHub")

            # Use GitHub API to get latest release info
            api_url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()

            release_data = response.json()
            latest_version = str(release_data.get("tag_name", "")).strip()

            if latest_version:
                self.logger.debug(f"Latest yt-dlp version: {latest_version}")
                return latest_version
            else:
                self.logger.warning(
                    "Could not determine latest yt-dlp version from API response"
                )
                return None

        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Failed to check latest yt-dlp version: {e}")
            return None
        except (KeyError, ValueError) as e:
            self.logger.warning(f"Failed to parse yt-dlp version response: {e}")
            return None

    def compare_versions(self, current: str, latest: str) -> bool:
        """Compare version strings to determine if update is needed.

        Args:
            current: Current version string
            latest: Latest available version string

        Returns:
            True if latest is newer than current, False otherwise
        """
        try:
            # Remove 'v' prefix if present and any non-numeric suffixes
            def clean_version(version: str) -> Tuple[int, ...]:
                cleaned = version.lstrip("v").split("-")[0].split("+")[0]
                parts = []
                for part in cleaned.split("."):
                    try:
                        parts.append(int(part))
                    except ValueError:
                        # Skip non-numeric parts
                        break
                return tuple(parts)

            current_parts = clean_version(current)
            latest_parts = clean_version(latest)

            # If either version parsing failed (empty tuple), can't compare
            if not current_parts or not latest_parts:
                self.logger.warning(
                    f"Failed to parse version parts: current={current_parts}, "
                    f"latest={latest_parts}"
                )
                return False

            # Pad shorter version with zeros for comparison
            max_len = max(len(current_parts), len(latest_parts))
            current_padded = current_parts + (0,) * (max_len - len(current_parts))
            latest_padded = latest_parts + (0,) * (max_len - len(latest_parts))

            is_newer = latest_padded > current_padded
            self.logger.debug(
                f"Version comparison: {current} -> {latest} (newer: {is_newer})"
            )

            return is_newer

        except Exception as e:
            self.logger.warning(
                f"Failed to compare versions {current} vs {latest}: {e}"
            )
            return False

    def check_and_update_ytdlp(self) -> bool:
        """Check for yt-dlp updates and update if a newer version is available.

        Returns:
            True if yt-dlp was updated or is already current, False if update failed
        """
        self.logger.info("Checking for yt-dlp updates...")

        try:
            # Check if yt-dlp is available locally and get its version
            if self.is_tool_available_locally("yt-dlp"):
                local_path = self.get_tool_path("yt-dlp")
                current_version = self.get_tool_version("yt-dlp", local_path)
            else:
                current_version = None

            if not current_version:
                self.logger.info(
                    "yt-dlp not found locally, will download latest version"
                )
                return self.download_tool("yt-dlp")

            # Get latest version
            latest_version = self.get_latest_ytdlp_version()
            if not latest_version:
                self.logger.warning(
                    "Could not determine latest yt-dlp version, skipping update"
                )
                return True  # Don't fail if we can't check for updates

            # Compare versions
            if not self.compare_versions(current_version, latest_version):
                self.logger.info(
                    f"yt-dlp is already up to date (current: {current_version})"
                )
                return True

            self.logger.info(
                f"yt-dlp update available: {current_version} -> {latest_version}"
            )

            # Back up current version
            current_path = self.get_tool_path("yt-dlp")
            backup_path = None
            if current_path and current_path.exists():
                backup_path = current_path.with_suffix(f".backup-{current_version}")
                self.logger.debug(f"Backing up current yt-dlp to {backup_path}")
                shutil.copy2(current_path, backup_path)

            # Download new version
            success = self.download_tool("yt-dlp")

            if success:
                self.logger.info(
                    f"Successfully updated yt-dlp from {current_version} to "
                    f"{latest_version}"
                )

                # Verify the new version
                new_version = self.get_tool_version("yt-dlp")
                if new_version and new_version != current_version:
                    self.logger.info(
                        f"yt-dlp update verified (new version: {new_version})"
                    )

                    # Clean up backup if update was successful
                    if current_path and backup_path and backup_path.exists():
                        try:
                            backup_path.unlink()
                            self.logger.debug(
                                "Removed backup file after successful update"
                            )
                        except OSError as e:
                            self.logger.warning(f"Could not remove backup file: {e}")
                else:
                    self.logger.warning(
                        "Could not verify yt-dlp update, but download appeared "
                        "successful"
                    )

                return True
            else:
                self.logger.error("Failed to download new yt-dlp version")

                # Restore backup if available
                if current_path and backup_path and backup_path.exists():
                    try:
                        shutil.copy2(backup_path, current_path)
                        backup_path.unlink()
                        self.logger.info(
                            "Restored previous yt-dlp version after failed update"
                        )
                    except OSError as e:
                        self.logger.error(
                            f"Could not restore backup after failed update: {e}"
                        )

                return False

        except Exception as e:
            self.logger.error(f"Unexpected error during yt-dlp update check: {e}")
            return False
