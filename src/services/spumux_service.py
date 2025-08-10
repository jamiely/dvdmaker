"""Spumux service for DVD Maker.

This module handles creating DVD button overlays using spumux, including:
- Generating button graphics with PIL
- Creating spumux XML configuration files
- Executing spumux to create subtitle (.sub/.idx) files
- Integrating button overlays with DVD menu videos
"""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    PIL_AVAILABLE = False
else:
    PIL_AVAILABLE = True

from ..config.settings import Settings
from ..exceptions import DVDMakerError
from ..services.cache_manager import CacheManager
from ..services.tool_manager import ToolManager
from .base import BaseService


class SpumuxError(DVDMakerError):
    """Base exception for spumux-related errors."""

    pass


class SpumuxNotAvailableError(SpumuxError):
    """Exception raised when spumux is not available."""

    pass


class ButtonGraphicError(SpumuxError):
    """Exception raised when button graphic creation fails."""

    pass


class ButtonConfig:
    """Configuration for a single DVD button."""

    def __init__(
        self,
        name: str,
        text: str,
        position: Tuple[int, int],
        size: Tuple[int, int],
        navigation_command: str,
        color: str = "#FFFFFF",
    ):
        """Initialize button configuration.

        Args:
            name: Button name (e.g., "button01")
            text: Text to display on button
            position: (x, y) position on screen
            size: (width, height) of button
            navigation_command: DVD navigation command
            color: Text color in hex format
        """
        self.name = name
        self.text = text
        self.position = position
        self.size = size
        self.navigation_command = navigation_command
        self.color = color

    @property
    def x0(self) -> int:
        """Left edge of button."""
        return self.position[0] - self.size[0] // 2

    @property
    def y0(self) -> int:
        """Top edge of button."""
        return self.position[1] - self.size[1] // 2

    @property
    def x1(self) -> int:
        """Right edge of button."""
        return self.position[0] + self.size[0] // 2

    @property
    def y1(self) -> int:
        """Bottom edge of button."""
        return self.position[1] + self.size[1] // 2


class SubtitleFiles:
    """Container for spumux-generated subtitle files."""

    def __init__(self, sub_file: Optional[Path], idx_file: Optional[Path]):
        """Initialize subtitle files.

        Args:
            sub_file: Path to .sub file (None if not applicable)
            idx_file: Path to .idx file (None if not applicable)
        """
        self.sub_file = sub_file
        self.idx_file = idx_file

    @property
    def exists(self) -> bool:
        """Check if both subtitle files exist."""
        return (
            self.sub_file is not None
            and self.idx_file is not None
            and self.sub_file.exists()
            and self.idx_file.exists()
        )


class ButtonOverlay:
    """Container for button overlay data."""

    def __init__(
        self,
        button_config: ButtonConfig,
        graphic_file: Path,
        subtitle_files: SubtitleFiles,
    ):
        """Initialize button overlay.

        Args:
            button_config: Button configuration
            graphic_file: Path to button graphic PNG
            subtitle_files: Generated subtitle files
        """
        self.button_config = button_config
        self.graphic_file = graphic_file
        self.subtitle_files = subtitle_files


class SpumuxService(BaseService):
    """Creates DVD button overlays using spumux.

    This class handles:
    - Creating button graphics with PIL
    - Generating spumux XML configuration
    - Executing spumux to create subtitle overlays
    - Integration with DVD authoring workflow
    """

    def __init__(
        self,
        settings: Settings,
        tool_manager: ToolManager,
        cache_manager: CacheManager,
    ):
        """Initialize the spumux service.

        Args:
            settings: Application settings
            tool_manager: Tool manager for spumux access
            cache_manager: Cache manager for caching operations
        """
        super().__init__(settings)
        self.tool_manager = tool_manager
        self.cache_manager = cache_manager

        # Check PIL availability
        if not PIL_AVAILABLE:
            self.logger.warning(
                "PIL/Pillow not available - button graphics cannot be created"
            )

    def is_available(self) -> bool:
        """Check if spumux and dependencies are available.

        Returns:
            True if spumux and PIL are available, False otherwise
        """
        if not PIL_AVAILABLE:
            self.logger.debug("PIL/Pillow not available")
            return False

        try:
            self.tool_manager.get_tool_command("spumux")
            return True
        except Exception as e:
            self.logger.debug(f"spumux not available: {e}")
            return False

    def create_button_overlay(
        self, menu_video: Path, output_dir: Path
    ) -> Optional[ButtonOverlay]:
        """Create button overlay for menu video.

        Args:
            menu_video: Path to menu video file
            output_dir: Directory for output files

        Returns:
            ButtonOverlay object if successful, None if disabled or failed

        Raises:
            SpumuxError: If button overlay creation fails
        """
        if not getattr(self.settings, "button_enabled", True):
            self.logger.debug("Button overlay disabled in settings")
            return None

        if not self.is_available():
            self.logger.warning(
                "Spumux or dependencies not available - skipping button overlay"
            )
            return None

        self._log_operation_start("button overlay creation", menu_video=menu_video.name)

        try:
            # Create button configuration
            button_config = self._create_button_config()

            # Create button graphics (normal, highlight, select)
            graphic_files = self._create_button_graphics(
                button_config, output_dir / "temp_buttons"
            )

            # Generate spumux XML
            xml_file = self._generate_spumux_xml(
                button_config, graphic_files, output_dir
            )

            # Execute spumux
            subtitle_files = self._execute_spumux(xml_file, menu_video, output_dir)

            overlay = ButtonOverlay(button_config, graphic_files[0], subtitle_files)

            self._log_operation_complete(
                "button overlay creation", button_name=button_config.name
            )
            return overlay

        except Exception as e:
            self._log_operation_error("button overlay creation", e)
            # Don't re-raise - allow DVD creation to continue without buttons
            return None

    def _create_button_config(self) -> ButtonConfig:
        """Create button configuration matching DVDStyler's "Play All" button.

        Returns:
            ButtonConfig object with DVDStyler-compatible "Play All" button
        """
        # DVDStyler positioning: button01 at (120, 286) to (219, 310)  
        # Force DVDStyler coordinates for maximum car DVD compatibility
        # Override any existing settings to ensure DVDStyler positioning
        
        return ButtonConfig(
            name="button01",
            text="Play all",       # DVDStyler exact text
            position=(169, 298),   # Center of DVDStyler button: (120+219)/2, (286+310)/2
            size=(99, 24),         # DVDStyler dimensions: (219-120, 310-286)
            navigation_command="g0=1;jump title 1;",  # The autoplay magic!
            color="#FFFFFF",       # White text
        )

    def _create_button_graphics(
        self, button_config: ButtonConfig, output_dir: Path
    ) -> Tuple[Path, Path, Path]:
        """Create DVDStyler-style button graphics (normal, highlight, select).

        Args:
            button_config: Button configuration
            output_dir: Directory for output files

        Returns:
            Tuple of (normal, highlight, select) PNG file paths

        Raises:
            ButtonGraphicError: If graphic creation fails
        """
        if not PIL_AVAILABLE:
            raise ButtonGraphicError("PIL/Pillow not available for button graphics")

        output_dir.mkdir(parents=True, exist_ok=True)
        
        # DVDStyler naming convention  
        normal_file = output_dir / f"{button_config.name}_buttons.png"
        highlight_file = output_dir / f"{button_config.name}_highlight.png" 
        select_file = output_dir / f"{button_config.name}_select.png"

        try:
            screen_width = 720
            screen_height = 480
            button_x0, button_y0 = button_config.x0, button_config.y0
            button_x1, button_y1 = button_config.x1, button_config.y1

            # 1. Normal state - mostly transparent (like DVDStyler)
            normal_image = Image.new("RGBA", (screen_width, screen_height), (0, 0, 0, 0))
            normal_image.save(normal_file, "PNG")

            # 2. Highlight state - blue rectangle (like DVDStyler's highlight)
            highlight_image = Image.new("RGBA", (screen_width, screen_height), (0, 0, 0, 0))
            highlight_pixels = highlight_image.load()
            
            # Draw blue highlight rectangle matching DVDStyler's style
            for y in range(button_y0, button_y1):
                for x in range(button_x0, button_x1):
                    if y < screen_height and x < screen_width:
                        # Blue highlight color (like DVDStyler)
                        highlight_pixels[x, y] = (100, 150, 255, 180)  # Light blue, semi-transparent
            
            highlight_image.save(highlight_file, "PNG")

            # 3. Select state - brighter/different color when pressed  
            select_image = Image.new("RGBA", (screen_width, screen_height), (0, 0, 0, 0))
            select_pixels = select_image.load()
            
            # Draw brighter selection rectangle
            for y in range(button_y0, button_y1):
                for x in range(button_x0, button_x1):
                    if y < screen_height and x < screen_width:
                        # Brighter blue for selection (like DVDStyler)
                        select_pixels[x, y] = (150, 200, 255, 220)  # Brighter blue
                        
            select_image.save(select_file, "PNG")

            self.logger.debug(
                f"Created DVDStyler-style button graphics: normal({normal_file.name}), "
                f"highlight({highlight_file.name}), select({select_file.name}) "
                f"at ({button_x0},{button_y0})-({button_x1},{button_y1})"
            )
            return normal_file, highlight_file, select_file

        except Exception as e:
            raise ButtonGraphicError(f"Failed to create button graphics: {e}") from e

    def _generate_spumux_xml(
        self, button_config: ButtonConfig, graphic_files: Tuple[Path, Path, Path], output_dir: Path
    ) -> Path:
        """Generate spumux XML configuration file.

        Args:
            button_config: Button configuration
            graphic_files: Tuple of (normal, highlight, select) PNG files
            output_dir: Directory for output file

        Returns:
            Path to created XML file
        """
        xml_file = output_dir / "spumux_config.xml"
        normal_file, highlight_file, select_file = graphic_files

        # Create spumux XML structure
        subpictures = ET.Element("subpictures")
        stream = ET.SubElement(subpictures, "stream")

        # Create SPU element exactly like DVDStyler with separate state images
        spu = ET.SubElement(
            stream,
            "spu",
            start="00:00:00.00",
            image=str(normal_file),
            highlight=str(highlight_file), 
            select=str(select_file),
            force="yes",  # Force display for menu buttons
        )

        # Add button definition with absolute screen coordinates (DVDStyler style)
        ET.SubElement(
            spu,
            "button",
            name=button_config.name,
            x0=str(button_config.x0),  # Absolute screen coordinates
            y0=str(button_config.y0),
            x1=str(button_config.x1),
            y1=str(button_config.y1),
            left=button_config.name,   # Self-referencing navigation
            right=button_config.name,
            up=button_config.name,
            down="button02" if button_config.name == "button01" else "button01",
        )

        # Write XML to file with pretty formatting
        import xml.dom.minidom

        rough_string = ET.tostring(subpictures, encoding="utf-8")
        reparsed = xml.dom.minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8")

        with open(xml_file, "wb") as f:
            f.write(pretty_xml)

        self.logger.debug(f"Generated spumux XML: {xml_file.name}")
        return xml_file

    def _execute_spumux(
        self, xml_file: Path, menu_video: Path, output_dir: Path
    ) -> SubtitleFiles:
        """Execute spumux to create subtitle files.

        Args:
            xml_file: Path to spumux XML configuration
            menu_video: Path to menu video file
            output_dir: Directory for output files

        Returns:
            SubtitleFiles object with paths to created files

        Raises:
            SpumuxError: If spumux execution fails
        """
        try:
            spumux_cmd = self.tool_manager.get_tool_command("spumux")
        except Exception as e:
            raise SpumuxNotAvailableError("spumux not found") from e

        # Output file (spumux processes video through stdin/stdout)
        base_name = menu_video.stem
        processed_video = output_dir / f"{base_name}_with_buttons.mpv"

        # Remove existing processed video if it exists
        if processed_video.exists():
            processed_video.unlink()

        # Build spumux command with DVD mode
        cmd = spumux_cmd + ["-m", "dvd", "-P", "-s", "0", str(xml_file)]

        self.logger.debug(f"Executing spumux: {' '.join(cmd)}")

        try:
            # spumux processes video through stdin/stdout, embedding subtitle data
            with (
                open(menu_video, "rb") as input_file,
                open(processed_video, "wb") as output_file,
            ):
                result = subprocess.run(
                    cmd,
                    stdin=input_file,
                    stdout=output_file,
                    stderr=subprocess.PIPE,
                    check=True,
                    cwd=output_dir,
                )

            self.logger.debug("spumux completed successfully")
            if result.stderr:
                self.logger.debug(f"spumux stderr: {result.stderr.decode()}")

            # Verify the processed video was created
            if processed_video.exists() and processed_video.stat().st_size > 0:
                self.logger.debug(
                    f"Created processed video with buttons: {processed_video.name}"
                )
                # Replace original menu video with processed version
                processed_video.replace(menu_video)
                self.logger.debug("Replaced original menu video with processed version")
            else:
                self.logger.warning(
                    "spumux completed but no processed video was created"
                )

            # Return empty SubtitleFiles object (spumux doesn't create separate
            # subtitle files) - subtitle data is embedded in the video stream
            subtitle_files = SubtitleFiles(None, None)
            return subtitle_files

        except subprocess.CalledProcessError as e:
            self.logger.error(f"spumux failed with exit code {e.returncode}")
            self.logger.error(f"spumux stdout: {e.stdout.decode() if e.stdout else ''}")
            self.logger.error(f"spumux stderr: {e.stderr.decode() if e.stderr else ''}")
            raise SpumuxError(f"spumux execution failed: {e}") from e
