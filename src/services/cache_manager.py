"""Cache management for video files and metadata.

This module provides intelligent file caching to avoid redundant operations,
with video ID as the primary cache key and integrity verification through checksums.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from ..models.playlist import PlaylistMetadata
from ..models.video import VideoFile, VideoMetadata
from ..utils.filename import FilenameMapper
from ..utils.logging import get_logger

logger = get_logger(__name__)


class CacheManager:
    """Manages caching of downloaded and converted video files."""

    def __init__(
        self,
        cache_dir: Path,
        force_download: bool = False,
        force_convert: bool = False,
    ) -> None:
        """Initialize the cache manager.

        Args:
            cache_dir: Base directory for cache storage
            force_download: If True, ignore download cache and re-download files
            force_convert: If True, ignore conversion cache and re-convert files
        """
        self.cache_dir = cache_dir
        self.force_download = force_download
        self.force_convert = force_convert

        # Cache subdirectories
        self.downloads_dir = cache_dir / "downloads"
        self.converted_dir = cache_dir / "converted"
        self.metadata_dir = cache_dir / "metadata"

        # In-progress directories for atomic operations
        self.downloads_in_progress_dir = self.downloads_dir / ".in-progress"
        self.converted_in_progress_dir = self.converted_dir / ".in-progress"

        # Filename mapper for ASCII normalization
        self.filename_mapper = FilenameMapper(cache_dir / "filename_mapping.json")

        # Create directories
        self._create_directories()

        logger.info(
            f"CacheManager initialized with cache_dir={cache_dir}, "
            f"force_download={force_download}, "
            f"force_convert={force_convert}"
        )

    def _create_directories(self) -> None:
        """Create all necessary cache directories."""
        directories = [
            self.cache_dir,
            self.downloads_dir,
            self.converted_dir,
            self.metadata_dir,
            self.downloads_in_progress_dir,
            self.converted_in_progress_dir,
        ]

        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                logger.trace(  # type: ignore[attr-defined]
                    f"Created cache directory: {directory}"
                )
            except OSError as e:
                logger.error(f"Failed to create cache directory {directory}: {e}")
                raise RuntimeError(f"Failed to create cache directory: {e}")

        logger.debug("All cache directories created successfully")

    def get_download_cache_path(self, video_id: str, format_ext: str = "mp4") -> Path:
        """Get cache path for downloaded video file.

        Args:
            video_id: Video ID (used as cache key)
            format_ext: File extension for the video format

        Returns:
            Path to cached download file
        """
        cache_filename = f"{video_id}.{format_ext.lstrip('.')}"
        cache_path = self.downloads_dir / cache_filename

        logger.trace(  # type: ignore[attr-defined]
            f"Download cache path for {video_id}: {cache_path}"
        )
        return cache_path

    def get_converted_cache_path(self, video_id: str, format_ext: str = "mpg") -> Path:
        """Get cache path for converted video file.

        Args:
            video_id: Video ID (used as cache key)
            format_ext: File extension for the converted format

        Returns:
            Path to cached converted file
        """
        cache_filename = f"{video_id}.{format_ext.lstrip('.')}"
        cache_path = self.converted_dir / cache_filename

        logger.trace(  # type: ignore[attr-defined]
            f"Converted cache path for {video_id}: {cache_path}"
        )
        return cache_path

    def get_metadata_cache_path(self, video_id: str) -> Path:
        """Get cache path for video metadata file.

        Args:
            video_id: Video ID (used as cache key)

        Returns:
            Path to cached metadata file
        """
        cache_filename = f"{video_id}_metadata.json"
        cache_path = self.metadata_dir / cache_filename

        logger.trace(  # type: ignore[attr-defined]
            f"Metadata cache path for {video_id}: {cache_path}"
        )
        return cache_path

    def get_playlist_metadata_cache_path(self, playlist_id: str) -> Path:
        """Get cache path for playlist metadata file.

        Args:
            playlist_id: Playlist ID (used as cache key)

        Returns:
            Path to cached playlist metadata file
        """
        cache_filename = f"playlist_{playlist_id}_metadata.json"
        cache_path = self.metadata_dir / cache_filename

        logger.trace(  # type: ignore[attr-defined]
            f"Playlist metadata cache path for {playlist_id}: {cache_path}"
        )
        return cache_path

    def is_download_cached(self, video_id: str, format_ext: str = "mp4") -> bool:
        """Check if video download is cached and valid.

        Args:
            video_id: Video ID to check
            format_ext: Expected file extension

        Returns:
            True if valid cached download exists, False otherwise
        """
        if self.force_download:
            logger.debug(f"Forcing download for {video_id}, ignoring cache")
            return False

        cache_path = self.get_download_cache_path(video_id, format_ext)

        if not cache_path.exists():
            logger.trace(  # type: ignore[attr-defined]
                f"No download cache found for {video_id}"
            )
            return False

        # Check if file is currently being written (in-progress)
        in_progress_path = self.downloads_in_progress_dir / cache_path.name
        if in_progress_path.exists():
            logger.debug(
                f"Download for {video_id} is in progress, treating as not cached"
            )
            return False

        # Verify file integrity if metadata is available
        metadata_path = self.get_metadata_cache_path(video_id)
        if metadata_path.exists():
            try:
                with open(metadata_path, "r") as f:
                    metadata_data = json.load(f)

                expected_size = metadata_data.get("file_size")

                if expected_size is not None:
                    actual_size = cache_path.stat().st_size
                    if actual_size != expected_size:
                        logger.warning(
                            f"Download cache size mismatch for {video_id}: "
                            f"expected {expected_size}, actual {actual_size}"
                        )
                        return False

                # TODO: Implement checksum verification if needed
                # For now, size check is sufficient for most cases

            except (json.JSONDecodeError, OSError, KeyError) as e:
                logger.warning(
                    f"Failed to verify download cache integrity for {video_id}: {e}"
                )
                # Continue - file existence check passed

        logger.debug(f"Valid download cache found for {video_id}")
        return True

    def is_converted_cached(self, video_id: str, format_ext: str = "mpg") -> bool:
        """Check if video conversion is cached and valid.

        Args:
            video_id: Video ID to check
            format_ext: Expected converted file extension

        Returns:
            True if valid cached conversion exists, False otherwise
        """
        if self.force_convert:
            logger.debug(f"Forcing conversion for {video_id}, ignoring cache")
            return False

        cache_path = self.get_converted_cache_path(video_id, format_ext)

        if not cache_path.exists():
            logger.trace(  # type: ignore[attr-defined]
                f"No converted cache found for {video_id}"
            )
            return False

        # Check if file is currently being written (in-progress)
        in_progress_path = self.converted_in_progress_dir / cache_path.name
        if in_progress_path.exists():
            logger.debug(
                f"Conversion for {video_id} is in progress, treating as not cached"
            )
            return False

        logger.debug(f"Valid converted cache found for {video_id}")
        return True

    def store_download(
        self, video_id: str, source_path: Path, metadata: VideoMetadata
    ) -> VideoFile:
        """Store downloaded video file in cache atomically.

        Args:
            video_id: Video ID (cache key)
            source_path: Path to the downloaded file
            metadata: Video metadata

        Returns:
            VideoFile object representing the cached file

        Raises:
            RuntimeError: If caching operation fails
        """
        logger.info(f"Storing download cache for {video_id} from {source_path}")

        if not source_path.exists():
            logger.error(f"Source file does not exist: {source_path}")
            raise RuntimeError(f"Source file does not exist: {source_path}")

        # Determine format from source file
        format_ext = source_path.suffix.lstrip(".")
        cache_path = self.get_download_cache_path(video_id, format_ext)
        in_progress_path = self.downloads_in_progress_dir / cache_path.name

        try:
            # Atomic operation: copy to in-progress location first
            logger.trace(  # type: ignore[attr-defined]
                f"Copying {source_path} to in-progress location {in_progress_path}"
            )
            shutil.copy2(source_path, in_progress_path)

            # Verify file was copied correctly
            original_size = source_path.stat().st_size
            copied_size = in_progress_path.stat().st_size

            if original_size != copied_size:
                logger.error(
                    f"File copy verification failed: original {original_size} bytes, "
                    f"copied {copied_size} bytes"
                )
                raise RuntimeError("File copy verification failed")

            # Move to final location (atomic on most filesystems)
            logger.trace(  # type: ignore[attr-defined]
                f"Moving {in_progress_path} to final location {cache_path}"
            )
            shutil.move(str(in_progress_path), str(cache_path))

            # Calculate checksum and file size
            file_size = cache_path.stat().st_size
            checksum = self._calculate_file_checksum(cache_path)

            # Store metadata
            metadata_dict = {
                "video_id": metadata.video_id,
                "title": metadata.title,
                "duration": metadata.duration,
                "url": metadata.url,
                "thumbnail_url": metadata.thumbnail_url,
                "description": metadata.description,
                "file_size": file_size,
                "checksum": checksum,
                "format": format_ext,
                "cached_at": datetime.now().isoformat(),
            }

            metadata_path = self.get_metadata_cache_path(video_id)
            with open(metadata_path, "w") as f:
                json.dump(metadata_dict, f, indent=2)

            logger.debug(
                f"Successfully cached download for {video_id}: {file_size} bytes, "
                f"checksum {checksum[:8]}..."
            )

            return VideoFile(
                metadata=metadata,
                file_path=cache_path,
                file_size=file_size,
                checksum=checksum,
                format=format_ext,
            )

        except Exception as e:
            # Clean up in-progress file if it exists
            if in_progress_path.exists():
                try:
                    in_progress_path.unlink()
                    logger.trace(  # type: ignore[attr-defined]
                        f"Cleaned up in-progress file: {in_progress_path}"
                    )
                except OSError:
                    pass

            logger.error(f"Failed to store download cache for {video_id}: {e}")
            raise RuntimeError(f"Failed to store download cache: {e}")

    def store_converted(
        self, video_id: str, source_path: Path, original_metadata: VideoMetadata
    ) -> VideoFile:
        """Store converted video file in cache atomically.

        Args:
            video_id: Video ID (cache key)
            source_path: Path to the converted file
            original_metadata: Original video metadata

        Returns:
            VideoFile object representing the cached converted file

        Raises:
            RuntimeError: If caching operation fails
        """
        logger.info(f"Storing converted cache for {video_id} from {source_path}")

        if not source_path.exists():
            logger.error(f"Source file does not exist: {source_path}")
            raise RuntimeError(f"Source file does not exist: {source_path}")

        # Determine format from source file
        format_ext = source_path.suffix.lstrip(".")
        cache_path = self.get_converted_cache_path(video_id, format_ext)
        in_progress_path = self.converted_in_progress_dir / cache_path.name

        try:
            # Atomic operation: copy to in-progress location first
            logger.trace(  # type: ignore[attr-defined]
                f"Copying {source_path} to in-progress location {in_progress_path}"
            )
            shutil.copy2(source_path, in_progress_path)

            # Verify file was copied correctly
            original_size = source_path.stat().st_size
            copied_size = in_progress_path.stat().st_size

            if original_size != copied_size:
                logger.error(
                    f"File copy verification failed: original {original_size} bytes, "
                    f"copied {copied_size} bytes"
                )
                raise RuntimeError("File copy verification failed")

            # Move to final location (atomic on most filesystems)
            logger.trace(  # type: ignore[attr-defined]
                f"Moving {in_progress_path} to final location {cache_path}"
            )
            shutil.move(str(in_progress_path), str(cache_path))

            # Calculate checksum and file size
            file_size = cache_path.stat().st_size
            checksum = self._calculate_file_checksum(cache_path)

            logger.debug(
                f"Successfully cached converted file for {video_id}: "
                f"{file_size} bytes, checksum {checksum[:8]}..."
            )

            return VideoFile(
                metadata=original_metadata,
                file_path=cache_path,
                file_size=file_size,
                checksum=checksum,
                format=format_ext,
            )

        except Exception as e:
            # Clean up in-progress file if it exists
            if in_progress_path.exists():
                try:
                    in_progress_path.unlink()
                    logger.trace(  # type: ignore[attr-defined]
                        f"Cleaned up in-progress file: {in_progress_path}"
                    )
                except OSError:
                    pass

            logger.error(f"Failed to store converted cache for {video_id}: {e}")
            raise RuntimeError(f"Failed to store converted cache: {e}")

    def get_cached_download(
        self, video_id: str, format_ext: str = "mp4"
    ) -> Optional[VideoFile]:
        """Retrieve cached download file if available and valid.

        Args:
            video_id: Video ID to retrieve
            format_ext: Expected file extension

        Returns:
            VideoFile object if cached, None otherwise
        """
        if not self.is_download_cached(video_id, format_ext):
            return None

        cache_path = self.get_download_cache_path(video_id, format_ext)
        metadata_path = self.get_metadata_cache_path(video_id)

        try:
            # Load metadata
            with open(metadata_path, "r") as f:
                metadata_dict = json.load(f)

            metadata = VideoMetadata(
                video_id=metadata_dict["video_id"],
                title=metadata_dict["title"],
                duration=metadata_dict["duration"],
                url=metadata_dict["url"],
                thumbnail_url=metadata_dict.get("thumbnail_url"),
                description=metadata_dict.get("description"),
            )

            video_file = VideoFile(
                metadata=metadata,
                file_path=cache_path,
                file_size=metadata_dict["file_size"],
                checksum=metadata_dict["checksum"],
                format=metadata_dict["format"],
            )

            logger.debug(f"Retrieved cached download for {video_id}")
            return video_file

        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning(f"Failed to retrieve cached download for {video_id}: {e}")
            return None

    def get_cached_converted(
        self, video_id: str, format_ext: str = "mpg"
    ) -> Optional[VideoFile]:
        """Retrieve cached converted file if available and valid.

        Args:
            video_id: Video ID to retrieve
            format_ext: Expected converted file extension

        Returns:
            VideoFile object if cached, None otherwise
        """
        if not self.is_converted_cached(video_id, format_ext):
            return None

        cache_path = self.get_converted_cache_path(video_id, format_ext)

        # Get original metadata from download cache
        metadata_path = self.get_metadata_cache_path(video_id)
        if not metadata_path.exists():
            logger.warning(
                f"No metadata found for converted file {video_id}, cannot retrieve"
            )
            return None

        try:
            # Load metadata
            with open(metadata_path, "r") as f:
                metadata_dict = json.load(f)

            metadata = VideoMetadata(
                video_id=metadata_dict["video_id"],
                title=metadata_dict["title"],
                duration=metadata_dict["duration"],
                url=metadata_dict["url"],
                thumbnail_url=metadata_dict.get("thumbnail_url"),
                description=metadata_dict.get("description"),
            )

            # Calculate current file info
            file_size = cache_path.stat().st_size
            checksum = self._calculate_file_checksum(cache_path)

            video_file = VideoFile(
                metadata=metadata,
                file_path=cache_path,
                file_size=file_size,
                checksum=checksum,
                format=format_ext,
            )

            logger.debug(f"Retrieved cached converted file for {video_id}")
            return video_file

        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning(
                f"Failed to retrieve cached converted file for {video_id}: {e}"
            )
            return None

    def store_playlist_metadata(self, playlist_metadata: PlaylistMetadata) -> None:
        """Store playlist metadata in cache.

        Args:
            playlist_metadata: Playlist metadata to cache
        """
        logger.debug(f"Storing playlist metadata for {playlist_metadata.playlist_id}")

        metadata_dict = {
            "playlist_id": playlist_metadata.playlist_id,
            "title": playlist_metadata.title,
            "description": playlist_metadata.description,
            "video_count": playlist_metadata.video_count,
            "total_size_estimate": playlist_metadata.total_size_estimate,
            "cached_at": datetime.now().isoformat(),
        }

        cache_path = self.get_playlist_metadata_cache_path(
            playlist_metadata.playlist_id
        )

        try:
            with open(cache_path, "w") as f:
                json.dump(metadata_dict, f, indent=2)

            logger.debug(
                f"Successfully cached playlist metadata for "
                f"{playlist_metadata.playlist_id}"
            )
        except OSError as e:
            logger.error(f"Failed to store playlist metadata: {e}")
            raise RuntimeError(f"Failed to store playlist metadata: {e}")

    def get_cached_playlist_metadata(
        self, playlist_id: str
    ) -> Optional[PlaylistMetadata]:
        """Retrieve cached playlist metadata if available.

        Args:
            playlist_id: Playlist ID to retrieve

        Returns:
            PlaylistMetadata object if cached, None otherwise
        """
        cache_path = self.get_playlist_metadata_cache_path(playlist_id)

        if not cache_path.exists():
            logger.trace(  # type: ignore[attr-defined]
                f"No cached playlist metadata found for {playlist_id}"
            )
            return None

        try:
            with open(cache_path, "r") as f:
                metadata_dict = json.load(f)

            playlist_metadata = PlaylistMetadata(
                playlist_id=metadata_dict["playlist_id"],
                title=metadata_dict["title"],
                description=metadata_dict.get("description"),
                video_count=metadata_dict["video_count"],
                total_size_estimate=metadata_dict.get("total_size_estimate"),
            )

            logger.debug(f"Retrieved cached playlist metadata for {playlist_id}")
            return playlist_metadata

        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning(
                f"Failed to retrieve cached playlist metadata for {playlist_id}: {e}"
            )
            return None

    def get_normalized_filename(self, video_id: str, original_title: str) -> str:
        """Get normalized filename for a video using the filename mapper.

        Args:
            video_id: Video ID (cache key)
            original_title: Original video title

        Returns:
            Normalized ASCII filename
        """
        normalized = self.filename_mapper.get_normalized_filename(
            video_id, original_title
        )
        logger.trace(  # type: ignore[attr-defined]
            f"Normalized filename for {video_id}: {normalized}"
        )
        return normalized

    def save_filename_mapping(self) -> None:
        """Save filename mappings to disk."""
        logger.debug("Saving filename mappings")
        self.filename_mapper.save_mapping()

    def cleanup_cache(self, max_age_days: int = 30) -> None:
        """Clean up old cache files.

        Args:
            max_age_days: Maximum age in days for cache files
        """
        logger.info(f"Starting cache cleanup (max_age_days={max_age_days})")

        from datetime import timedelta

        cutoff_time = datetime.now() - timedelta(days=max_age_days)

        cleaned_files = 0
        total_size_freed = 0

        for cache_dir in [self.downloads_dir, self.converted_dir, self.metadata_dir]:
            for file_path in cache_dir.rglob("*"):
                if file_path.is_file() and not file_path.name.startswith("."):
                    try:
                        file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if file_time < cutoff_time:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            cleaned_files += 1
                            total_size_freed += file_size
                            logger.trace(  # type: ignore[attr-defined]
                                f"Cleaned up old cache file: {file_path}"
                            )
                    except OSError as e:
                        logger.warning(f"Failed to clean up {file_path}: {e}")

        logger.info(
            f"Cache cleanup completed: {cleaned_files} files removed, "
            f"{total_size_freed / (1024*1024):.1f} MB freed"
        )

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        stats = {
            "downloads_count": 0,
            "downloads_size": 0,
            "converted_count": 0,
            "converted_size": 0,
            "metadata_count": 0,
            "metadata_size": 0,
        }

        cache_dirs = [
            ("downloads", self.downloads_dir),
            ("converted", self.converted_dir),
            ("metadata", self.metadata_dir),
        ]

        for prefix, cache_dir in cache_dirs:
            if cache_dir.exists():
                for file_path in cache_dir.rglob("*"):
                    if file_path.is_file() and not file_path.name.startswith("."):
                        try:
                            file_size = file_path.stat().st_size
                            stats[f"{prefix}_count"] += 1
                            stats[f"{prefix}_size"] += file_size
                        except OSError:
                            pass

        logger.debug(f"Cache statistics: {stats}")
        return stats

    def _calculate_file_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum of a file.

        Args:
            file_path: Path to file to checksum

        Returns:
            Hexadecimal checksum string
        """
        import hashlib

        logger.trace(  # type: ignore[attr-defined]
            f"Calculating checksum for {file_path}"
        )

        sha256_hash = hashlib.sha256()

        try:
            with open(file_path, "rb") as f:
                # Read file in chunks to handle large files
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)

            checksum = sha256_hash.hexdigest()
            logger.trace(  # type: ignore[attr-defined]
                f"Checksum for {file_path}: {checksum[:8]}..."
            )
            return checksum

        except OSError as e:
            logger.error(f"Failed to calculate checksum for {file_path}: {e}")
            raise RuntimeError(f"Failed to calculate checksum: {e}")
