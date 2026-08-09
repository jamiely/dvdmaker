#!/usr/bin/env python3
"""DVD Maker CLI - Main entry point for the DVD Maker application.

This script orchestrates the complete workflow of converting YouTube playlists
or local videos into physical DVDs, processing them for DVD compatibility, and
authoring a complete DVD structure.
"""

import argparse
import hashlib
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
from .services.local_media import LocalMediaError, load_local_media
from .services.spumux_service import SpumuxService
from .services.tool_manager import ToolManager, ToolManagerError
from .utils.capacity import log_excluded_videos, select_videos_for_dvd_capacity
from .utils.logging import get_logger, operation_context, setup_logging
from .utils.time_format import format_duration_human_readable


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog="dvdmaker",
        description="Convert YouTube playlists or local videos into physical DVDs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --playlist-url "https://www.youtube.com/playlist?list=PLxxx"
  %(prog)s --playlist-url "PLxxx" --output-dir ./my-dvd
  %(prog)s --playlist-url "PLxxx" --iso --menu-title "My Collection"
  %(prog)s --input ./movie.mp4 --chapter-interval-minutes 10
  %(prog)s --input ./part1.mkv --input ./more-videos --no-ai-titles
        """,
    )

    # Main operation arguments (mutually exclusive)
    operation_group = parser.add_mutually_exclusive_group(required=True)
    operation_group.add_argument(
        "--playlist-url",
        help="YouTube playlist URL or playlist ID",
    )
    operation_group.add_argument(
        "--input",
        action="append",
        type=Path,
        metavar="PATH",
        help="Local video file or directory (repeat for more inputs)",
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
        help="Custom DVD menu title (default: playlist/local source title)",
    )
    parser.add_argument(
        "--menu-subtitle",
        help="Optional subtitle shown below the DVD menu title (default: empty)",
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
    autoplay_group = parser.add_mutually_exclusive_group()
    autoplay_group.add_argument(
        "--autoplay",
        dest="autoplay",
        action="store_true",
        default=None,
        help="Start playback when the disc is inserted (default)",
    )
    autoplay_group.add_argument(
        "--no-autoplay",
        dest="autoplay",
        action="store_false",
        help="Show the main menu when the disc is inserted",
    )
    parser.add_argument(
        "--chapter-interval-minutes",
        type=int,
        metavar="MINUTES",
        help=(
            "Override chapter spacing with 1-120 minutes within each source "
            "(one video over 10 minutes defaults to 10)"
        ),
    )
    parser.add_argument(
        "--no-ai-titles",
        action="store_true",
        default=None,
        help="Use local filename stems without Codex title cleanup",
    )

    # Cache behavior options
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Force re-download all video files and refresh playlist data, "
        "even if cached",
    )
    parser.add_argument(
        "--force-convert",
        action="store_true",
        help="Force re-conversion even if cached",
    )
    parser.add_argument(
        "--refresh-playlist",
        action="store_true",
        help="Refresh playlist data to detect newly added videos "
        "(without re-downloading existing videos)",
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

    chapter_interval = getattr(args, "chapter_interval_minutes", None)
    if chapter_interval is not None and not 1 <= chapter_interval <= 120:
        raise ValueError("Chapter interval must be between 1 and 120 minutes")

    # Validate playlist URL format when playlist mode is selected.
    if not getattr(args, "clean", None) and not getattr(args, "input", None):
        if not getattr(args, "playlist_url", None):
            raise ValueError("Playlist URL is required (or provide local --input)")

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
    if getattr(args, "menu_subtitle", None) is not None:
        updates["menu_subtitle"] = args.menu_subtitle
    if args.video_format:
        updates["video_format"] = args.video_format
    if args.aspect_ratio:
        updates["aspect_ratio"] = args.aspect_ratio
    if args.no_iso:
        updates["generate_iso"] = False
    if getattr(args, "autoplay", None) is not None:
        updates["autoplay"] = args.autoplay
    if getattr(args, "chapter_interval_minutes", None) is not None:
        updates["chapter_interval_minutes"] = args.chapter_interval_minutes
    if getattr(args, "no_ai_titles", None):
        updates["ai_titles"] = False

    # Cache settings
    if args.force_download:
        updates["force_download"] = True
    if args.force_convert:
        updates["force_convert"] = True
    if args.refresh_playlist:
        updates["refresh_playlist"] = True

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


def validate_tools(tool_manager: ToolManager, require_ytdlp: bool = True) -> bool:
    """Validate that all required tools are available."""
    logger = get_logger(__name__)

    with operation_context("tool_validation"):
        logger.debug("Validating required tools...")

        try:
            if require_ytdlp:
                # Playlist mode alone needs yt-dlp.
                update_success = tool_manager.check_and_update_ytdlp()
                if update_success:
                    logger.debug("yt-dlp update check completed successfully")
                else:
                    logger.warning(
                        "yt-dlp update check failed, but continuing with "
                        "existing version"
                    )

            if require_ytdlp:
                tools_available, missing_tools = tool_manager.ensure_tools_available()
            else:
                tools_available, missing_tools = tool_manager.ensure_tools_available(
                    require_ytdlp=False
                )

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

        local_inputs = getattr(args, "input", None)

        # DVD creation operation
        with operation_context(
            "dvd_creation",
            input_mode="local" if local_inputs else "playlist",
        ):
            start_time = time.time()
            if local_inputs:
                logger.info("Starting DVD creation from local media")
            else:
                logger.info("Starting DVD creation for playlist: %s", args.playlist_url)
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
            tools_valid = (
                validate_tools(tool_manager, require_ytdlp=False)
                if local_inputs
                else validate_tools(tool_manager)
            )
            if not tools_valid:
                logger.error("Tool validation failed - cannot proceed")
                return 1

            # Initialize remaining services
            converter = VideoConverter(
                settings=settings,
                tool_manager=tool_manager,
                cache_manager=cache_manager,
                progress_callback=progress_callback,
            )

            spumux_service = SpumuxService(
                settings=settings,
                tool_manager=tool_manager,
                cache_manager=cache_manager,
            )

            dvd_author = DVDAuthor(
                settings=settings,
                tool_manager=tool_manager,
                cache_manager=cache_manager,
                spumux_service=spumux_service,
                progress_callback=progress_callback,
            )

            # Execute source-specific first step.
            if local_inputs:
                logger.info("Step 1: Validating local media...")
                with operation_context("local_media_validation"):
                    local_media = load_local_media(
                        local_inputs,
                        tool_manager,
                        settings.cache_dir,
                        ai_titles=settings.ai_titles,
                    )
                    video_files = local_media.videos
                    default_menu_title = local_media.default_menu_title
                    identity = "".join(video.checksum for video in video_files)
                    source_id = (
                        f"local-{hashlib.sha256(identity.encode()).hexdigest()[:12]}"
                    )
                    logger.info("Validated %d local videos", len(video_files))
            else:
                downloader = VideoDownloader(
                    settings=settings,
                    cache_manager=cache_manager,
                    tool_manager=tool_manager,
                )
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
                    video_files = []
                    for video in playlist.get_available_videos():
                        cached_file = cache_manager.get_cached_download(video.video_id)
                        if cached_file:
                            video_files.append(cached_file)
                    default_menu_title = playlist.metadata.title
                    source_id = playlist.metadata.playlist_id

            logger.info("Step 2: Converting videos to DVD format...")
            with operation_context("video_conversion"):
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
                menu_title = settings.menu_title or default_menu_title

                authored_dvd = dvd_author.create_dvd_structure(
                    converted_videos=final_videos,
                    menu_title=menu_title,
                    output_dir=settings.output_dir,
                    playlist_id=source_id,
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

            summary_lines.append(f"Total processing time: {total_time_str}")

            # Handle ISO file path separately for logging vs display
            iso_summary_line = None
            if authored_dvd.iso_file:
                # For display: use relative path when possible
                iso_file_path = Path(authored_dvd.iso_file)
                try:
                    display_iso_path = iso_file_path.relative_to(Path.cwd())
                except ValueError:
                    # If path is not relative to cwd, show the full absolute path
                    display_iso_path = iso_file_path.resolve()

                iso_summary_line = f"ISO file: {display_iso_path}"
                summary_lines.append(iso_summary_line)

            # Log to file first (with absolute paths for ISO files)
            for line in summary_lines:
                if line == iso_summary_line and authored_dvd.iso_file:
                    # Log absolute path for ISO file
                    absolute_iso_path = Path(authored_dvd.iso_file).resolve()
                    logger.info(f"ISO file: {absolute_iso_path}")
                else:
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

    except (YtDlpError, LocalMediaError, VideoConverterError, DVDAuthorError) as e:
        logger = get_logger(__name__)
        logger.error(f"Operation failed: {e}")
        return 1

    except Exception as e:
        logger = get_logger(__name__)
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
