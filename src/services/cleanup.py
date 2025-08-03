"""Cache and output cleanup service for DVD Maker.

This module provides functionality to clean up various types of cached
and output data generated during DVD creation processes.
"""

import shutil
from pathlib import Path
from typing import Dict, List, Optional

from ..utils.logging import get_logger

logger = get_logger(__name__)


class CleanupStats:
    """Statistics for cleanup operations."""

    def __init__(self) -> None:
        """Initialize cleanup statistics."""
        self.files_removed = 0
        self.directories_removed = 0
        self.bytes_freed = 0
        self.errors = 0

    @property
    def total_items_removed(self) -> int:
        """Get total number of items (files + directories) removed."""
        return self.files_removed + self.directories_removed

    @property
    def size_freed_mb(self) -> float:
        """Get size freed in megabytes."""
        return self.bytes_freed / (1024 * 1024)

    @property
    def size_freed_gb(self) -> float:
        """Get size freed in gigabytes."""
        return self.bytes_freed / (1024 * 1024 * 1024)

    def __repr__(self) -> str:
        """String representation of cleanup stats."""
        return (
            f"CleanupStats(files={self.files_removed}, "
            f"dirs={self.directories_removed}, "
            f"bytes={self.bytes_freed}, errors={self.errors})"
        )


class CleanupManager:
    """Manages cleanup operations for DVD Maker cached and output data."""

    def __init__(
        self,
        cache_dir: Path,
        output_dir: Path,
        temp_dir: Optional[Path] = None,
    ) -> None:
        """Initialize the cleanup manager.

        Args:
            cache_dir: Base cache directory containing downloads/conversions
            output_dir: Base output directory containing DVD structures/ISOs
            temp_dir: Temporary directory (optional)
        """
        self.cache_dir = cache_dir
        self.output_dir = output_dir
        self.temp_dir = temp_dir

        logger.debug(
            f"CleanupManager initialized with cache_dir={cache_dir}, "
            f"output_dir={output_dir}, temp_dir={temp_dir}"
        )

    def clean_downloads(self, dry_run: bool = False) -> CleanupStats:
        """Clean downloaded video files from yt-dlp cache.

        Args:
            dry_run: If True, only report what would be cleaned without deletion

        Returns:
            CleanupStats with cleanup results
        """
        logger.info("Cleaning downloads cache...")
        stats = CleanupStats()

        downloads_dir = self.cache_dir / "downloads"
        if not downloads_dir.exists():
            logger.info("Downloads directory does not exist, nothing to clean")
            return stats

        # Clean video files but preserve .in-progress directory and metadata
        for item in downloads_dir.iterdir():
            if item.name.startswith("."):
                logger.debug(f"Skipping hidden item: {item}")
                continue

            if item.is_file():
                self._remove_item(item, stats, dry_run, "download file")

        logger.info(
            f"Downloads cleanup complete: {stats.files_removed} files, "
            f"{stats.size_freed_mb:.1f}MB freed"
        )
        return stats

    def clean_conversions(self, dry_run: bool = False) -> CleanupStats:
        """Clean converted video files from ffmpeg cache.

        Args:
            dry_run: If True, only report what would be cleaned without deletion

        Returns:
            CleanupStats with cleanup results
        """
        logger.info("Cleaning conversions cache...")
        stats = CleanupStats()

        converted_dir = self.cache_dir / "converted"
        if not converted_dir.exists():
            logger.info("Conversions directory does not exist, nothing to clean")
            return stats

        # Clean converted files and subdirectories, but preserve .in-progress items
        for item in converted_dir.iterdir():
            if item.name.startswith("."):
                logger.debug(f"Skipping hidden item: {item}")
                continue

            if item.is_file():
                # Direct files in converted directory (legacy structure)
                self._remove_item(item, stats, dry_run, "converted file")
            elif item.is_dir():
                # Video-specific subdirectories containing converted files
                # Each subdirectory contains {video_id}_dvd.mpg and {video_id}_thumb.jpg
                logger.debug(f"Cleaning converted subdirectory: {item}")
                for sub_item in item.iterdir():
                    if sub_item.is_file():
                        self._remove_item(sub_item, stats, dry_run, "converted file")

                # Remove empty subdirectory after cleaning files
                if not dry_run and item.exists():
                    try:
                        if not any(item.iterdir()):  # Directory is empty
                            item.rmdir()
                            stats.directories_removed += 1
                            logger.debug(
                                f"Removed empty converted subdirectory: {item}"
                            )
                    except OSError as e:
                        logger.warning(f"Failed to remove empty directory {item}: {e}")

        # Also clean metadata file if it exists
        metadata_file = converted_dir / "converted_metadata.json"
        if metadata_file.exists():
            self._remove_item(metadata_file, stats, dry_run, "converted metadata")

        logger.info(
            f"Conversions cleanup complete: {stats.files_removed} files, "
            f"{stats.directories_removed} directories, "
            f"{stats.size_freed_mb:.1f}MB freed"
        )
        return stats

    def clean_dvd_output(self, dry_run: bool = False) -> CleanupStats:
        """Clean DVD output directories (VIDEO_TS structures).

        Args:
            dry_run: If True, only report what would be cleaned without deletion

        Returns:
            CleanupStats with cleanup results
        """
        logger.info("Cleaning DVD output directories...")
        stats = CleanupStats()

        if not self.output_dir.exists():
            logger.info("Output directory does not exist, nothing to clean")
            return stats

        # Clean playlist-specific directories containing VIDEO_TS
        for item in self.output_dir.iterdir():
            if item.is_dir():
                video_ts_dir = item / "VIDEO_TS"
                if video_ts_dir.exists():
                    self._remove_item(
                        video_ts_dir, stats, dry_run, "VIDEO_TS directory"
                    )

        logger.info(
            f"DVD output cleanup complete: {stats.directories_removed} directories, "
            f"{stats.size_freed_mb:.1f}MB freed"
        )
        return stats

    def clean_isos(self, dry_run: bool = False) -> CleanupStats:
        """Clean ISO image files.

        Args:
            dry_run: If True, only report what would be cleaned without deletion

        Returns:
            CleanupStats with cleanup results
        """
        logger.info("Cleaning ISO files...")
        stats = CleanupStats()

        if not self.output_dir.exists():
            logger.info("Output directory does not exist, nothing to clean")
            return stats

        # Find and clean .iso files in output directory
        for item in self.output_dir.rglob("*.iso"):
            if item.is_file():
                self._remove_item(item, stats, dry_run, "ISO file")

        logger.info(
            f"ISO cleanup complete: {stats.files_removed} files, "
            f"{stats.size_freed_mb:.1f}MB freed"
        )
        return stats

    def clean_temp_files(self, dry_run: bool = False) -> CleanupStats:
        """Clean temporary files if temp directory is specified.

        Args:
            dry_run: If True, only report what would be cleaned without deletion

        Returns:
            CleanupStats with cleanup results
        """
        logger.info("Cleaning temporary files...")
        stats = CleanupStats()

        if not self.temp_dir or not self.temp_dir.exists():
            logger.info("Temp directory not specified or does not exist")
            return stats

        # Clean all contents of temp directory
        for item in self.temp_dir.iterdir():
            self._remove_item(item, stats, dry_run, "temp file/directory")

        logger.info(
            f"Temp cleanup complete: {stats.total_items_removed} items, "
            f"{stats.size_freed_mb:.1f}MB freed"
        )
        return stats

    def clean_all(self, dry_run: bool = False) -> Dict[str, CleanupStats]:
        """Clean all cached and output data.

        Args:
            dry_run: If True, only report what would be cleaned without deletion

        Returns:
            Dictionary mapping cleanup type to CleanupStats
        """
        logger.info("Starting comprehensive cleanup...")

        results = {
            "downloads": self.clean_downloads(dry_run),
            "conversions": self.clean_conversions(dry_run),
            "dvd_output": self.clean_dvd_output(dry_run),
            "isos": self.clean_isos(dry_run),
            "temp": self.clean_temp_files(dry_run),
        }

        # Calculate totals
        total_files = sum(stats.files_removed for stats in results.values())
        total_dirs = sum(stats.directories_removed for stats in results.values())
        total_bytes = sum(stats.bytes_freed for stats in results.values())
        total_errors = sum(stats.errors for stats in results.values())

        logger.info(
            f"Comprehensive cleanup complete: {total_files} files, "
            f"{total_dirs} directories, {total_bytes / (1024*1024):.1f}MB freed, "
            f"{total_errors} errors"
        )

        return results

    def get_cleanup_preview(self, cleanup_type: str) -> List[Path]:
        """Get a preview of items that would be cleaned without actually cleaning.

        Args:
            cleanup_type: Type of cleanup (downloads, conversions,
                          dvd-output, isos, all)

        Returns:
            List of paths that would be cleaned
        """
        preview_items = []

        if cleanup_type == "downloads":
            downloads_dir = self.cache_dir / "downloads"
            if downloads_dir.exists():
                for item in downloads_dir.iterdir():
                    if not item.name.startswith(".") and item.is_file():
                        preview_items.append(item)

        elif cleanup_type == "conversions":
            converted_dir = self.cache_dir / "converted"
            if converted_dir.exists():
                for item in converted_dir.iterdir():
                    if not item.name.startswith(".") and item.is_file():
                        preview_items.append(item)

        elif cleanup_type == "dvd-output":
            if self.output_dir.exists():
                for item in self.output_dir.iterdir():
                    if item.is_dir():
                        video_ts_dir = item / "VIDEO_TS"
                        if video_ts_dir.exists():
                            preview_items.append(video_ts_dir)

        elif cleanup_type == "isos":
            if self.output_dir.exists():
                for item in self.output_dir.rglob("*.iso"):
                    if item.is_file():
                        preview_items.append(item)

        elif cleanup_type == "all":
            # Combine all cleanup types
            for cleanup_subtype in ["downloads", "conversions", "dvd-output", "isos"]:
                preview_items.extend(self.get_cleanup_preview(cleanup_subtype))

        return preview_items

    def _remove_item(
        self, item: Path, stats: CleanupStats, dry_run: bool, item_type: str
    ) -> None:
        """Remove a file or directory and update statistics.

        Args:
            item: Path to remove
            stats: CleanupStats to update
            dry_run: If True, don't actually remove the item
            item_type: Human-readable description of item type for logging
        """
        try:
            # Calculate size before removal
            if item.is_file():
                size = item.stat().st_size
            else:
                size = self._calculate_directory_size(item)

            if dry_run:
                logger.info(f"Would remove {item_type}: {item} ({size} bytes)")
            else:
                logger.debug(f"Removing {item_type}: {item}")

                if item.is_file():
                    item.unlink()
                    stats.files_removed += 1
                else:
                    shutil.rmtree(item)
                    stats.directories_removed += 1

                logger.trace(  # type: ignore[attr-defined]
                    f"Removed {item_type}: {item}"
                )

            stats.bytes_freed += size

        except OSError as e:
            logger.warning(f"Failed to remove {item_type} {item}: {e}")
            stats.errors += 1

    def _calculate_directory_size(self, directory: Path) -> int:
        """Calculate total size of a directory recursively.

        Args:
            directory: Directory to calculate size for

        Returns:
            Total size in bytes
        """
        total_size = 0
        try:
            for item in directory.rglob("*"):
                if item.is_file():
                    try:
                        total_size += item.stat().st_size
                    except OSError:
                        pass  # Skip files we can't stat
        except OSError:
            pass  # Skip if directory can't be read

        return total_size
