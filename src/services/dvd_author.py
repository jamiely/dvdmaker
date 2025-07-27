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
from ..models.dvd import DVDChapter, DVDStructure
from ..models.video import VideoFile, VideoMetadata
from ..services.cache_manager import CacheManager
from ..services.converter import ConvertedVideoFile
from ..services.tool_manager import ToolManager
from ..utils.filename import normalize_to_ascii
from ..utils.logging import get_logger
from ..utils.time_format import format_duration_human_readable

# Progress callback type
ProgressCallback = Callable[[str, float], None]

logger = get_logger(__name__)


class DVDAuthorError(Exception):
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
            logger.error("No VTS IFO files found")
            return False

        # Check for corresponding BUP files for each VTS
        for ifo_file in vts_ifo_files:
            bup_file = ifo_file.with_suffix(".BUP")
            if not bup_file.exists():
                logger.error(f"Missing corresponding BUP file: {bup_file.name}")
                return False

        # Check for VTS VOB files (at least one should exist)
        vob_files = list(self.video_ts_dir.glob("VTS_*_*.VOB"))
        if not vob_files:
            logger.error("No VTS VOB files found")
            return False

        logger.debug(
            f"DVD structure validation passed: {len(vts_ifo_files)} VTS sets, "
            f"{len(vob_files)} VOB files found"
        )
        return True


class DVDAuthor:
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
        self.settings = settings
        self.tool_manager = tool_manager
        self.cache_manager = cache_manager
        self.progress_callback = progress_callback

        logger.debug("DVDAuthor initialized")

    def _report_progress(self, message: str, progress: float) -> None:
        """Report progress if callback is available.

        Args:
            message: Progress message
            progress: Progress value (0.0 to 1.0)
        """
        if self.progress_callback:
            self.progress_callback(message, progress)
        logger.debug(f"DVD Author Progress: {message} ({progress:.1%})")

    def create_dvd_structure(
        self,
        converted_videos: List[ConvertedVideoFile],
        menu_title: str,
        output_dir: Path,
        create_iso: bool = False,
    ) -> AuthoredDVD:
        """Create DVD structure from converted videos.

        Args:
            converted_videos: List of converted video files
            menu_title: Title for the DVD menu
            output_dir: Directory to create DVD structure in
            create_iso: Whether to create an ISO file

        Returns:
            AuthoredDVD object with completed structure

        Raises:
            DVDAuthoringError: If DVD authoring fails
            DVDCapacityExceededError: If videos exceed DVD capacity
        """
        logger.debug(
            f"Creating DVD structure with {len(converted_videos)} videos: "
            f"'{menu_title}'"
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
            logger.warning(
                f"DVD capacity exceeded: {dvd_structure.size_gb:.2f}GB > "
                f"{self.DVD_CAPACITY_GB}GB"
            )
            # Don't raise exception - create DVD with available videos
            logger.warning("Continuing with DVD creation despite capacity warning")

        # Create output directory structure
        video_ts_dir = output_dir / "VIDEO_TS"
        audio_ts_dir = output_dir / "AUDIO_TS"

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
                iso_file = self._create_iso(output_dir, video_ts_dir, menu_title)
                authored_dvd.iso_file = iso_file

            self._report_progress("DVD creation complete", 1.0)
            logger.info(
                f"DVD creation completed successfully: {authored_dvd.size_gb:.2f}GB, "
                f"{len(chapters)} chapters"
            )

            return authored_dvd

        except DVDStructureCreationError:
            # Re-raise validation errors as-is for more specific error handling
            raise
        except Exception as e:
            logger.error(f"DVD authoring failed: {e}")
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
        logger.debug(f"Creating DVD chapters from {len(converted_videos)} videos")

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
            logger.debug(
                f"Created chapter {i}: {video.metadata.title} "
                f"({duration_str}, starts at {start_time_str})"
            )

        total_duration_str = format_duration_human_readable(current_time)
        logger.info(
            f"Created {len(chapters)} chapters with total duration {total_duration_str}"
        )
        return chapters

    def _create_dvd_xml(self, dvd_structure: DVDStructure, video_ts_dir: Path) -> Path:
        """Create dvdauthor XML configuration.

        Args:
            dvd_structure: DVD structure to create XML for
            video_ts_dir: VIDEO_TS directory path

        Returns:
            Path to created XML file
        """
        logger.debug(f"Creating dvdauthor XML for '{dvd_structure.menu_title}'")

        # Create XML structure
        dvdauthor = ET.Element("dvdauthor", dest=str(video_ts_dir))

        # Determine video format for DVD
        video_format = self.settings.video_format.lower()  # dvdauthor expects lowercase

        # Create vmgm (Video Manager Menu)
        vmgm = ET.SubElement(dvdauthor, "vmgm")
        menus = ET.SubElement(vmgm, "menus")

        # Add video format to menus (satisfies VMGM)
        ET.SubElement(
            menus, "video", format=video_format, aspect=self.settings.aspect_ratio
        )

        pgc = ET.SubElement(menus, "pgc")

        # Add menu title
        ET.SubElement(pgc, "pre").text = "jump title 1;"

        # Create titleset
        titleset = ET.SubElement(dvdauthor, "titleset")
        titles = ET.SubElement(titleset, "titles")

        # Add video format to titles
        ET.SubElement(
            titles, "video", format=video_format, aspect=self.settings.aspect_ratio
        )

        title_pgc = ET.SubElement(titles, "pgc")

        # Add chapters as cells
        ordered_chapters = dvd_structure.get_chapters_ordered()
        for chapter in ordered_chapters:
            # Normalize filename for DVD compatibility
            normalized_path = self._normalize_video_path(chapter.video_file.file_path)
            ET.SubElement(title_pgc, "vob", file=str(normalized_path), chapters="0")

        # Write XML to temporary file
        xml_file = video_ts_dir.parent / "dvd_structure.xml"
        tree = ET.ElementTree(dvdauthor)
        tree.write(xml_file, encoding="utf-8", xml_declaration=True)

        logger.debug(f"Created dvdauthor XML: {xml_file}")
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
            logger.debug(f"Copying video for ASCII compatibility: {ascii_filename}")
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
        logger.info("Running dvdauthor to create DVD structure")

        import shutil

        dvdauthor_path = shutil.which("dvdauthor")
        if not dvdauthor_path:
            raise DVDAuthoringError(
                "dvdauthor not found. Please install dvdauthor:\n"
                "  macOS: brew install dvdauthor\n"
                "  Ubuntu/Debian: sudo apt install dvdauthor\n"
                "  RHEL/CentOS: sudo yum install dvdauthor"
            )

        # Use the parent directory of VIDEO_TS as the output directory
        output_dir = video_ts_dir.parent
        cmd = [str(dvdauthor_path), "-o", str(output_dir), "-x", str(xml_file)]

        logger.info(f"Executing dvdauthor command: {' '.join(cmd)}")

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

            logger.info(f"dvdauthor completed successfully in {creation_time:.1f}s")
            logger.debug(f"dvdauthor stdout: {result.stdout}")

            if result.stderr:
                logger.debug(f"dvdauthor stderr: {result.stderr}")

            return creation_time

        except subprocess.CalledProcessError as e:
            logger.error(f"dvdauthor failed with exit code {e.returncode}")
            logger.error(f"dvdauthor stdout: {e.stdout}")
            logger.error(f"dvdauthor stderr: {e.stderr}")
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
        logger.debug("Creating ISO image from VIDEO_TS directory")

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

        # Use genisoimage or mkisofs to create ISO
        iso_tools = ["genisoimage", "mkisofs"]
        iso_tool = None

        for tool in iso_tools:
            try:
                result = subprocess.run(
                    [tool, "--version"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                iso_tool = tool
                logger.debug(f"Found ISO creation tool: {tool}")
                break
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue

        if not iso_tool:
            raise DVDAuthoringError(
                "No ISO creation tool found. Please install genisoimage or mkisofs:\n"
                "  macOS: brew install dvdrtools\n"
                "  Ubuntu/Debian: sudo apt install genisoimage\n"
                "  RHEL/CentOS: sudo yum install genisoimage"
            )

        cmd = [
            iso_tool,
            "-dvd-video",
            "-o",
            str(iso_file),
            str(video_ts_dir.parent),
        ]

        logger.debug(f"Executing ISO creation command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )

            logger.info(f"ISO creation completed: {iso_file}")
            logger.debug(f"ISO tool stdout: {result.stdout}")

            if result.stderr:
                logger.debug(f"ISO tool stderr: {result.stderr}")

            return iso_file

        except subprocess.CalledProcessError as e:
            logger.error(f"ISO creation failed with exit code {e.returncode}")
            logger.error(f"ISO tool stdout: {e.stdout}")
            logger.error(f"ISO tool stderr: {e.stderr}")
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

        logger.debug(f"DVD capacity estimate: {size_gb:.2f}GB, fits on DVD: {fits}")

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
                logger.debug(f"Including video: {video.metadata.title}")
            else:
                logger.warning(
                    f"Excluding missing/invalid video: {video.metadata.title}"
                )

        logger.info(
            f"Found {len(successful_videos)}/{len(converted_videos)} "
            f"successfully converted videos"
        )

        return successful_videos
