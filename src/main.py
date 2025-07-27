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

    # Required arguments
    parser.add_argument(
        "--playlist-url",
        required=True,
        help="YouTube playlist URL or playlist ID",
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

    # Validate playlist URL format
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

                logger.info(f"Converted {len(converted_videos)} videos successfully")

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
                    create_iso=settings.generate_iso,
                )

                logger.info(f"DVD structure created at: {authored_dvd.video_ts_dir}")
                if authored_dvd.iso_file:
                    logger.info(f"ISO image created at: {authored_dvd.iso_file}")

            # Report final metrics
            end_time = time.time()
            total_time = int(end_time - start_time)
            total_time_str = format_duration_human_readable(total_time)

            logger.info("=== DVD Creation Summary ===")
            logger.info(
                f"Total videos processed: {len(final_videos)} "
                f"(duration: {capacity_result.total_duration_human_readable})"
            )
            logger.info(f"Total size: {capacity_result.total_size_gb:.2f}GB")
            if capacity_result.has_exclusions:
                excluded_count = len(capacity_result.excluded_videos)
                logger.info(
                    f"Videos excluded: {excluded_count} "
                    f"({capacity_result.excluded_size_gb:.2f}GB)"
                )
            logger.info(f"Total processing time: {total_time_str}")
            logger.info("DVD creation completed successfully!")
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
