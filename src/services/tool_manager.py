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
from ..utils.logging import get_logger
from ..utils.platform import (
    get_download_url,
    get_dvdauthor_install_instructions,
    is_platform_supported,
)

# Simple progress callback type
ProgressCallback = Callable[[str, float], None]

logger = get_logger(__name__)


class ToolManagerError(Exception):
    """Base exception for tool manager errors."""

    pass


class ToolDownloadError(ToolManagerError):
    """Exception raised when tool download fails."""

    pass


class ToolValidationError(ToolManagerError):
    """Exception raised when tool validation fails."""

    pass


class ToolManager:
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
        self.settings = settings
        self.progress_callback = progress_callback
        self.bin_dir = settings.bin_dir
        self.tool_versions_file = self.bin_dir / "tool_versions.json"

        # Cache for tool status to avoid repeated expensive validation calls
        self._tools_status_cache: Optional[Dict[str, Dict[str, Any]]] = None

        # Ensure bin directory exists
        self.bin_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"ToolManager initialized with bin_dir: {self.bin_dir}")

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
        logger.info(f"Executing command: {cmd_str}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=text,
                timeout=timeout,
                **kwargs,
            )

            # Log command completion and output
            logger.info(
                f"Command completed with return code {result.returncode}: {cmd_str}"
            )

            if capture_output and result.stdout:
                logger.debug(f"Command stdout: {result.stdout.strip()}")

            if capture_output and result.stderr:
                if result.returncode == 0:
                    logger.debug(f"Command stderr: {result.stderr.strip()}")
                else:
                    logger.warning(f"Command stderr: {result.stderr.strip()}")

            return result

        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out after {timeout}s: {cmd_str}")
            raise
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed with return code {e.returncode}: {cmd_str}")
            if e.stdout:
                logger.debug(f"Failed command stdout: {e.stdout.strip()}")
            if e.stderr:
                logger.debug(f"Failed command stderr: {e.stderr.strip()}")
            raise
        except Exception as e:
            logger.error(f"Command execution failed: {cmd_str} - {e}")
            raise

    def get_tool_versions(self) -> Dict[str, str]:
        """Load tool versions from tool_versions.json.

        Returns:
            Dictionary mapping tool names to versions
        """
        if not self.tool_versions_file.exists():
            logger.debug("No tool_versions.json found, returning empty dict")
            return {}

        try:
            with open(self.tool_versions_file, "r") as f:
                versions: Dict[str, str] = json.load(f)
            logger.debug(f"Loaded tool versions: {versions}")
            return versions
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load tool versions: {e}")
            return {}

    def save_tool_versions(self, versions: Dict[str, str]) -> None:
        """Save tool versions to tool_versions.json.

        Args:
            versions: Dictionary mapping tool names to versions
        """
        try:
            with open(self.tool_versions_file, "w") as f:
                json.dump(versions, f, indent=2)
            logger.debug(f"Saved tool versions: {versions}")
        except IOError as e:
            logger.error(f"Failed to save tool versions: {e}")
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

        logger.debug(f"Tool {tool_name} local availability: {available}")
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

        logger.debug(f"Tool {tool_name} system availability: {available}")
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
        logger.debug(f"Validating functionality and getting version for {tool_name}")

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
                logger.error(f"Unknown tool for validation: {tool_name}")
                return False, None

            # Use longer timeout for yt-dlp as it can be slow on first run
            timeout = 30 if tool_name == "yt-dlp" else 10
            result = self._run_logged_subprocess(cmd, timeout=timeout)

            # Handle mkisofs fallback to genisoimage
            if tool_name == "mkisofs" and result.returncode != 0:
                logger.debug("mkisofs version check failed, trying genisoimage")
                try:
                    fallback_cmd = ["genisoimage", "--version"]
                    fallback_result = self._run_logged_subprocess(
                        fallback_cmd, timeout=timeout
                    )
                    if fallback_result.returncode == 0:
                        result = fallback_result
                        logger.debug("Using genisoimage version info")
                    else:
                        logger.warning(
                            "Both mkisofs and genisoimage version checks failed"
                        )
                        return False, None
                except Exception:
                    logger.warning("Both mkisofs and genisoimage version checks failed")
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
                logger.warning(f"Tool {tool_name} validation failed: {result.stderr}")
                return False, None
            else:
                functional = True

            # Extract version from output
            version = self._extract_version_from_output(
                tool_name, result.stdout, result.stderr
            )

            if functional:
                logger.debug(f"Tool {tool_name} is functional, version: {version}")

            return functional, version

        except (
            subprocess.TimeoutExpired,
            subprocess.SubprocessError,
            FileNotFoundError,
        ) as e:
            logger.warning(f"Tool {tool_name} validation failed with exception: {e}")
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
                    logger.debug(f"Extracted {tool_name} version: {version}")
                    return version
        elif tool_name == "yt-dlp":
            # yt-dlp outputs just the version string
            version = output.strip()
            logger.debug(f"Extracted {tool_name} version: {version}")
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
                        logger.debug(f"Extracted {tool_name} version: {version}")
                        return version
                    else:
                        version = "system"
                        logger.debug(f"Detected {tool_name} version: {version}")
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
                    logger.debug(f"Extracted {tool_name} version: {version}")
                    return version
            # Fallback for minimal version info
            version = "system"
            logger.debug(f"Detected {tool_name} version: {version}")
            return version

        logger.warning(f"Could not extract version from {tool_name} output")
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
        logger.info(f"Downloading {url} to {destination}")

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

            logger.info(f"Successfully downloaded {destination.name}")

        except requests.RequestException as e:
            logger.error(f"Failed to download {url}: {e}")
            raise ToolDownloadError(f"Failed to download {url}: {e}")

    def extract_archive(self, archive_path: Path, extract_to: Path) -> None:
        """Extract an archive file.

        Args:
            archive_path: Path to the archive file
            extract_to: Directory to extract to

        Raises:
            ToolDownloadError: If extraction fails
        """
        logger.debug(f"Extracting {archive_path} to {extract_to}")

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

            logger.debug(f"Successfully extracted {archive_path.name}")

        except (zipfile.BadZipFile, tarfile.TarError) as e:
            logger.error(f"Failed to extract {archive_path}: {e}")
            raise ToolDownloadError(f"Failed to extract {archive_path}: {e}")

    def make_executable(self, file_path: Path) -> None:
        """Make a file executable.

        Args:
            file_path: Path to the file to make executable
        """
        logger.debug(f"Making {file_path} executable")

        # Add execute permissions for user, group, and others
        current_mode = file_path.stat().st_mode
        new_mode = current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        file_path.chmod(new_mode)

        logger.debug(f"Made {file_path} executable")

    def download_tool(self, tool_name: str) -> bool:
        """Download a specific tool.

        Args:
            tool_name: Name of the tool to download

        Returns:
            True if download was successful

        Raises:
            ToolDownloadError: If download fails
        """
        logger.info(f"Starting download of {tool_name}")

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

            logger.info(f"Successfully downloaded and installed {tool_name}")
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
        logger.debug(f"Looking for {tool_name} binary in {extract_dir}")

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
                    logger.debug(f"Found {tool_name} binary at {file_path}")
                    return file_path

        logger.warning(f"Could not find {tool_name} binary in extracted files")
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
            logger.debug("Using cached tool status")
            return self._tools_status_cache

        logger.info("Checking tool availability and status")

        tools_status = {}

        # Base required tools
        required_tools = ["ffmpeg", "yt-dlp", "dvdauthor"]

        # Add ISO creation tools if ISO generation is enabled
        if self.settings.generate_iso:
            # Check for mkisofs or genisoimage (either can be used)
            required_tools.append("mkisofs")

        for tool_name in required_tools:
            logger.debug(f"Checking status of {tool_name}")

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
            logger.debug(f"Status for {tool_name}: {status}")

        # Cache the results for future use
        self._tools_status_cache = tools_status
        return tools_status

    def _invalidate_cache(self) -> None:
        """Invalidate the tools status cache."""
        logger.debug("Invalidating tools status cache")
        self._tools_status_cache = None

    def ensure_tools_available(self) -> Tuple[bool, List[str]]:
        """Ensure all required tools are available.

        Returns:
            Tuple of (success, list of missing tools with instructions)
        """
        logger.info("Ensuring all required tools are available")

        tools_status = self.check_tools(use_cache=False)  # Force fresh check
        missing_tools: List[str] = []
        needs_recheck = False

        for tool_name, status in tools_status.items():
            logger.debug(f"Processing tool {tool_name} with status: {status}")

            if not status["functional"]:
                if tool_name == "dvdauthor":
                    # dvdauthor must be installed by user
                    instructions = get_dvdauthor_install_instructions()
                    missing_tools.append(f"{tool_name}: {instructions}")
                    logger.warning(f"dvdauthor not available: {instructions}")
                elif tool_name == "mkisofs":
                    # mkisofs is system-only, provide installation instructions
                    missing_tools.append(
                        f"{tool_name}: Not available. Install with:\n"
                        "  macOS: brew install dvdrtools\n"
                        "  Ubuntu/Debian: sudo apt install genisoimage\n"
                        "  RHEL/CentOS: sudo yum install genisoimage"
                    )
                    logger.warning("mkisofs/genisoimage not available for ISO creation")
                elif self.settings.download_tools:
                    # Try to download the tool
                    try:
                        logger.info(f"Attempting to download {tool_name}")
                        self.download_tool(tool_name)
                        logger.info(f"Successfully downloaded {tool_name}")
                        needs_recheck = True
                    except ToolDownloadError as e:
                        missing_tools.append(f"{tool_name}: Download failed - {e}")
                        logger.error(f"Failed to download {tool_name}: {e}")
                    except Exception as e:
                        missing_tools.append(f"{tool_name}: Unexpected error - {e}")
                        logger.error(f"Unexpected error downloading {tool_name}: {e}")
                else:
                    missing_tools.append(
                        f"{tool_name}: Not available and auto-download disabled"
                    )
                    logger.warning(
                        f"{tool_name} not available and auto-download disabled. "
                        f"Status: available_locally={status['available_locally']}, "
                        f"available_system={status['available_system']}, "
                        f"functional={status['functional']}, path={status['path']}"
                    )

        # Only recheck tools once if any downloads occurred
        if needs_recheck:
            logger.debug("Rechecking tools after downloads")
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
                        logger.error(
                            f"{tool_name} downloaded but validation failed: {status}"
                        )

        success = len(missing_tools) == 0

        if success:
            logger.info("All required tools are available")
        else:
            logger.warning(f"Missing tools: {missing_tools}")

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

        logger.debug(f"Command for {tool_name}: {command}")
        return command
