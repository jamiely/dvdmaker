"""Video downloading service using yt-dlp for YouTube playlists."""

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config.settings import Settings
from ..exceptions import DVDMakerError
from ..models.playlist import Playlist, PlaylistMetadata, VideoStatus
from ..models.video import VideoMetadata
from ..services.cache_manager import CacheManager
from ..services.tool_manager import ToolManager
from ..utils.logging import get_logger
from ..utils.progress import ProgressCallback, ProgressTracker, SilentProgressCallback

logger = get_logger(__name__)


class YtDlpError(DVDMakerError):
    """Exception raised when yt-dlp operations fail."""

    pass


class VideoDownloader:
    """Downloads videos from YouTube playlists using yt-dlp."""

    def __init__(
        self,
        settings: Settings,
        cache_manager: CacheManager,
        tool_manager: ToolManager,
    ) -> None:
        """Initialize video downloader.

        Args:
            settings: Application settings
            cache_manager: Cache manager for downloaded files
            tool_manager: Tool manager for yt-dlp binary
        """
        self.settings = settings
        self.cache_manager = cache_manager
        self.tool_manager = tool_manager

        logger.debug(
            f"VideoDownloader initialized with cache_dir={settings.cache_dir}, "
            f"rate_limit={settings.download_rate_limit}"
        )

    def _ensure_yt_dlp_available(self) -> None:
        """Ensure yt-dlp is available.

        Raises:
            RuntimeError: If yt-dlp cannot be found or downloaded
        """
        logger.debug("Checking yt-dlp availability")

        # Check if tool manager has yt-dlp available
        if not self.tool_manager.is_tool_available_locally("yt-dlp"):
            logger.info("yt-dlp not found, downloading...")
            self.tool_manager.download_tool("yt-dlp")

        # Verify availability by trying to get the command
        try:
            yt_dlp_cmd = self.tool_manager.get_tool_command("yt-dlp")
            logger.debug(f"Using yt-dlp command: {yt_dlp_cmd}")
        except Exception as e:
            logger.error("Failed to get yt-dlp command after download")
            raise RuntimeError(
                "yt-dlp is not available and could not be downloaded"
            ) from e

    def _run_yt_dlp(
        self,
        args: List[str],
        capture_output: bool = True,
        timeout: Optional[int] = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run yt-dlp with the given arguments.

        Args:
            args: Command line arguments for yt-dlp
            capture_output: Whether to capture stdout/stderr
            timeout: Optional timeout in seconds

        Returns:
            Completed process

        Raises:
            YtDlpError: If yt-dlp command fails
        """
        self._ensure_yt_dlp_available()

        # Build full command using ToolManager
        yt_dlp_cmd = self.tool_manager.get_tool_command("yt-dlp")
        cmd = yt_dlp_cmd + args

        logger.debug(f"Executing yt-dlp command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                check=False,  # We'll check return code manually
            )

            # Log command completion and output
            logger.debug(f"yt-dlp completed with return code {result.returncode}")

            if result.stdout:
                logger.debug(f"yt-dlp stdout: {result.stdout.strip()}")

            if result.stderr:
                if result.returncode == 0:
                    logger.debug(f"yt-dlp stderr: {result.stderr.strip()}")
                else:
                    logger.warning(f"yt-dlp stderr: {result.stderr.strip()}")

            if result.returncode != 0:
                error_msg = (
                    f"yt-dlp failed with return code {result.returncode}: "
                    f"{result.stderr if result.stderr else 'No error output'}"
                )
                logger.error(error_msg)
                raise YtDlpError(error_msg)

            logger.trace(  # type: ignore[attr-defined]
                "yt-dlp command completed successfully"
            )
            return result

        except subprocess.TimeoutExpired as e:
            logger.error(f"yt-dlp command timed out after {timeout}s")
            raise YtDlpError(f"Command timed out after {timeout}s") from e
        except OSError as e:
            logger.error(f"Failed to execute yt-dlp: {e}")
            raise YtDlpError(f"Failed to execute yt-dlp: {e}") from e

    def _get_base_yt_dlp_args(self) -> List[str]:
        """Get base yt-dlp arguments used for all operations.

        Returns:
            List of base command line arguments
        """
        args = [
            "--no-warnings",  # Reduce noise in output
            "--limit-rate",
            self.settings.download_rate_limit,
            "--cache-dir",
            str(self.settings.cache_dir / "yt-dlp-cache"),
        ]

        return args

    def extract_playlist_metadata(
        self, playlist_url: str, progress_callback: Optional[ProgressCallback] = None
    ) -> PlaylistMetadata:
        """Extract metadata for a YouTube playlist.

        Args:
            playlist_url: YouTube playlist URL
            progress_callback: Optional progress callback

        Returns:
            PlaylistMetadata with basic playlist information

        Raises:
            YtDlpError: If playlist extraction fails
        """
        logger.debug(f"Extracting playlist metadata from: {playlist_url}")

        callback = progress_callback or SilentProgressCallback()
        tracker = ProgressTracker(1, callback, "Extracting playlist metadata...")

        try:
            # Extract playlist ID from URL
            playlist_id = self._extract_playlist_id(playlist_url)
            logger.debug(f"Extracted playlist ID: {playlist_id}")

            # Check cache first
            cached_metadata = self.cache_manager.get_cached_playlist_metadata(
                playlist_id
            )
            if cached_metadata:
                logger.debug(f"Using cached playlist metadata for {playlist_id}")
                tracker.complete("Used cached playlist metadata")
                return cached_metadata

            # Build yt-dlp command for playlist extraction
            args = self._get_base_yt_dlp_args() + [
                "--flat-playlist",
                "--dump-json",
                playlist_url,
            ]

            result = self._run_yt_dlp(args)

            # Parse first line to get playlist metadata
            lines = result.stdout.strip().split("\n")
            if not lines:
                raise YtDlpError("No output from yt-dlp playlist extraction")

            # First line contains playlist metadata
            playlist_data = json.loads(lines[0])

            metadata = PlaylistMetadata(
                playlist_id=playlist_id,
                title=playlist_data.get("title", f"Playlist {playlist_id}"),
                description=playlist_data.get("description"),
                video_count=len(lines) - 1,  # Subtract playlist line
                total_size_estimate=None,  # Will be calculated later
            )

            # Cache the metadata
            self.cache_manager.store_playlist_metadata(metadata)

            tracker.complete(f"Extracted metadata for playlist: {metadata.title}")
            logger.info(
                f"Successfully extracted playlist metadata: {metadata.title} "
                f"({metadata.video_count} videos)"
            )

            return metadata

        except Exception as e:
            error_msg = f"Failed to extract playlist metadata: {e}"
            logger.error(error_msg)
            tracker.error(error_msg)
            raise YtDlpError(error_msg) from e

    def extract_playlist_videos(
        self, playlist_url: str, progress_callback: Optional[ProgressCallback] = None
    ) -> List[VideoMetadata]:
        """Extract video metadata for all videos in a playlist.

        Args:
            playlist_url: YouTube playlist URL
            progress_callback: Optional progress callback

        Returns:
            List of VideoMetadata objects in playlist order

        Raises:
            YtDlpError: If video extraction fails
        """
        logger.debug(f"Extracting video metadata from playlist: {playlist_url}")

        callback = progress_callback or SilentProgressCallback()
        tracker = ProgressTracker(1, callback, "Extracting video metadata...")

        try:
            # Build yt-dlp command for video extraction
            args = self._get_base_yt_dlp_args() + [
                "--flat-playlist",
                "--dump-json",
                playlist_url,
            ]

            result = self._run_yt_dlp(args)

            lines = result.stdout.strip().split("\n")
            if len(lines) < 2:  # At least playlist + one video
                raise YtDlpError("Playlist appears to be empty or invalid")

            videos = []
            # Skip first line (playlist metadata)
            for i, line in enumerate(lines[1:], 1):
                try:
                    video_data = json.loads(line)

                    # Extract video metadata
                    video = VideoMetadata(
                        video_id=video_data.get("id", ""),
                        title=video_data.get("title", f"Video {i}"),
                        duration=video_data.get("duration", 0),
                        url=video_data.get("url", video_data.get("webpage_url", "")),
                        thumbnail_url=video_data.get("thumbnail"),
                        description=video_data.get("description"),
                    )

                    videos.append(video)
                    logger.trace(  # type: ignore[attr-defined]
                        f"Extracted video {i}: {video.title} ({video.video_id})"
                    )

                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse video metadata line {i}: {e}")
                    continue

            tracker.complete(f"Extracted metadata for {len(videos)} videos")
            logger.debug(f"Successfully extracted {len(videos)} video metadata entries")

            return videos

        except Exception as e:
            error_msg = f"Failed to extract playlist videos: {e}"
            logger.error(error_msg)
            tracker.error(error_msg)
            raise YtDlpError(error_msg) from e

    def extract_full_playlist(
        self, playlist_url: str, progress_callback: Optional[ProgressCallback] = None
    ) -> Playlist:
        """Extract complete playlist with metadata and videos.

        Args:
            playlist_url: YouTube playlist URL
            progress_callback: Optional progress callback

        Returns:
            Complete Playlist object with metadata and videos

        Raises:
            YtDlpError: If playlist extraction fails
        """
        logger.debug(f"Extracting complete playlist: {playlist_url}")

        callback = progress_callback or SilentProgressCallback()

        try:
            # Extract playlist metadata
            metadata = self.extract_playlist_metadata(playlist_url, callback)

            # Extract video metadata
            videos = self.extract_playlist_videos(playlist_url, callback)

            # Update metadata with actual video count
            if len(videos) != metadata.video_count:
                logger.debug(
                    f"Updating video count: {metadata.video_count} -> {len(videos)}"
                )
                metadata = PlaylistMetadata(
                    playlist_id=metadata.playlist_id,
                    title=metadata.title,
                    description=metadata.description,
                    video_count=len(videos),
                    total_size_estimate=metadata.total_size_estimate,
                )

            # Create video status mapping (all start as AVAILABLE)
            video_statuses = {video.video_id: VideoStatus.AVAILABLE for video in videos}

            playlist = Playlist(
                metadata=metadata,
                videos=videos,
                video_statuses=video_statuses,
            )

            logger.info(
                f"Successfully extracted complete playlist: {metadata.title} "
                f"({len(videos)} videos)"
            )

            return playlist

        except Exception as e:
            error_msg = f"Failed to extract complete playlist: {e}"
            logger.error(error_msg)
            if callback:
                callback.error(error_msg)
            raise YtDlpError(error_msg) from e

    def download_video(
        self,
        video: VideoMetadata,
        playlist: Playlist,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> bool:
        """Download a single video from the playlist.

        Args:
            video: Video metadata to download
            playlist: Playlist containing the video (for status updates)
            progress_callback: Optional progress callback

        Returns:
            True if download succeeded, False otherwise
        """
        logger.info(f"Downloading video: {video.title} ({video.video_id})")

        callback = progress_callback or SilentProgressCallback()
        tracker = ProgressTracker(1, callback, f"Downloading: {video.title}")

        try:
            # Update status to downloading
            playlist.update_video_status(video.video_id, VideoStatus.DOWNLOADING)

            # Check cache first
            cached_file = self.cache_manager.get_cached_download(video.video_id)
            if cached_file:
                logger.debug(f"Video {video.video_id} found in cache")
                playlist.update_video_status(video.video_id, VideoStatus.DOWNLOADED)
                tracker.complete("Used cached download")
                return True

            # Create temporary download directory
            with tempfile.TemporaryDirectory(
                prefix="dvdmaker_download_", dir=self.settings.temp_dir
            ) as temp_dir:
                temp_path = Path(temp_dir)

                # Build yt-dlp download command
                output_template = str(temp_path / "%(id)s.%(ext)s")
                args = [
                    "--format",
                    self.settings.video_quality,
                    "--output",
                    output_template,
                    "--limit-rate",
                    self.settings.download_rate_limit,
                    "--cache-dir",
                    str(self.settings.cache_dir / "yt-dlp-cache"),
                    "--no-warnings",
                    video.url,
                ]

                # Run download
                self._run_yt_dlp(args, timeout=3600)  # 1 hour timeout

                # Find downloaded file
                downloaded_files = list(temp_path.glob(f"{video.video_id}.*"))
                if not downloaded_files:
                    raise YtDlpError(f"No downloaded file found for {video.video_id}")

                downloaded_file = downloaded_files[0]
                logger.debug(f"Downloaded file: {downloaded_file}")

                # Store in cache
                cached_file = self.cache_manager.store_download(
                    video.video_id, downloaded_file, video
                )

                # Update status
                playlist.update_video_status(video.video_id, VideoStatus.DOWNLOADED)

                tracker.complete(f"Downloaded: {video.title}")
                logger.info(
                    f"Successfully downloaded video: {video.title} "
                    f"({cached_file.size_mb:.1f}MB)"
                )

                return True

        except YtDlpError as e:
            logger.error(f"Failed to download video {video.video_id}: {e}")
            playlist.update_video_status(video.video_id, VideoStatus.FAILED)
            tracker.error(f"Download failed: {str(e)}")
            return False

        except Exception as e:
            logger.error(f"Unexpected error downloading video {video.video_id}: {e}")
            playlist.update_video_status(video.video_id, VideoStatus.FAILED)
            tracker.error(f"Download failed: {str(e)}")
            return False

    def download_playlist(
        self,
        playlist_url: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Playlist:
        """Download all videos in a playlist.

        Args:
            playlist_url: YouTube playlist URL
            progress_callback: Optional progress callback

        Returns:
            Playlist object with updated video statuses

        Raises:
            YtDlpError: If playlist extraction fails
        """
        logger.debug(f"Starting playlist download: {playlist_url}")

        callback = progress_callback or SilentProgressCallback()

        try:
            # Extract playlist
            playlist = self.extract_full_playlist(playlist_url, callback)

            # Check DVD capacity
            if not playlist.check_dvd_capacity():
                logger.warning(
                    f"Playlist {playlist.metadata.title} may exceed DVD capacity"
                )

            # Download each video
            total_videos = len(playlist.videos)
            successful_downloads = 0

            tracker = ProgressTracker(
                total_videos, callback, f"Downloading {total_videos} videos..."
            )

            for i, video in enumerate(playlist.videos, 1):
                tracker.update(
                    0,  # Don't increment yet
                    f"Downloading {i}/{total_videos}: {video.title}",
                )

                # Skip if already downloaded
                if self.cache_manager.is_download_cached(video.video_id):
                    logger.debug(f"Video {video.video_id} already cached, skipping")
                    playlist.update_video_status(video.video_id, VideoStatus.DOWNLOADED)
                    successful_downloads += 1
                    tracker.update(1, f"Cached: {video.title}")
                    continue

                # Attempt download
                if self.download_video(video, playlist, None):  # No nested progress
                    successful_downloads += 1
                    tracker.update(1, f"Downloaded: {video.title}")
                else:
                    tracker.update(1, f"Failed: {video.title}")

            # Report results
            success_rate = playlist.get_success_rate()
            if successful_downloads == total_videos:
                message = f"Downloaded all {total_videos} videos successfully"
                tracker.complete(message)
                logger.debug(message)
            else:
                failed_count = total_videos - successful_downloads
                message = (
                    f"Downloaded {successful_downloads}/{total_videos} videos "
                    f"({success_rate:.1f}% success rate, {failed_count} failed)"
                )
                if successful_downloads > 0:
                    tracker.complete(message)
                    logger.warning(message)
                else:
                    tracker.error("All downloads failed")
                    logger.error("All video downloads failed")

            return playlist

        except Exception as e:
            error_msg = f"Failed to download playlist: {e}"
            logger.error(error_msg)
            if callback:
                callback.error(error_msg)
            raise YtDlpError(error_msg) from e

    def _extract_playlist_id(self, playlist_url: str) -> str:
        """Extract playlist ID from YouTube URL.

        Args:
            playlist_url: YouTube playlist URL

        Returns:
            Playlist ID string

        Raises:
            ValueError: If URL doesn't contain a valid playlist ID
        """
        # Match various YouTube playlist URL formats
        patterns = [
            r"[?&]list=([a-zA-Z0-9_-]+)",  # Standard format
            r"youtube\.com/playlist\?.*list=([a-zA-Z0-9_-]+)",  # Direct playlist URL
            r"youtu\.be/.*[?&]list=([a-zA-Z0-9_-]+)",  # Short URL with playlist
        ]

        for pattern in patterns:
            match = re.search(pattern, playlist_url)
            if match:
                playlist_id = match.group(1)
                logger.trace(  # type: ignore[attr-defined]
                    f"Extracted playlist ID {playlist_id} from URL"
                )
                return playlist_id

        logger.error(f"Could not extract playlist ID from URL: {playlist_url}")
        raise ValueError(f"Invalid YouTube playlist URL: {playlist_url}")

    def get_download_info(self, video_url: str) -> Dict[str, Any]:
        """Get detailed information about a video without downloading.

        Args:
            video_url: YouTube video URL

        Returns:
            Dictionary with video information

        Raises:
            YtDlpError: If information extraction fails
        """
        logger.debug(f"Getting download info for: {video_url}")

        try:
            args = self._get_base_yt_dlp_args() + [
                "--no-download",
                "--dump-json",
                video_url,
            ]

            result = self._run_yt_dlp(args)
            info: Dict[str, Any] = json.loads(result.stdout.strip())

            logger.trace(  # type: ignore[attr-defined]
                f"Retrieved download info for video: {info.get('title', 'Unknown')}"
            )

            return info

        except Exception as e:
            error_msg = f"Failed to get download info: {e}"
            logger.error(error_msg)
            raise YtDlpError(error_msg) from e

    def validate_url(self, url: str) -> bool:
        """Validate if a URL is a supported YouTube playlist.

        Args:
            url: URL to validate

        Returns:
            True if URL is valid, False otherwise
        """
        try:
            self._extract_playlist_id(url)
            logger.debug(f"URL validation successful: {url}")
            return True
        except ValueError:
            logger.debug(f"URL validation failed: {url}")
            return False
