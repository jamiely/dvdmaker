"""DVD authoring service for DVD Maker.

This module handles creating DVD structures using dvdauthor, including:
- Creating VIDEO_TS directory structure
- Generating DVD menus
- Handling multiple videos as chapters in a single title
- ASCII filename normalization for DVD compatibility
- DVD capacity validation and warnings
"""

import hashlib
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from PIL import Image, ImageDraw, ImageFont, ImageStat

from ..config.settings import Settings
from ..exceptions import DVDMakerError
from ..models.dvd import DVDChapter, DVDStructure
from ..models.video import VideoFile, VideoMetadata
from ..services.cache_manager import CacheManager
from ..services.converter import ConvertedVideoFile
from ..services.spumux_service import ButtonConfig, SpumuxService
from ..services.tool_manager import ToolManager
from ..utils.filename import normalize_to_ascii
from ..utils.logging import get_logger
from ..utils.time_format import format_duration_human_readable
from .base import BaseService

# Progress callback type
ProgressCallback = Callable[[str, float], None]

DEFAULT_SINGLE_VIDEO_CHAPTER_INTERVAL_MINUTES = 10
CHAPTER_MENU_MIN_MARKERS = 3
CHAPTERS_PER_MENU_PAGE = 6
MAX_PROGRAMS_PER_TITLE_PGC = 255
CHAPTER_MENU_STYLE_VERSION = "2"


def generate_chapter_offsets(
    duration_seconds: int, interval_minutes: Optional[int]
) -> Tuple[int, ...]:
    """Generate independent, strictly in-source chapter offsets."""
    if not interval_minutes or duration_seconds <= 0:
        return (0,)
    interval_seconds = interval_minutes * 60
    return tuple(range(0, duration_seconds, interval_seconds)) or (0,)


def format_chapter_timestamp(seconds: int) -> str:
    """Format a deterministic dvdauthor chapter timestamp."""
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def minimum_interval_for_program_limit(
    durations: Sequence[int], maximum_programs: int = MAX_PROGRAMS_PER_TITLE_PGC
) -> Optional[int]:
    """Find the smallest whole-minute interval that fits one title PGC."""
    for interval_minutes in range(1, 121):
        interval_seconds = interval_minutes * 60
        marker_count = sum(
            max(1, (max(0, duration) + interval_seconds - 1) // interval_seconds)
            for duration in durations
        )
        if marker_count <= maximum_programs:
            return interval_minutes
    return None


@dataclass(frozen=True)
class ChapterMenuEntry:
    """One selectable chapter marker and its source-local thumbnail location."""

    chapter_number: int
    source_index: int
    source_offset: int
    chapter_end: int
    source_duration: int
    source_video: Path
    source_title: str
    source_checksum: str


class DVDAuthorError(DVDMakerError):
    """Base exception for DVD authoring errors."""

    pass


class DVDAuthoringError(DVDAuthorError):
    """Exception raised when DVD authoring fails."""

    pass


class DVDCapacityExceededError(DVDAuthorError):
    """Exception raised when DVD capacity is exceeded."""

    pass


class DVDStructureCreationError(DVDAuthorError):
    """Exception raised when DVD structure creation fails."""

    pass


class AuthoredDVD:
    """Represents a completed DVD with VIDEO_TS structure."""

    def __init__(
        self,
        dvd_structure: DVDStructure,
        video_ts_dir: Path,
        iso_file: Optional[Path] = None,
        creation_time: float = 0.0,
    ):
        """Initialize authored DVD.

        Args:
            dvd_structure: The DVD structure that was authored
            video_ts_dir: Path to VIDEO_TS directory
            iso_file: Optional path to ISO file
            creation_time: Time taken to create DVD in seconds
        """
        self.dvd_structure = dvd_structure
        self.video_ts_dir = video_ts_dir
        self.iso_file = iso_file
        self.creation_time = creation_time
        self.logger = get_logger(__name__)

    @property
    def exists(self) -> bool:
        """Check if the VIDEO_TS directory exists."""
        return (
            self.video_ts_dir.exists() and (self.video_ts_dir / "VIDEO_TS.IFO").exists()
        )

    @property
    def has_iso(self) -> bool:
        """Check if ISO file exists."""
        return self.iso_file is not None and self.iso_file.exists()

    @property
    def size_gb(self) -> float:
        """Get total size in GB."""
        return self.dvd_structure.size_gb

    def validate_structure(self) -> bool:
        """Validate the DVD structure is complete.

        Returns:
            True if structure is valid, False otherwise
        """
        # Check for any VTS (Video Title Set) files - these are the core content
        vts_ifo_files = list(self.video_ts_dir.glob("VTS_*_0.IFO"))
        if not vts_ifo_files:
            self.logger.error("No VTS IFO files found")
            return False

        # Check for corresponding BUP files for each VTS
        for ifo_file in vts_ifo_files:
            bup_file = ifo_file.with_suffix(".BUP")
            if not bup_file.exists():
                self.logger.error(f"Missing corresponding BUP file: {bup_file.name}")
                return False

        # Check for VTS VOB files (at least one should exist)
        vob_files = list(self.video_ts_dir.glob("VTS_*_*.VOB"))
        if not vob_files:
            self.logger.error("No VTS VOB files found")
            return False

        self.logger.debug(
            f"DVD structure validation passed: {len(vts_ifo_files)} VTS sets, "
            f"{len(vob_files)} VOB files found"
        )
        return True


class DVDAuthor(BaseService):
    """Creates DVD structures using dvdauthor.

    This class handles:
    - Creating DVD menu structures
    - Generating VIDEO_TS directory structure
    - Converting multiple videos into chapters of a single title
    - ASCII filename normalization for DVD compatibility
    - DVD capacity validation and warnings
    - Optional ISO image generation
    """

    # DVD capacity limits
    DVD_CAPACITY_GB = 4.7  # Single layer DVD capacity
    DVD_CAPACITY_BYTES = int(DVD_CAPACITY_GB * 1024 * 1024 * 1024)

    def __init__(
        self,
        settings: Settings,
        tool_manager: ToolManager,
        cache_manager: CacheManager,
        spumux_service: Optional[SpumuxService] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        """Initialize the DVD author.

        Args:
            settings: Application settings
            tool_manager: Tool manager for dvdauthor access
            cache_manager: Cache manager for caching operations
            spumux_service: Optional spumux service for button overlays
            progress_callback: Optional callback for progress reporting
        """
        super().__init__(settings)
        self.tool_manager = tool_manager
        self.cache_manager = cache_manager
        self.spumux_service = spumux_service
        self.progress_callback = progress_callback
        self._menu_button_configs: Dict[Path, Tuple[ButtonConfig, ...]] = {}

    def _create_playlist_output_dir(
        self, base_output_dir: Path, playlist_id: str
    ) -> Path:
        """Create playlist-specific output directory for concurrent execution safety.

        Args:
            base_output_dir: Base output directory
            playlist_id: Playlist ID to use for directory naming

        Returns:
            Path to playlist-specific output directory

        Raises:
            DVDAuthoringError: If directory creation fails
        """
        # Sanitize playlist ID for directory name
        safe_playlist_id = normalize_to_ascii(playlist_id)
        # Remove any remaining unsafe characters
        import re

        safe_playlist_id = re.sub(r'[<>:"/\\|?*\s]', "_", safe_playlist_id)
        safe_playlist_id = safe_playlist_id.strip("_.- ")

        if not safe_playlist_id:
            safe_playlist_id = "unknown_playlist"

        playlist_output_dir = base_output_dir / safe_playlist_id

        try:
            # Create playlist-specific directory
            playlist_output_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(
                f"Created playlist output directory: {playlist_output_dir}"
            )
            return playlist_output_dir

        except OSError as e:
            self.logger.error(
                f"Failed to create playlist output directory {playlist_output_dir}: {e}"
            )
            raise DVDAuthoringError(f"Failed to create output directory: {e}") from e

    def _report_progress(self, message: str, progress: float) -> None:
        """Report progress if callback is available.

        Args:
            message: Progress message
            progress: Progress value (0.0 to 1.0)
        """
        if self.progress_callback:
            self.progress_callback(message, progress)
        self.logger.debug(f"DVD Author Progress: {message} ({progress:.1%})")

    def create_dvd_structure(
        self,
        converted_videos: List[ConvertedVideoFile],
        menu_title: str,
        output_dir: Path,
        playlist_id: str,
        create_iso: bool = False,
    ) -> AuthoredDVD:
        """Create DVD structure from converted videos.

        Args:
            converted_videos: List of converted video files
            menu_title: Title for the DVD menu
            output_dir: Base output directory
            playlist_id: Playlist ID for creating specific output directory
            create_iso: Whether to create an ISO file

        Returns:
            AuthoredDVD object with completed structure

        Raises:
            DVDAuthoringError: If DVD authoring fails
            DVDCapacityExceededError: If videos exceed DVD capacity
        """
        # Create playlist-specific output directory
        playlist_output_dir = self._create_playlist_output_dir(output_dir, playlist_id)

        self.logger.debug(
            f"Creating DVD structure with {len(converted_videos)} videos: "
            f"'{menu_title}' in {playlist_output_dir}"
        )
        self._report_progress("Preparing DVD structure", 0.0)

        if not converted_videos:
            raise DVDAuthoringError("No videos provided for DVD creation")

        # Create DVD chapters from converted videos
        chapters = self._create_chapters(converted_videos)
        marker_count = sum(len(chapter.chapter_offsets) for chapter in chapters)
        self.logger.info(
            "Prepared %d source videos with %d authored DVD chapter markers",
            len(chapters),
            marker_count,
        )
        if marker_count > MAX_PROGRAMS_PER_TITLE_PGC:
            minimum_interval = minimum_interval_for_program_limit(
                [chapter.duration for chapter in chapters]
            )
            if minimum_interval is None:
                suggestion = "split the inputs across multiple discs"
            else:
                suggestion = (
                    f"use --chapter-interval-minutes {minimum_interval} or greater"
                )
            raise DVDAuthoringError(
                f"{marker_count} chapter markers exceed the DVD title limit of "
                f"{MAX_PROGRAMS_PER_TITLE_PGC}; {suggestion}"
            )
        total_size = sum(video.file_size for video in converted_videos)

        # Check DVD capacity
        dvd_structure = DVDStructure(
            chapters=chapters,
            menu_title=normalize_to_ascii(menu_title),
            total_size=total_size,
        )

        if not dvd_structure.fits_on_dvd(self.DVD_CAPACITY_GB):
            self.logger.warning(
                f"DVD capacity exceeded: {dvd_structure.size_gb:.2f}GB > "
                f"{self.DVD_CAPACITY_GB}GB"
            )
            # Don't raise exception - create DVD with available videos
            self.logger.warning("Continuing with DVD creation despite capacity warning")

        # Create output directory structure within playlist directory
        video_ts_dir = playlist_output_dir / "VIDEO_TS"
        audio_ts_dir = playlist_output_dir / "AUDIO_TS"

        # Clean existing directories
        import shutil

        if video_ts_dir.exists():
            shutil.rmtree(video_ts_dir)
        if audio_ts_dir.exists():
            shutil.rmtree(audio_ts_dir)

        video_ts_dir.mkdir(parents=True, exist_ok=True)
        audio_ts_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Create DVD authoring XML
            self._report_progress("Creating DVD authoring configuration", 0.2)
            dvd_xml = self._create_dvd_xml(dvd_structure, video_ts_dir)

            # Create button overlays for menu videos
            self._report_progress("Creating button overlays for menu videos", 0.3)
            self._create_button_overlays(playlist_output_dir)

            # Run dvdauthor
            self._report_progress("Running dvdauthor", 0.4)
            creation_time = self._run_dvdauthor(dvd_xml, video_ts_dir)

            # Validate created structure
            self._report_progress("Validating DVD structure", 0.8)
            authored_dvd = AuthoredDVD(
                dvd_structure=dvd_structure,
                video_ts_dir=video_ts_dir,
                creation_time=creation_time,
            )

            if not authored_dvd.validate_structure():
                raise DVDStructureCreationError("Created DVD structure is invalid")

            # Create ISO if requested
            iso_file = None
            if create_iso:
                self._report_progress("Creating ISO image", 0.9)
                iso_file = self._create_iso(
                    playlist_output_dir, video_ts_dir, menu_title
                )
                authored_dvd.iso_file = iso_file

            # Skip cleanup of temporary menu files for debugging
            # self._cleanup_temp_menu_files(playlist_output_dir)

            self._report_progress("DVD creation complete", 1.0)
            self.logger.info(
                f"DVD creation completed successfully: {authored_dvd.size_gb:.2f}GB, "
                f"{len(chapters)} sources, {marker_count} chapter markers"
            )

            return authored_dvd

        except DVDStructureCreationError:
            # Re-raise validation errors as-is for more specific error handling
            raise
        except Exception as e:
            self.logger.error(f"DVD authoring failed: {e}")
            raise DVDAuthoringError(f"Failed to create DVD structure: {e}") from e

    def _create_chapters(
        self, converted_videos: List[ConvertedVideoFile]
    ) -> List[DVDChapter]:
        """Create DVD chapters from converted videos.

        Args:
            converted_videos: List of converted video files

        Returns:
            List of DVD chapters ordered by original playlist position
        """
        self.logger.debug(f"Creating DVD chapters from {len(converted_videos)} videos")

        chapters = []
        current_time = 0
        chapter_interval = self.settings.chapter_interval_minutes
        if (
            chapter_interval is None
            and len(converted_videos) == 1
            and converted_videos[0].duration
            > DEFAULT_SINGLE_VIDEO_CHAPTER_INTERVAL_MINUTES * 60
        ):
            chapter_interval = DEFAULT_SINGLE_VIDEO_CHAPTER_INTERVAL_MINUTES
            self.logger.info(
                "Using automatic %d-minute chapters for the single long video",
                chapter_interval,
            )

        for i, video in enumerate(converted_videos, 1):
            # Create updated metadata with actual converted video duration
            updated_metadata = VideoMetadata(
                video_id=video.metadata.video_id,
                title=video.metadata.title,
                duration=video.duration,  # Use converted video duration
                url=video.metadata.url,
                thumbnail_url=video.metadata.thumbnail_url,
                description=video.metadata.description,
            )

            # Create VideoFile from ConvertedVideoFile
            video_file = VideoFile(
                metadata=updated_metadata,
                file_path=video.video_file,
                file_size=video.file_size,
                checksum=video.checksum,
                format="mpeg2",  # DVD format
            )

            chapter = DVDChapter(
                chapter_number=i,
                video_file=video_file,
                start_time=current_time,
                chapter_offsets=generate_chapter_offsets(
                    video.duration, chapter_interval
                ),
            )

            chapters.append(chapter)
            current_time += (
                chapter.duration
            )  # Use chapter.duration instead of video.duration

            duration_str = format_duration_human_readable(chapter.duration)
            start_time_str = format_duration_human_readable(chapter.start_time)
            self.logger.debug(
                f"Created chapter {i}: {video.metadata.title} "
                f"({duration_str}, starts at {start_time_str})"
            )

        total_duration_str = format_duration_human_readable(current_time)
        self.logger.debug(
            f"Created {len(chapters)} chapters with total duration {total_duration_str}"
        )
        return chapters

    def _create_menu_video(
        self,
        source_video: Path,
        output_path: Path,
        duration: float = 1.0,
        aspect_ratio: Optional[str] = None,
        is_vmgm: bool = True,
        show_chapter_selection: bool = True,
        menu_title: str = "DVD",
    ) -> None:
        """Render the static main menu and encode it as a DVD menu MPEG."""
        del source_video, duration
        width, height = self._menu_dimensions()
        still_path = output_path.with_suffix(".png")
        image = Image.new("RGB", (width, height), (12, 18, 30))
        draw = ImageDraw.Draw(image)
        title_font = self._load_menu_font(self._scale_y(34), bold=True)
        button_font = self._load_menu_font(self._scale_y(24), bold=True)
        subtitle_font = self._load_menu_font(self._scale_y(16))
        title = self._ellipsize(draw, menu_title, title_font, 560)
        title_box = draw.textbbox((0, 0), title, font=title_font)
        draw.text(
            ((width - (title_box[2] - title_box[0])) // 2, self._scale_y(78)),
            title,
            font=title_font,
            fill=(245, 248, 255),
        )
        draw.text(
            (self._scale_x(100), self._scale_y(155)),
            "DVD Video",
            font=subtitle_font,
            fill=(135, 158, 190),
        )
        configs = self._main_menu_buttons(show_chapter_selection)
        for config in configs:
            draw.rounded_rectangle(
                (config.x0, config.y0, config.x1, config.y1),
                radius=self._scale_y(8),
                fill=(25, 38, 59),
                outline=(67, 91, 128),
                width=2,
            )
            draw.text(
                (config.x0 + 14, config.y0 + self._scale_y(4)),
                config.text,
                font=button_font,
                fill=(245, 248, 255),
            )
        if not is_vmgm:
            self.logger.debug("Rendered legacy titleset menu through main-menu path")
        image.save(still_path, "PNG")
        self._encode_menu_still(
            still_path, output_path, aspect_ratio or self.settings.aspect_ratio
        )

    def _main_menu_buttons(
        self, show_chapter_selection: bool
    ) -> Tuple[ButtonConfig, ...]:
        """Return visible main-menu buttons and their remote navigation."""
        play_down = "button02" if show_chapter_selection else "button01"
        buttons = [
            ButtonConfig(
                "button01",
                "Play all",
                (self._scale_x(210), self._scale_y(286)),
                (self._scale_x(220), self._scale_y(40)),
                "g0=1;jump title 1;",
                down=play_down,
            )
        ]
        if show_chapter_selection:
            buttons.append(
                ButtonConfig(
                    "button02",
                    "Select chapter",
                    (self._scale_x(210), self._scale_y(342)),
                    (self._scale_x(260), self._scale_y(40)),
                    "g0=0;jump titleset 1 menu entry ptt;",
                    up="button01",
                )
            )
        return tuple(buttons)

    @staticmethod
    def _flatten_chapter_menu_entries(
        chapters: Sequence[DVDChapter],
    ) -> List[ChapterMenuEntry]:
        """Map every source-local marker to its global DVD chapter number."""
        entries: List[ChapterMenuEntry] = []
        chapter_number = 1
        for source_index, chapter in enumerate(chapters, 1):
            for offset_index, source_offset in enumerate(chapter.chapter_offsets):
                chapter_end = (
                    chapter.chapter_offsets[offset_index + 1]
                    if offset_index + 1 < len(chapter.chapter_offsets)
                    else chapter.duration
                )
                entries.append(
                    ChapterMenuEntry(
                        chapter_number=chapter_number,
                        source_index=source_index,
                        source_offset=source_offset,
                        chapter_end=chapter_end,
                        source_duration=chapter.duration,
                        source_video=chapter.video_file.file_path,
                        source_title=chapter.title,
                        source_checksum=chapter.video_file.checksum,
                    )
                )
                chapter_number += 1
        return entries

    @staticmethod
    def _paginate_chapter_entries(
        entries: Sequence[ChapterMenuEntry],
    ) -> List[Tuple[ChapterMenuEntry, ...]]:
        return [
            tuple(entries[index : index + CHAPTERS_PER_MENU_PAGE])
            for index in range(0, len(entries), CHAPTERS_PER_MENU_PAGE)
        ]

    def _chapter_page_buttons(
        self,
        entries: Sequence[ChapterMenuEntry],
        page_number: int,
        page_count: int,
    ) -> Tuple[ButtonConfig, ...]:
        """Build a six-item grid plus Back/Previous/Next controls."""
        configs: List[ButtonConfig] = []
        entry_count = len(entries)
        for index, entry in enumerate(entries):
            row, column = divmod(index, 3)
            name = f"button{index + 1:02d}"
            left = f"button{index:02d}" if column > 0 else name
            right = (
                f"button{index + 2:02d}"
                if column < 2 and index + 1 < entry_count
                else name
            )
            up = f"button{index - 2:02d}" if row > 0 else name
            down_index = index + 3
            down = (
                f"button{down_index + 1:02d}"
                if down_index < entry_count
                else "button07"
            )
            cell_left = 65 + column * 205
            cell_top = 82 + row * 150
            configs.append(
                ButtonConfig(
                    name,
                    f"Chapter {entry.chapter_number}",
                    (self._scale_x(cell_left + 90), self._scale_y(cell_top + 65)),
                    (self._scale_x(180), self._scale_y(130)),
                    f"g0=0;jump title 1 chapter {entry.chapter_number};",
                    left=left,
                    right=right,
                    up=up,
                    down=down,
                )
            )

        bottom_y = self._scale_y(423)
        last_grid = f"button{entry_count:02d}"
        nav_right = (
            "button08"
            if page_number > 1
            else ("button09" if page_number < page_count else last_grid)
        )
        configs.append(
            ButtonConfig(
                "button07",
                "Back to menu",
                (self._scale_x(120), bottom_y),
                (self._scale_x(180), self._scale_y(38)),
                "g0=0;jump vmgm menu 1;",
                right=nav_right,
                up=last_grid,
            )
        )
        if page_number > 1:
            configs.append(
                ButtonConfig(
                    "button08",
                    "← Previous",
                    (self._scale_x(340), bottom_y),
                    (self._scale_x(170), self._scale_y(38)),
                    f"g0=0;jump menu {page_number};",
                    left="button07",
                    right="button09" if page_number < page_count else "button08",
                    up=last_grid,
                )
            )
        if page_number < page_count:
            configs.append(
                ButtonConfig(
                    "button09",
                    "Next →",
                    (self._scale_x(570), bottom_y),
                    (self._scale_x(170), self._scale_y(38)),
                    f"g0=0;jump menu {page_number + 2};",
                    left="button08" if page_number > 1 else "button07",
                    up=last_grid,
                )
            )
        return tuple(configs)

    def _create_chapter_menu_video(
        self,
        entries: Sequence[ChapterMenuEntry],
        page_number: int,
        page_count: int,
        menu_title: str,
        output_path: Path,
        multiple_sources: bool,
    ) -> Tuple[ButtonConfig, ...]:
        """Render a 3x2 thumbnail page and encode it as a menu MPEG."""
        width, height = self._menu_dimensions()
        image = Image.new("RGB", (width, height), (12, 18, 30))
        draw = ImageDraw.Draw(image)
        title_font = self._load_menu_font(self._scale_y(25), bold=True)
        label_font = self._load_menu_font(self._scale_y(15), bold=True)
        small_font = self._load_menu_font(self._scale_y(12))
        nav_font = self._load_menu_font(self._scale_y(16), bold=True)
        page_title = f"{menu_title} — Chapters {page_number}/{page_count}"
        page_title = self._ellipsize(draw, page_title, title_font, 630)
        draw.text(
            (self._scale_x(55), self._scale_y(28)),
            page_title,
            font=title_font,
            fill=(245, 248, 255),
        )
        configs = self._chapter_page_buttons(entries, page_number, page_count)
        for index, entry in enumerate(entries):
            row, column = divmod(index, 3)
            cell_left = self._scale_x(65 + column * 205)
            cell_top = self._scale_y(82 + row * 150)
            thumb_width = self._scale_x(180)
            thumb_height = self._scale_y(96)
            thumbnail = self._chapter_thumbnail(entry, thumb_width, thumb_height)
            with Image.open(thumbnail) as source_image:
                image.paste(source_image.convert("RGB"), (cell_left, cell_top))
            draw.rectangle(
                (
                    cell_left,
                    cell_top,
                    cell_left + thumb_width - 1,
                    cell_top + thumb_height - 1,
                ),
                outline=(75, 94, 122),
                width=2,
            )
            label = f"Chapter {entry.chapter_number}"
            if multiple_sources:
                label = self._ellipsize(draw, entry.source_title, label_font, 178)
            draw.text(
                (cell_left + 2, cell_top + thumb_height + self._scale_y(3)),
                label,
                font=label_font,
                fill=(245, 248, 255),
            )
            timestamp = self._menu_timestamp(entry.source_offset)
            if multiple_sources:
                timestamp = f"Chapter {entry.chapter_number}  •  {timestamp}"
            draw.text(
                (cell_left + 2, cell_top + thumb_height + self._scale_y(21)),
                timestamp,
                font=small_font,
                fill=(150, 170, 198),
            )
        for config in configs[len(entries) :]:
            draw.rounded_rectangle(
                (config.x0, config.y0, config.x1, config.y1),
                radius=self._scale_y(6),
                fill=(25, 38, 59),
                outline=(67, 91, 128),
                width=2,
            )
            draw.text(
                (config.x0 + 10, config.y0 + self._scale_y(6)),
                config.text,
                font=nav_font,
                fill=(245, 248, 255),
            )
        still_path = output_path.with_suffix(".png")
        image.save(still_path, "PNG")
        self._encode_menu_still(still_path, output_path, self.settings.aspect_ratio)
        return configs

    def _chapter_thumbnail(
        self, entry: ChapterMenuEntry, width: int, height: int
    ) -> Path:
        """Extract and cache a frame one second after a chapter boundary."""
        identity = "|".join(
            (
                CHAPTER_MENU_STYLE_VERSION,
                entry.source_checksum,
                str(entry.source_offset),
                str(width),
                str(height),
                self.settings.video_format,
                self.settings.aspect_ratio,
            )
        )
        asset_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        thumbnail_dir = self.cache_manager.cache_dir / "menu_assets" / "thumbnails"
        thumbnail_dir.mkdir(parents=True, exist_ok=True)
        thumbnail_path = thumbnail_dir / f"{asset_key}.png"
        if thumbnail_path.exists() and thumbnail_path.stat().st_size > 0:
            return thumbnail_path
        ffmpeg_cmd = self.tool_manager.get_tool_command("ffmpeg")
        filter_chain = (
            "scale='trunc(iw*sar/2)*2':ih,setsar=1,"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
        )
        maximum_seek = max(entry.source_offset, entry.chapter_end - 1)
        candidates = tuple(
            dict.fromkeys(
                min(entry.source_offset + delta, maximum_seek)
                for delta in (1, 3, 5, 10)
            )
        )
        last_error: Optional[Exception] = None
        for seek_seconds in candidates:
            command = ffmpeg_cmd + [
                "-ss",
                str(seek_seconds),
                "-i",
                str(entry.source_video),
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-vf",
                filter_chain,
                "-y",
                str(thumbnail_path),
            ]
            try:
                subprocess.run(command, capture_output=True, text=True, check=True)
                if thumbnail_path.exists() and thumbnail_path.stat().st_size > 0:
                    if self._thumbnail_has_picture(thumbnail_path):
                        return thumbnail_path
            except (OSError, subprocess.CalledProcessError) as exc:
                last_error = exc
        if thumbnail_path.exists() and thumbnail_path.stat().st_size > 0:
            return thumbnail_path
        if last_error:
            self.logger.warning(
                "Could not extract thumbnail for chapter %d: %s",
                entry.chapter_number,
                last_error,
            )
        placeholder = Image.new("RGB", (width, height), (28, 39, 56))
        placeholder_draw = ImageDraw.Draw(placeholder)
        placeholder_font = self._load_menu_font(max(12, self._scale_y(18)), bold=True)
        placeholder_draw.text(
            (width // 2, height // 2),
            self._menu_timestamp(entry.source_offset),
            anchor="mm",
            font=placeholder_font,
            fill=(190, 205, 226),
        )
        placeholder.save(thumbnail_path, "PNG")
        return thumbnail_path

    @staticmethod
    def _thumbnail_has_picture(thumbnail_path: Path) -> bool:
        """Reject effectively black frames so an early chapter retry can be used."""
        with Image.open(thumbnail_path) as image:
            luminance = ImageStat.Stat(image.convert("L")).mean[0]
        return luminance >= 12

    def _encode_menu_still(
        self, still_path: Path, output_path: Path, aspect_ratio: str
    ) -> None:
        """Encode a rendered still with silent AC-3 as a compliant menu MPEG."""
        ffmpeg_cmd = self.tool_manager.get_tool_command("ffmpeg")
        is_ntsc = self.settings.video_format == "NTSC"
        framerate = "30000/1001" if is_ntsc else "25"
        gop = "18" if is_ntsc else "15"
        command = ffmpeg_cmd + [
            "-loop",
            "1",
            "-framerate",
            framerate,
            "-i",
            str(still_path),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            "1",
            "-c:v",
            "mpeg2video",
            "-pix_fmt",
            "yuv420p",
            "-r",
            framerate,
            "-g",
            gop,
            "-b:v",
            "6000k",
            "-maxrate",
            "9000k",
            "-bufsize",
            "1835008",
            "-c:a",
            "ac3",
            "-ar",
            "48000",
            "-b:a",
            "192k",
            "-muxrate",
            "10080k",
            "-packetsize",
            "2048",
            "-aspect",
            aspect_ratio,
            "-shortest",
            "-f",
            "dvd",
            "-y",
            str(output_path),
        ]
        try:
            subprocess.run(command, capture_output=True, text=True, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise DVDAuthoringError(
                f"Failed to encode DVD menu {output_path.name}: {exc}"
            ) from exc

    def _menu_dimensions(self) -> Tuple[int, int]:
        return (720, 480 if self.settings.video_format == "NTSC" else 576)

    @staticmethod
    def _scale_x(value: int) -> int:
        return value

    def _scale_y(self, value: int) -> int:
        return value if self.settings.video_format == "NTSC" else round(value * 1.2)

    @staticmethod
    def _load_menu_font(
        size: int, bold: bool = False
    ) -> Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]:
        candidates = [
            (
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                if bold
                else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            ),
            (
                "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
                if bold
                else "/usr/share/fonts/TTF/DejaVuSans.ttf"
            ),
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        return ImageFont.load_default()

    @staticmethod
    def _ellipsize(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: Union[ImageFont.FreeTypeFont, ImageFont.ImageFont],
        maximum_width: int,
    ) -> str:
        if draw.textlength(text, font=font) <= maximum_width:
            return text
        shortened = text
        while shortened and draw.textlength(f"{shortened}…", font=font) > maximum_width:
            shortened = shortened[:-1]
        return f"{shortened}…" if shortened else "…"

    @staticmethod
    def _menu_timestamp(seconds: int) -> str:
        hours, remainder = divmod(max(0, seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def _create_black_menu_video(
        self, output_path: Path, duration: float = 0.5, aspect_ratio: str = ""
    ) -> None:
        """Create a black menu video as fallback."""
        try:
            ffmpeg_cmd = self.tool_manager.get_tool_command("ffmpeg")

            # Create black video
            cmd = ffmpeg_cmd + [
                "-f",
                "lavfi",
                "-i",
                f"color=black:size=720x480:duration={duration}:rate=29.97",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-c:v",
                "mpeg2video",
                "-c:a",
                "ac3",
                "-b:v",
                "8000k",
                "-b:a",
                "192k",
                "-aspect",
                aspect_ratio if aspect_ratio else self.settings.aspect_ratio,
                "-t",
                str(duration),
                "-f",
                "dvd",
                "-y",
                str(output_path),
            ]

            subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.logger.debug(f"Created fallback black menu video: {output_path.name}")

        except Exception as e:
            self.logger.error(f"Failed to create fallback menu video: {e}")

    def _create_button_overlays(self, playlist_output_dir: Path) -> None:
        """Create every registered hotspot, failing before authoring dead menus."""
        if not self._menu_button_configs:
            self.logger.debug("No interactive menu videos were registered")
            return
        if not self.spumux_service:
            raise DVDAuthoringError(
                "Spumux service is required for interactive DVD menus"
            )

        self.logger.info(
            "Creating button overlays for %d menu video(s)",
            len(self._menu_button_configs),
        )
        for menu_file, configs in self._menu_button_configs.items():
            overlay = self.spumux_service.create_button_overlay(
                menu_file,
                playlist_output_dir,
                button_configs=configs,
                asset_key=menu_file.stem,
                strict=True,
            )
            if not overlay:
                raise DVDAuthoringError(
                    f"Failed to create interactive buttons for {menu_file.name}"
                )

    def _cleanup_temp_menu_files(self, playlist_output_dir: Path) -> None:
        """Clean up temporary menu files after DVD creation."""
        temp_dir = self.cache_manager.cache_dir / "temp_menus"
        if temp_dir.exists():
            try:
                import shutil

                shutil.rmtree(temp_dir)
                self.logger.debug("Cleaned up temporary menu files")
            except Exception as e:
                self.logger.warning(f"Failed to clean up temporary menu files: {e}")

    def _create_dvd_xml(self, dvd_structure: DVDStructure, video_ts_dir: Path) -> Path:
        """Create autoplay plus a paginated thumbnail chapter browser."""
        self.logger.debug(f"Creating dvdauthor XML for '{dvd_structure.menu_title}'")
        dvdauthor = ET.Element("dvdauthor", dest=str(video_ts_dir))
        video_format = self.settings.video_format.lower()
        aspect_ratio = self.settings.aspect_ratio
        chapters = dvd_structure.get_chapters_ordered()
        entries = self._flatten_chapter_menu_entries(chapters)
        show_chapter_menu = len(entries) >= CHAPTER_MENU_MIN_MARKERS
        pages = self._paginate_chapter_entries(entries) if show_chapter_menu else []
        temp_dir = self.cache_manager.cache_dir / "temp_menus"
        temp_dir.mkdir(parents=True, exist_ok=True)
        self._menu_button_configs = {}

        vmgm = ET.SubElement(dvdauthor, "vmgm")
        if self.settings.autoplay:
            ET.SubElement(vmgm, "fpc").text = "g0=1;jump title 1;"
        vmgm_menus = ET.SubElement(vmgm, "menus")
        self._add_menu_media_declarations(vmgm_menus, video_format, aspect_ratio)
        main_pgc = ET.SubElement(vmgm_menus, "pgc", entry="title")
        main_file = temp_dir / "menu0-0.mpg"
        self._create_menu_video(
            chapters[0].video_file.file_path,
            main_file,
            aspect_ratio=aspect_ratio,
            is_vmgm=True,
            show_chapter_selection=show_chapter_menu,
            menu_title=dvd_structure.menu_title,
        )
        main_buttons = self._main_menu_buttons(show_chapter_menu)
        for button in main_buttons:
            ET.SubElement(main_pgc, "button", name=button.name).text = (
                button.navigation_command
            )
        ET.SubElement(main_pgc, "vob", file=str(main_file), pause="inf")
        self._menu_button_configs[main_file] = main_buttons

        titleset = ET.SubElement(dvdauthor, "titleset")
        titleset_menus = ET.SubElement(titleset, "menus")
        self._add_menu_media_declarations(titleset_menus, video_format, aspect_ratio)
        root_pgc = ET.SubElement(titleset_menus, "pgc", entry="root")
        ET.SubElement(root_pgc, "pre").text = "jump vmgm menu 1;"

        multiple_sources = len(chapters) > 1
        for page_number, page_entries in enumerate(pages, 1):
            if page_number == 1:
                page_pgc = ET.SubElement(titleset_menus, "pgc", entry="ptt")
            else:
                page_pgc = ET.SubElement(titleset_menus, "pgc")
            menu_file = temp_dir / f"menu1-{page_number - 1}.mpg"
            page_buttons = self._create_chapter_menu_video(
                page_entries,
                page_number,
                len(pages),
                dvd_structure.menu_title,
                menu_file,
                multiple_sources,
            )
            for button in page_buttons:
                ET.SubElement(page_pgc, "button", name=button.name).text = (
                    button.navigation_command
                )
            ET.SubElement(page_pgc, "vob", file=str(menu_file), pause="inf")
            self._menu_button_configs[menu_file] = page_buttons

        titles = ET.SubElement(titleset, "titles")
        if aspect_ratio == "16:9":
            ET.SubElement(
                titles,
                "video",
                format=video_format,
                aspect=aspect_ratio,
                widescreen="nopanscan",
            )
        else:
            ET.SubElement(titles, "video", format=video_format, aspect=aspect_ratio)
        ET.SubElement(titles, "audio", lang="EN")
        title_pgc = ET.SubElement(titles, "pgc")
        for chapter in chapters:
            normalized_path = self._normalize_video_path(chapter.video_file.file_path)
            chapter_times = (
                "0:00"
                if chapter.chapter_offsets == (0,)
                else ",".join(
                    format_chapter_timestamp(offset)
                    for offset in chapter.chapter_offsets
                )
            )
            ET.SubElement(
                title_pgc,
                "vob",
                file=str(normalized_path),
                chapters=chapter_times,
            )
        ET.SubElement(title_pgc, "post").text = "call menu entry root;"

        cache_dir = self.cache_manager.cache_dir / "build"
        cache_dir.mkdir(parents=True, exist_ok=True)
        xml_file = cache_dir / "dvd_structure.xml"
        import xml.dom.minidom

        rough_string = ET.tostring(dvdauthor, encoding="utf-8")
        pretty_xml = xml.dom.minidom.parseString(rough_string).toprettyxml(
            indent="  ", encoding="utf-8"
        )
        with open(xml_file, "wb") as output_file:
            output_file.write(pretty_xml)
        self.logger.info(
            "Generated %d chapter-menu page(s) for %d marker(s)",
            len(pages),
            len(entries),
        )
        return xml_file

    @staticmethod
    def _add_menu_media_declarations(
        menus: ET.Element, video_format: str, aspect_ratio: str
    ) -> None:
        """Declare identical video/audio/subpicture mappings for a menu domain."""
        if aspect_ratio == "16:9":
            ET.SubElement(
                menus,
                "video",
                format=video_format,
                aspect=aspect_ratio,
                widescreen="nopanscan",
            )
        else:
            ET.SubElement(menus, "video", format=video_format, aspect=aspect_ratio)
        ET.SubElement(menus, "audio", lang="EN")
        subpicture = ET.SubElement(menus, "subpicture", lang="EN")
        ET.SubElement(
            subpicture,
            "stream",
            id="0",
            mode="widescreen" if aspect_ratio == "16:9" else "normal",
        )
        if aspect_ratio == "16:9":
            ET.SubElement(subpicture, "stream", id="1", mode="letterbox")

    def _normalize_video_path(self, video_path: Path) -> Path:
        """Normalize video file path for DVD compatibility.

        Args:
            video_path: Original video file path

        Returns:
            Normalized path with ASCII-safe filename
        """
        # Get ASCII-safe filename
        ascii_filename = normalize_to_ascii(video_path.name)

        if ascii_filename == video_path.name:
            return video_path

        # Never write beside a local source. Use an identity-specific cache
        # directory so equally named sources from different locations cannot
        # collide.
        path_identity = hashlib.sha256(
            str(video_path.resolve()).encode("utf-8")
        ).hexdigest()[:12]
        normalized_dir = (
            self.cache_manager.cache_dir / "normalized_videos" / path_identity
        )
        normalized_dir.mkdir(parents=True, exist_ok=True)
        normalized_path = normalized_dir / ascii_filename

        if not normalized_path.exists():
            self.logger.debug(
                f"Copying video for ASCII compatibility: {ascii_filename}"
            )
            import shutil

            shutil.copy2(video_path, normalized_path)

        return normalized_path

    def _run_dvdauthor(self, xml_file: Path, video_ts_dir: Path) -> float:
        """Run dvdauthor to create DVD structure.

        Args:
            xml_file: Path to dvdauthor XML configuration
            video_ts_dir: VIDEO_TS directory path

        Returns:
            Time taken to create DVD in seconds

        Raises:
            DVDAuthoringError: If dvdauthor execution fails
        """
        self.logger.debug("Running dvdauthor to create DVD structure")

        try:
            dvdauthor_cmd = self.tool_manager.get_tool_command("dvdauthor")
        except Exception as e:
            raise DVDAuthoringError(
                "dvdauthor not found. Please install dvdauthor:\n"
                "  macOS: brew install dvdauthor\n"
                "  Ubuntu/Debian: sudo apt install dvdauthor\n"
                "  RHEL/CentOS: sudo yum install dvdauthor"
            ) from e

        # Use the parent directory of VIDEO_TS as the output directory
        output_dir = video_ts_dir.parent
        cmd = dvdauthor_cmd + ["-o", str(output_dir), "-x", str(xml_file)]

        self.logger.debug(f"Executing dvdauthor command: {' '.join(cmd)}")

        import time

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                cwd=video_ts_dir.parent,
            )

            end_time = time.time()
            creation_time = end_time - start_time

            self.logger.debug(
                f"dvdauthor completed successfully in {creation_time:.1f}s"
            )
            self.logger.debug(f"dvdauthor stdout: {result.stdout}")

            if result.stderr:
                self.logger.debug(f"dvdauthor stderr: {result.stderr}")

            return creation_time

        except subprocess.CalledProcessError as e:
            self.logger.error(f"dvdauthor failed with exit code {e.returncode}")
            self.logger.error(f"dvdauthor stdout: {e.stdout}")
            self.logger.error(f"dvdauthor stderr: {e.stderr}")
            raise DVDAuthoringError(
                f"dvdauthor execution failed: {e.stderr or e.stdout}"
            ) from e

    def _create_iso(
        self, output_dir: Path, video_ts_dir: Path, title: str = "dvd"
    ) -> Path:
        """Create ISO image from VIDEO_TS directory.

        Args:
            output_dir: Output directory for ISO file
            video_ts_dir: VIDEO_TS directory to create ISO from
            title: Title to use for the ISO filename (will be cleaned)

        Returns:
            Path to created ISO file

        Raises:
            DVDAuthoringError: If ISO creation fails
        """
        self.logger.debug("Creating ISO image from VIDEO_TS directory")

        # Create clean filename from title
        from ..utils.filename import normalize_to_ascii

        clean_title = normalize_to_ascii(title)
        # Remove unsafe chars and replace spaces with underscores
        import re

        clean_title = re.sub(r'[<>:"/\\|?*\s]', "_", clean_title)
        # Limit length and ensure it ends with .iso
        clean_title = clean_title[:50].strip("_.- ")
        if not clean_title:
            clean_title = "dvd"

        iso_file = output_dir / f"{clean_title}.iso"

        # Remove existing ISO file to prevent bloat between runs
        if iso_file.exists():
            iso_file.unlink()
            self.logger.debug(f"Removed existing ISO file: {iso_file}")

        # Use ToolManager to get mkisofs/genisoimage command
        try:
            mkisofs_cmd = self.tool_manager.get_tool_command("mkisofs")
        except Exception as e:
            raise DVDAuthoringError(
                "No ISO creation tool found. Please install genisoimage or mkisofs:\n"
                "  macOS: brew install dvdrtools\n"
                "  Ubuntu/Debian: sudo apt install genisoimage\n"
                "  RHEL/CentOS: sudo yum install genisoimage"
            ) from e

        # Create volume label (DVD title) - limit to 32 chars for compatibility
        volume_label = clean_title[:32].upper()
        if not volume_label:
            volume_label = "DVD"

        cmd = mkisofs_cmd + [
            "-dvd-video",
            "-V",
            volume_label,  # Set volume label
            "-o",
            str(iso_file),
            str(video_ts_dir.parent),
        ]

        self.logger.debug(f"Creating ISO with volume label: '{volume_label}'")
        self.logger.debug(f"Executing ISO creation command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )

            self.logger.debug(f"ISO creation completed: {iso_file}")
            self.logger.debug(f"ISO tool stdout: {result.stdout}")

            if result.stderr:
                self.logger.debug(f"ISO tool stderr: {result.stderr}")

            return iso_file

        except subprocess.CalledProcessError as e:
            self.logger.error(f"ISO creation failed with exit code {e.returncode}")
            self.logger.error(f"ISO tool stdout: {e.stdout}")
            self.logger.error(f"ISO tool stderr: {e.stderr}")
            raise DVDAuthoringError(
                f"ISO creation failed: {e.stderr or e.stdout}"
            ) from e

    def estimate_dvd_capacity(
        self, converted_videos: List[ConvertedVideoFile]
    ) -> Tuple[float, bool]:
        """Estimate total size and check if it fits on DVD.

        Args:
            converted_videos: List of converted video files

        Returns:
            Tuple of (size_in_gb, fits_on_dvd)
        """
        total_size = sum(video.file_size for video in converted_videos)
        size_gb = total_size / (1024 * 1024 * 1024)
        fits = size_gb <= self.DVD_CAPACITY_GB

        self.logger.debug(
            f"DVD capacity estimate: {size_gb:.2f}GB, fits on DVD: {fits}"
        )

        return size_gb, fits

    def get_successfully_converted_videos(
        self, converted_videos: List[ConvertedVideoFile]
    ) -> List[ConvertedVideoFile]:
        """Filter to only successfully converted videos that exist.

        Args:
            converted_videos: List of converted video files

        Returns:
            List of videos that exist and are valid
        """
        successful_videos = []

        for video in converted_videos:
            if video.exists and video.file_size > 0:
                successful_videos.append(video)
                self.logger.debug(f"Including video: {video.metadata.title}")
            else:
                self.logger.warning(
                    f"Excluding missing/invalid video: {video.metadata.title}"
                )

        self.logger.info(
            f"Found {len(successful_videos)}/{len(converted_videos)} "
            f"successfully converted videos"
        )

        return successful_videos
