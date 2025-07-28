#!/usr/bin/env python3
"""DVD Maker CLI - Main entry point for the DVD Maker application.

This script orchestrates the complete workflow of converting YouTube playlists
into physical DVDs by downloading videos, processing them for DVD compatibility,
and authoring a complete DVD structure.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from .config.settings import Settings, load_settings
from .services.cache_manager import CacheManager
from .services.cleanup import CleanupManager
from .services.converter import VideoConverter, VideoConverterError
from .services.downloader import VideoDownloader, YtDlpError
from .services.dvd_author import DVDAuthor, DVDAuthorError
from .services.tool_manager import ToolManager, ToolManagerError
from .utils.capacity import log_excluded_videos, select_videos_for_dvd_capacity
from .utils.logging import get_logger, operation_context, setup_logging
from .utils.time_format import format_duration_human_readable


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog="dvdmaker",
        description="Convert YouTube playlists into physical DVDs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --playlist-url "https://www.youtube.com/playlist?list=PLxxx"
  %(prog)s --playlist-url "PLxxx" --output-dir ./my-dvd
  %(prog)s --playlist-url "PLxxx" --iso --menu-title "My Collection"
        """,
    )

    # Main operation arguments (mutually exclusive)
    operation_group = parser.add_mutually_exclusive_group(required=True)
    operation_group.add_argument(
        "--playlist-url",
        help="YouTube playlist URL or playlist ID",
    )
    operation_group.add_argument(
        "--clean",
        choices=["downloads", "conversions", "dvd-output", "isos", "all"],
        help="Clean specific data type: downloads (yt-dlp cache), "
        "conversions (ffmpeg cache), dvd-output (VIDEO_TS dirs), "
        "isos (ISO files), or all",
    )

    # Directory options
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for DVD files (default: ./output)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="Cache directory for downloaded/processed files (default: ./cache)",
    )
    parser.add_argument(
        "--temp-dir",
        type=Path,
        help="Temporary files directory (default: ./temp)",
    )

    # Video quality and format options
    parser.add_argument(
        "--quality",
        default="best",
        help="Video quality preference (default: best)",
    )

    # DVD options
    parser.add_argument(
        "--menu-title",
        help="Custom DVD menu title (default: playlist title)",
    )
    parser.add_argument(
        "--video-format",
        choices=["NTSC", "PAL"],
        default="NTSC",
        help="DVD video format: NTSC (29.97fps, 720x480) or PAL (25fps, 720x576) "
        "(default: NTSC)",
    )
    parser.add_argument(
        "--aspect-ratio",
        choices=["4:3", "16:9"],
        default="16:9",
        help="DVD aspect ratio: 4:3 (standard) or 16:9 (widescreen) (default: 16:9)",
    )
    parser.add_argument(
        "--no-iso",
        action="store_true",
        help="Skip ISO image generation (ISO creation is enabled by default)",
    )

    # Cache behavior options
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Force re-download even if cached",
    )
    parser.add_argument(
        "--force-convert",
        action="store_true",
        help="Force re-conversion even if cached",
    )

    # Tool management options
    parser.add_argument(
        "--download-tools",
        action="store_true",
        help="Download required tools to local bin directory",
    )
    parser.add_argument(
        "--use-system-tools",
        action="store_true",
        help="Use system-installed tools instead of local bin",
    )

    # Logging options
    parser.add_argument(
        "--log-level",
        choices=["TRACE", "DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging level (default: INFO)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Specify log file path (default: logs/dvdmaker.log)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose console output (equivalent to --log-level DEBUG)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all console output except errors",
    )

    # Configuration file option
    parser.add_argument(
        "--config",
        type=Path,
        help="Configuration file path",
    )

    return parser


def validate_arguments(args: argparse.Namespace) -> None:
    """Validate command line arguments."""
    # Check for conflicting flags
    if args.quiet and args.verbose:
        raise ValueError("Cannot use both --quiet and --verbose flags")

    if args.use_system_tools and args.download_tools:
        raise ValueError(
            "Cannot use both --use-system-tools and --download-tools flags"
        )

    # Validate playlist URL format (only when not using --clean)
    if not hasattr(args, "clean") or not args.clean:
        if not args.playlist_url:
            raise ValueError("Playlist URL is required")

        # Basic URL/ID validation
        playlist_input = args.playlist_url.strip()
        if not (
            playlist_input.startswith("http")
            or playlist_input.startswith("PL")
            or len(playlist_input) >= 10
        ):
            raise ValueError(
                "Invalid playlist URL or ID. Expected a YouTube playlist URL or ID"
            )


def merge_settings_with_args(args: argparse.Namespace, settings: Settings) -> Settings:
    """Merge command line arguments with settings."""
    # Override settings with command line arguments where provided
    updates = {}

    # Directory settings
    if args.output_dir:
        updates["output_dir"] = args.output_dir
    if args.cache_dir:
        updates["cache_dir"] = args.cache_dir
    if args.temp_dir:
        updates["temp_dir"] = args.temp_dir

    # Video settings
    if args.quality:
        updates["video_quality"] = args.quality

    # DVD settings
    if args.menu_title:
        updates["menu_title"] = args.menu_title
    if args.video_format:
        updates["video_format"] = args.video_format
    if args.aspect_ratio:
        updates["aspect_ratio"] = args.aspect_ratio
    if args.no_iso:
        updates["generate_iso"] = False

    # Cache settings
    if args.force_download:
        updates["force_download"] = True
    if args.force_convert:
        updates["force_convert"] = True

    # Tool settings
    if args.use_system_tools:
        updates["use_system_tools"] = True
        updates["download_tools"] = False
    if args.download_tools:
        updates["download_tools"] = True
        updates["use_system_tools"] = False

    # Logging settings
    if args.log_level:
        updates["log_level"] = args.log_level
    if args.verbose:
        updates["verbose"] = True
    if args.quiet:
        updates["quiet"] = True

    # Create new settings with updates
    current_dict = settings.model_dump()
    current_dict.update(updates)

    return Settings(**current_dict)


def setup_application_logging(
    settings: Settings, log_file: Optional[Path] = None
) -> None:
    """Set up application logging based on settings."""
    if log_file:
        log_path = log_file
    else:
        log_path = settings.log_dir / "dvdmaker.log"

    setup_logging(
        log_dir=settings.log_dir,
        log_level=settings.get_effective_log_level(),
        log_file=log_path.name if log_path else "dvdmaker.log",
        max_file_size=settings.log_file_max_size,
        backup_count=settings.log_file_backup_count,
        console_output=not settings.quiet,
    )


def create_progress_callback(
    quiet: bool = False,
) -> Optional[Callable[[str, float], None]]:
    """Create a progress callback for console output."""
    if quiet:
        return None

    def simple_callback(operation: str, progress: float) -> None:
        """Simple progress callback for console output."""
        if progress >= 0:
            print(f"\r{operation}: {progress:.1f}%", end="", flush=True)
        else:
            print(f"\n{operation}")

    return simple_callback


def validate_tools(tool_manager: ToolManager) -> bool:
    """Validate that all required tools are available."""
    logger = get_logger(__name__)

    with operation_context("tool_validation"):
        logger.debug("Validating required tools...")

        try:
            # Check for yt-dlp updates first (before ensuring tools are available)
            update_success = tool_manager.check_and_update_ytdlp()
            if update_success:
                logger.debug("yt-dlp update check completed successfully")
            else:
                logger.warning(
                    "yt-dlp update check failed, but continuing with existing version"
                )

            tools_available, missing_tools = tool_manager.ensure_tools_available()

            if not tools_available:
                logger.error(f"Missing required tools: {', '.join(missing_tools)}")
                for tool in missing_tools:
                    if tool == "dvdauthor":
                        logger.error(
                            "dvdauthor must be installed manually. "
                            "On macOS: 'brew install dvdauthor', "
                            "On Ubuntu/Debian: 'sudo apt install dvdauthor'"
                        )
                return False

            logger.debug("All required tools are available")
            return True

        except ToolManagerError as e:
            logger.error(f"Tool validation failed: {e}")
            return False


def perform_cleanup(cleanup_type: str, settings: Settings) -> int:
    """Perform cleanup operations.

    Args:
        cleanup_type: Type of cleanup to perform
        settings: Application settings

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    logger = get_logger(__name__)

    try:
        cleanup_manager = CleanupManager(
            cache_dir=settings.cache_dir,
            output_dir=settings.output_dir,
            temp_dir=settings.temp_dir,
        )

        # Get preview of items to be cleaned
        items_to_clean = cleanup_manager.get_cleanup_preview(cleanup_type)

        if not items_to_clean:
            print(f"No {cleanup_type} data found to clean.")
            logger.info(f"No {cleanup_type} data found to clean")
            return 0

        # Show what will be cleaned
        print(f"\n=== {cleanup_type.title()} Cleanup Preview ===")
        print(f"The following {len(items_to_clean)} items will be removed:")

        for item in items_to_clean[:10]:  # Show first 10 items
            print(f"  - {item}")

        if len(items_to_clean) > 10:
            print(f"  ... and {len(items_to_clean) - 10} more items")

        # Ask for confirmation
        response = (
            input(f"\nProceed with {cleanup_type} cleanup? [y/N]: ").strip().lower()
        )
        if response not in ("y", "yes"):
            print("Cleanup cancelled.")
            logger.info("Cleanup cancelled by user")
            return 0

        # Perform cleanup
        print(f"\nCleaning {cleanup_type}...")
        logger.info(f"Starting {cleanup_type} cleanup")

        if cleanup_type == "downloads":
            stats = cleanup_manager.clean_downloads()
        elif cleanup_type == "conversions":
            stats = cleanup_manager.clean_conversions()
        elif cleanup_type == "dvd-output":
            stats = cleanup_manager.clean_dvd_output()
        elif cleanup_type == "isos":
            stats = cleanup_manager.clean_isos()
        elif cleanup_type == "all":
            results = cleanup_manager.clean_all()
            # Calculate totals
            total_files = sum(stats.files_removed for stats in results.values())
            total_dirs = sum(stats.directories_removed for stats in results.values())
            total_size_mb = sum(stats.size_freed_mb for stats in results.values())
            total_errors = sum(stats.errors for stats in results.values())

            print("\n=== Cleanup Complete ===")
            print(f"Files removed: {total_files}")
            print(f"Directories removed: {total_dirs}")
            print(f"Space freed: {total_size_mb:.1f} MB")
            if total_errors > 0:
                print(f"Errors encountered: {total_errors}")

            logger.info(
                f"Comprehensive cleanup complete: {total_files} files, "
                f"{total_dirs} directories, {total_size_mb:.1f}MB freed"
            )
            return 0
        else:
            logger.error(f"Unknown cleanup type: {cleanup_type}")
            return 1

        # Display results for single cleanup type
        print("\n=== Cleanup Complete ===")
        print(f"Files removed: {stats.files_removed}")
        print(f"Directories removed: {stats.directories_removed}")
        print(f"Space freed: {stats.size_freed_mb:.1f} MB")
        if stats.errors > 0:
            print(f"Errors encountered: {stats.errors}")

        logger.info(
            f"{cleanup_type} cleanup complete: "
            f"{stats.total_items_removed} items, {stats.size_freed_mb:.1f}MB freed"
        )
        return 0

    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        print(f"Error: Cleanup failed - {e}")
        return 1


def main() -> int:
    """Main entry point for the DVD Maker CLI."""
    try:
        # Parse command line arguments
        parser = create_argument_parser()
        args = parser.parse_args()

        # Validate arguments
        validate_arguments(args)

        # Load configuration
        settings = load_settings(args.config if hasattr(args, "config") else None)

        # Merge CLI arguments with settings
        settings = merge_settings_with_args(args, settings)

        # Set up logging
        setup_application_logging(settings, getattr(args, "log_file", None))

        logger = get_logger(__name__)

        # Branch between cleanup and DVD creation operations
        if hasattr(args, "clean") and args.clean:
            # Handle cleanup operation
            return perform_cleanup(args.clean, settings)

        # DVD creation operation
        with operation_context("dvd_creation", playlist_url=args.playlist_url):
            start_time = time.time()
            logger.info(f"Starting DVD creation for playlist: {args.playlist_url}")
            logger.debug(f"Output directory: {settings.output_dir}")

            # Create necessary directories
            settings.create_directories()

            # Create progress callback (disabled for now due to type mismatch)
            progress_callback = None

            # Initialize services with dependency injection
            cache_manager = CacheManager(
                cache_dir=settings.cache_dir,
                force_download=settings.force_download,
                force_convert=settings.force_convert,
            )

            tool_manager = ToolManager(
                settings=settings,
                progress_callback=progress_callback,
            )

            # Validate tools first
            if not validate_tools(tool_manager):
                logger.error("Tool validation failed - cannot proceed")
                return 1

            # Initialize remaining services
            downloader = VideoDownloader(
                settings=settings,
                cache_manager=cache_manager,
                tool_manager=tool_manager,
            )

            converter = VideoConverter(
                settings=settings,
                tool_manager=tool_manager,
                cache_manager=cache_manager,
                progress_callback=progress_callback,
            )

            dvd_author = DVDAuthor(
                settings=settings,
                tool_manager=tool_manager,
                cache_manager=cache_manager,
                progress_callback=progress_callback,
            )

            # Execute main workflow
            logger.info("Step 1: Downloading playlist...")
            with operation_context("playlist_download"):
                playlist = downloader.download_playlist(
                    args.playlist_url, progress_callback
                )

                if not playlist.get_available_videos():
                    logger.error("No videos available for download")
                    return 1

                available_count = len(playlist.get_available_videos())
                total_duration = playlist.total_duration_human_readable
                logger.info(
                    f"Downloaded {available_count} videos successfully "
                    f"(total duration: {total_duration})"
                )

            logger.info("Step 2: Converting videos to DVD format...")
            with operation_context("video_conversion"):
                # Get downloaded video files from cache
                video_files = []
                for video in playlist.get_available_videos():
                    cached_file = cache_manager.get_cached_download(video.video_id)
                    if cached_file:
                        video_files.append(cached_file)

                if not video_files:
                    logger.error("No video files available for conversion")
                    return 1

                converted_videos = converter.convert_videos(
                    video_files, force_convert=settings.force_convert
                )

                if not converted_videos:
                    logger.error("No videos were successfully converted")
                    return 1

                logger.debug(f"Converted {len(converted_videos)} videos successfully")

            logger.info("Step 2.5: Checking DVD capacity...")
            with operation_context("capacity_check"):
                # Check if all videos fit on DVD, exclude excess if necessary
                capacity_result = select_videos_for_dvd_capacity(converted_videos)

                if capacity_result.has_exclusions:
                    excluded_count = len(capacity_result.excluded_videos)
                    logger.warning(
                        f"DVD capacity exceeded! {excluded_count} videos will be "
                        f"excluded to fit on a standard 4.7GB DVD."
                    )
                    log_excluded_videos(capacity_result.excluded_videos)

                final_videos = capacity_result.included_videos

                if not final_videos:
                    logger.error("No videos fit on DVD after capacity check")
                    return 1

                logger.debug(
                    f"Using {len(final_videos)} videos for DVD "
                    f"({capacity_result.total_size_gb:.2f}GB)"
                )

            logger.info("Step 3: Creating DVD structure...")
            with operation_context("dvd_authoring"):
                menu_title = settings.menu_title or playlist.metadata.title

                authored_dvd = dvd_author.create_dvd_structure(
                    converted_videos=final_videos,
                    menu_title=menu_title,
                    output_dir=settings.output_dir,
                    playlist_id=playlist.metadata.playlist_id,
                    create_iso=settings.generate_iso,
                )

                logger.debug(f"DVD structure created at: {authored_dvd.video_ts_dir}")
                if authored_dvd.iso_file:
                    logger.debug(f"ISO image created at: {authored_dvd.iso_file}")

            # Report final metrics
            end_time = time.time()
            total_time = int(end_time - start_time)
            total_time_str = format_duration_human_readable(total_time)

            # Display summary to both log and stdout
            summary_lines = [
                "=== DVD Creation Summary ===",
                f"Total videos processed: {len(final_videos)} "
                f"(duration: {capacity_result.total_duration_human_readable})",
                f"Total size: {capacity_result.total_size_gb:.2f}GB",
            ]

            if capacity_result.has_exclusions:
                excluded_count = len(capacity_result.excluded_videos)
                summary_lines.append(
                    f"Videos excluded: {excluded_count} "
                    f"({capacity_result.excluded_size_gb:.2f}GB)"
                )

            # Convert absolute paths to relative paths for cleaner output
            try:
                dvd_path = authored_dvd.video_ts_dir.relative_to(Path.cwd())
            except ValueError:
                # If path is not relative to cwd, just use the directory name
                dvd_path = authored_dvd.video_ts_dir.name

            summary_lines.extend(
                [
                    f"Total processing time: {total_time_str}",
                    f"DVD structure: {dvd_path}",
                ]
            )

            if authored_dvd.iso_file:
                try:
                    iso_path = authored_dvd.iso_file.relative_to(Path.cwd())
                except ValueError:
                    # If path is not relative to cwd, just use the filename
                    iso_path = authored_dvd.iso_file.name
                summary_lines.append(f"ISO file: {iso_path}")

            # Log to file first
            for line in summary_lines:
                logger.info(line)

            # Then print summary to stdout (after logging is complete)
            print()  # Add spacing
            for line in summary_lines:
                print(line)

            return 0

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 130

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    except (YtDlpError, VideoConverterError, DVDAuthorError) as e:
        logger = get_logger(__name__)
        logger.error(f"Operation failed: {e}")
        return 1

    except Exception as e:
        logger = get_logger(__name__)
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
