"""DVD authoring service for DVD Maker.

This module handles creating DVD structures using dvdauthor, including:
- Creating VIDEO_TS directory structure
- Generating DVD menus
- Handling multiple videos as chapters in a single title
- ASCII filename normalization for DVD compatibility
- DVD capacity validation and warnings
"""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from ..config.settings import Settings
from ..exceptions import DVDMakerError
from ..models.dvd import DVDChapter, DVDStructure
from ..models.video import VideoFile, VideoMetadata
from ..services.cache_manager import CacheManager
from ..services.converter import ConvertedVideoFile
from ..services.tool_manager import ToolManager
from ..utils.filename import normalize_to_ascii
from ..utils.logging import get_logger
from ..utils.time_format import format_duration_human_readable
from .base import BaseService

# Progress callback type
ProgressCallback = Callable[[str, float], None]


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
        progress_callback: Optional[ProgressCallback] = None,
    ):
        """Initialize the DVD author.

        Args:
            settings: Application settings
            tool_manager: Tool manager for dvdauthor access
            cache_manager: Cache manager for caching operations
            progress_callback: Optional callback for progress reporting
        """
        super().__init__(settings)
        self.tool_manager = tool_manager
        self.cache_manager = cache_manager
        self.progress_callback = progress_callback

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
                f"{len(chapters)} chapters"
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
        duration: float = 0.5,
        aspect_ratio: Optional[str] = None,
    ) -> None:
        """Create a short menu video clip from source video using ffmpeg.

        Args:
            source_video: Source video file to clip from
            output_path: Output path for menu video
            duration: Duration in seconds for menu clip
            aspect_ratio: Target aspect ratio for menu video (defaults to settings)
        """
        try:
            ffmpeg_cmd = self.tool_manager.get_tool_command("ffmpeg")

            # Create a short clip from the beginning of the video for menu
            cmd = ffmpeg_cmd + [
                "-i",
                str(source_video),
                "-t",
                str(duration),  # Duration of clip
                "-c:v",
                "mpeg2video",  # DVD video codec
                "-c:a",
                "ac3",  # DVD audio codec
                "-b:v",
                "8000k",  # High bitrate for menu (like DVDStyler)
                "-b:a",
                "192k",  # Standard AC3 bitrate
                "-r",
                "29.97" if self.settings.video_format.upper() == "NTSC" else "25",
                "-s",
                (
                    "720x480"
                    if self.settings.video_format.upper() == "NTSC"
                    else "720x576"
                ),
                "-aspect",
                aspect_ratio if aspect_ratio else self.settings.aspect_ratio,
                "-f",
                "dvd",
                "-y",  # Overwrite output
                str(output_path),
            ]

            self.logger.debug(f"Creating menu video: {output_path.name}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            if result.stderr:
                self.logger.debug(f"ffmpeg menu creation stderr: {result.stderr}")

        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to create menu video {output_path}: {e}")
            # Create a minimal black video as fallback
            self._create_black_menu_video(
                output_path, duration, aspect_ratio or self.settings.aspect_ratio
            )
        except Exception as e:
            self.logger.warning(f"Menu video creation error: {e}")
            self._create_black_menu_video(
                output_path, duration, aspect_ratio or self.settings.aspect_ratio
            )

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

    def _cleanup_temp_menu_files(self, playlist_output_dir: Path) -> None:
        """Clean up temporary menu files after DVD creation."""
        temp_dir = playlist_output_dir / "temp_menus"
        if temp_dir.exists():
            try:
                import shutil

                shutil.rmtree(temp_dir)
                self.logger.debug("Cleaned up temporary menu files")
            except Exception as e:
                self.logger.warning(f"Failed to clean up temporary menu files: {e}")

    def _create_dvd_xml(self, dvd_structure: DVDStructure, video_ts_dir: Path) -> Path:
        """Create dvdauthor XML configuration with DVDStyler-inspired menu structure.

        Args:
            dvd_structure: DVD structure to create XML for
            video_ts_dir: VIDEO_TS directory path

        Returns:
            Path to created XML file
        """
        self.logger.debug(f"Creating dvdauthor XML for '{dvd_structure.menu_title}'")

        # Create XML structure with optional jumppad for autoplay
        if self.settings.autoplay:
            # jumppad=0 enables First Play Program Chain for autoplay
            dvdauthor = ET.Element("dvdauthor", dest=str(video_ts_dir), jumppad="0")
        else:
            dvdauthor = ET.Element("dvdauthor", dest=str(video_ts_dir))

        # Determine video format for DVD
        video_format = self.settings.video_format.lower()  # dvdauthor expects lowercase

        ordered_chapters = dvd_structure.get_chapters_ordered()
        temp_dir = video_ts_dir.parent / "temp_menus"
        temp_dir.mkdir(exist_ok=True)

        # Create VMGM (Video Manager Menu) like DVDStyler
        vmgm = ET.SubElement(dvdauthor, "vmgm")
        menus = ET.SubElement(vmgm, "menus")

        # Add video and audio specifications for VMGM
        vmgm_aspect = (
            "4:3" if self.settings.car_dvd_compatibility else self.settings.aspect_ratio
        )

        if self.settings.car_dvd_compatibility and self.settings.aspect_ratio != "4:3":
            self.logger.debug(
                f"Car DVD compatibility mode: overriding VMGM aspect ratio from "
                f"{self.settings.aspect_ratio} to 4:3 for better compatibility"
            )

        # Create video element with aspect ratio (only add widescreen for 16:9)
        if vmgm_aspect == "16:9":
            ET.SubElement(
                menus,
                "video",
                format=video_format,
                aspect=vmgm_aspect,
                widescreen="nopanscan",
            )
        else:
            ET.SubElement(
                menus,
                "video",
                format=video_format,
                aspect=vmgm_aspect,
            )
        ET.SubElement(menus, "audio", lang="EN")

        # Add subtitle support
        subpicture = ET.SubElement(menus, "subpicture", lang="EN")
        ET.SubElement(
            subpicture,
            "stream",
            id="0",
            mode="widescreen" if vmgm_aspect == "16:9" else "normal",
        )
        if vmgm_aspect == "16:9":
            ET.SubElement(subpicture, "stream", id="1", mode="letterbox")

        pgc = ET.SubElement(menus, "pgc", entry="title")

        # Create VMGM menu video (like DVDStyler's menu0-0.mpg)
        if ordered_chapters:
            vmgm_menu_file = temp_dir / "menu0-0.mpg"
            self._create_menu_video(
                ordered_chapters[0].video_file.file_path,
                vmgm_menu_file,
                aspect_ratio=vmgm_aspect,
            )

            # Add buttons and menu video reference like DVDStyler
            ET.SubElement(pgc, "button", name="button01").text = "g0=1;jump title 1;"
            if len(ordered_chapters) > 1:
                ET.SubElement(pgc, "button", name="button02").text = (
                    "g0=0;jump titleset 1 menu;"
                )

            # Add menu video (jumppad attribute controls autoplay behavior)
            ET.SubElement(pgc, "vob", file=str(vmgm_menu_file), pause="inf")
            ET.SubElement(pgc, "pre").text = "g1=101;"
        else:
            # Fallback to simple jump if no chapters
            ET.SubElement(pgc, "pre").text = "jump title 1;"

        # Create titleset
        titleset = ET.SubElement(dvdauthor, "titleset")

        # Add titleset menus if we have multiple chapters (like DVDStyler)
        if len(ordered_chapters) > 1:
            titleset_menus = ET.SubElement(titleset, "menus")

            # Video and audio specs for titleset menus (only add widescreen for 16:9)
            if self.settings.aspect_ratio == "16:9":
                ET.SubElement(
                    titleset_menus,
                    "video",
                    format=video_format,
                    aspect=self.settings.aspect_ratio,
                    widescreen="nopanscan",
                )
            else:
                ET.SubElement(
                    titleset_menus,
                    "video",
                    format=video_format,
                    aspect=self.settings.aspect_ratio,
                )
            ET.SubElement(titleset_menus, "audio", lang="EN")

            # Subtitle support
            ts_subpicture = ET.SubElement(titleset_menus, "subpicture", lang="EN")
            ET.SubElement(
                ts_subpicture,
                "stream",
                id="0",
                mode="widescreen" if self.settings.aspect_ratio == "16:9" else "normal",
            )
            if self.settings.aspect_ratio == "16:9":
                ET.SubElement(ts_subpicture, "stream", id="1", mode="letterbox")

            menu_pgc = ET.SubElement(titleset_menus, "pgc", entry="ptt,root")

            # Create titleset menu video (like DVDStyler's menu1-0.mpg)
            titleset_menu_file = temp_dir / "menu1-0.mpg"
            # Use second video or first if only one
            menu_source = (
                ordered_chapters[1]
                if len(ordered_chapters) > 1
                else ordered_chapters[0]
            )
            self._create_menu_video(
                menu_source.video_file.file_path,
                titleset_menu_file,
                aspect_ratio=self.settings.aspect_ratio,
            )

            # Create chapter navigation buttons (limit to 6 like DVDStyler's first menu)
            max_buttons = min(len(ordered_chapters), 6)
            for i in range(max_buttons):
                chapter_num = i + 1
                button_name = f"button{i+1:02d}"
                button_text = f"g0=0;jump title 1 chapter {chapter_num};"
                ET.SubElement(menu_pgc, "button", name=button_name).text = button_text

            # Add navigation buttons
            ET.SubElement(menu_pgc, "button", name="button07").text = (
                "g0=0;jump vmgm menu 1;"
            )

            # Add menu video and DVDStyler-style pre command
            ET.SubElement(menu_pgc, "vob", file=str(titleset_menu_file), pause="inf")
            pre_text = (
                "if (g1 & 0x8000 !=0) {g1^=0x8000;if (g1==101) jump vmgm menu 1;}g1=1;"
            )
            ET.SubElement(menu_pgc, "pre").text = pre_text

        # Create titles section
        titles = ET.SubElement(titleset, "titles")

        # Add video format to titles (only add widescreen for 16:9)
        if self.settings.aspect_ratio == "16:9":
            ET.SubElement(
                titles,
                "video",
                format=video_format,
                aspect=self.settings.aspect_ratio,
                widescreen="nopanscan",
            )
        else:
            ET.SubElement(
                titles,
                "video",
                format=video_format,
                aspect=self.settings.aspect_ratio,
            )
        ET.SubElement(titles, "audio", lang="EN")

        title_pgc = ET.SubElement(titles, "pgc")

        # Add chapters as individual vob entries with chapter marks
        for i, chapter in enumerate(ordered_chapters, 1):
            # Normalize filename for DVD compatibility
            normalized_path = self._normalize_video_path(chapter.video_file.file_path)
            ET.SubElement(title_pgc, "vob", file=str(normalized_path), chapters="0:00")

        # Add DVDStyler-inspired post command for menu navigation
        if len(ordered_chapters) > 1:
            ET.SubElement(title_pgc, "post").text = "g1|=0x8000; call menu entry root;"

        # Write XML to temporary file with pretty formatting
        xml_file = video_ts_dir.parent / "dvd_structure.xml"

        # Pretty print the XML for debugging
        import xml.dom.minidom

        rough_string = ET.tostring(dvdauthor, encoding="utf-8")
        reparsed = xml.dom.minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8")

        # Write pretty formatted XML
        with open(xml_file, "wb") as f:
            f.write(pretty_xml)

        self.logger.debug(
            f"Created DVDStyler-inspired dvdauthor XML with menu videos: {xml_file}"
        )
        if len(ordered_chapters) > 1:
            self.logger.info(
                f"Generated menu videos for {len(ordered_chapters)} chapter navigation"
            )

        return xml_file

    def _normalize_video_path(self, video_path: Path) -> Path:
        """Normalize video file path for DVD compatibility.

        Args:
            video_path: Original video file path

        Returns:
            Normalized path with ASCII-safe filename
        """
        # Get ASCII-safe filename
        ascii_filename = normalize_to_ascii(video_path.name)

        # Create normalized path in same directory
        normalized_path = video_path.parent / ascii_filename

        # Copy file if normalization changed the name
        if ascii_filename != video_path.name and not normalized_path.exists():
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

        cmd = mkisofs_cmd + [
            "-dvd-video",
            "-o",
            str(iso_file),
            str(video_ts_dir.parent),
        ]

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
