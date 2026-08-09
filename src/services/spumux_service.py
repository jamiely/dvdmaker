"""Create interactive DVD menu button overlays with spumux."""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

try:
    from PIL import Image, ImageDraw
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


class SpumuxNotAvailableError(SpumuxError):
    """Raised when a working spumux/Pillow installation is unavailable."""


class ButtonGraphicError(SpumuxError):
    """Raised when button graphics cannot be created."""


class ButtonConfig:
    """Visual bounds, remote navigation, and action for one DVD button."""

    def __init__(
        self,
        name: str,
        text: str,
        position: Tuple[int, int],
        size: Tuple[int, int],
        navigation_command: str,
        color: str = "#FFFFFF",
        left: Optional[str] = None,
        right: Optional[str] = None,
        up: Optional[str] = None,
        down: Optional[str] = None,
    ):
        self.name = name
        self.text = text
        self.position = position
        self.size = size
        self.navigation_command = navigation_command
        self.color = color
        self.left = left or name
        self.right = right or name
        self.up = up or name
        self.down = down or name

    @property
    def x0(self) -> int:
        return self.position[0] - self.size[0] // 2

    @property
    def y0(self) -> int:
        return self.position[1] - self.size[1] // 2

    @property
    def x1(self) -> int:
        return self.position[0] + self.size[0] // 2

    @property
    def y1(self) -> int:
        return self.position[1] + self.size[1] // 2


class SubtitleFiles:
    """Container retained for the original public service interface."""

    def __init__(self, sub_file: Optional[Path], idx_file: Optional[Path]):
        self.sub_file = sub_file
        self.idx_file = idx_file

    @property
    def exists(self) -> bool:
        return (
            self.sub_file is not None
            and self.idx_file is not None
            and self.sub_file.exists()
            and self.idx_file.exists()
        )


class ButtonOverlay:
    """Description of the buttons embedded into a menu MPEG."""

    def __init__(
        self,
        button_config: ButtonConfig,
        graphic_file: Path,
        subtitle_files: SubtitleFiles,
        button_configs: Optional[Sequence[ButtonConfig]] = None,
    ):
        self.button_config = button_config
        self.button_configs = tuple(button_configs or (button_config,))
        self.graphic_file = graphic_file
        self.subtitle_files = subtitle_files


ButtonConfigs = Union[ButtonConfig, Sequence[ButtonConfig]]


class SpumuxService(BaseService):
    """Create and multiplex one or more interactive buttons per menu."""

    def __init__(
        self,
        settings: Settings,
        tool_manager: ToolManager,
        cache_manager: CacheManager,
    ):
        super().__init__(settings)
        self.tool_manager = tool_manager
        self.cache_manager = cache_manager
        if not PIL_AVAILABLE:
            self.logger.warning(
                "PIL/Pillow not available - button graphics cannot be created"
            )

    def is_available(self) -> bool:
        if not PIL_AVAILABLE:
            self.logger.debug("PIL/Pillow not available")
            return False
        try:
            self.tool_manager.get_tool_command("spumux")
            return True
        except Exception as exc:
            self.logger.debug(f"spumux not available: {exc}")
            return False

    def create_button_overlay(
        self,
        menu_video: Path,
        output_dir: Path,
        button_configs: Optional[Sequence[ButtonConfig]] = None,
        asset_key: Optional[str] = None,
        strict: bool = False,
    ) -> Optional[ButtonOverlay]:
        """Embed all configured hotspots and highlight states in ``menu_video``."""
        if not getattr(self.settings, "button_enabled", True):
            if strict:
                raise SpumuxNotAvailableError("DVD menu buttons are disabled")
            self.logger.debug("Button overlay disabled in settings")
            return None
        if not self.is_available():
            if strict:
                raise SpumuxNotAvailableError(
                    "spumux and Pillow are required for interactive DVD menus"
                )
            self.logger.warning(
                "Spumux or dependencies not available - skipping button overlay"
            )
            return None

        self._log_operation_start("button overlay creation", menu_video=menu_video.name)
        try:
            configs: Tuple[ButtonConfig, ...] = tuple(
                button_configs or (self._create_button_config(),)
            )
            if not configs:
                raise ButtonGraphicError("At least one DVD menu button is required")
            key = asset_key or menu_video.stem
            buttons_dir = self.cache_manager.cache_dir / "temp_buttons" / key
            graphic_files = self._create_button_graphics(configs, buttons_dir)
            xml_file = self._generate_spumux_xml(
                configs, graphic_files, output_dir, asset_key=key
            )
            stream_ids = (0, 1) if self.settings.aspect_ratio == "16:9" else (0,)
            subtitle_files = self._execute_spumux(
                xml_file, menu_video, output_dir, stream_ids=stream_ids
            )
            overlay = ButtonOverlay(
                configs[0], graphic_files[0], subtitle_files, configs
            )
            self._log_operation_complete(
                "button overlay creation", button_count=len(configs)
            )
            return overlay
        except Exception as exc:
            self._log_operation_error("button overlay creation", exc)
            if strict:
                raise
            return None

    def _create_button_config(self) -> ButtonConfig:
        """Return the legacy DVDStyler-compatible Play All button."""
        return ButtonConfig(
            name="button01",
            text="Play all",
            position=(169, 298),
            size=(99, 24),
            navigation_command="g0=1;jump title 1;",
            color="#FFFFFF",
        )

    @staticmethod
    def _normalize_button_configs(
        button_config: ButtonConfigs,
    ) -> Tuple[ButtonConfig, ...]:
        configs: Tuple[ButtonConfig, ...]
        if isinstance(button_config, ButtonConfig):
            configs = (button_config,)
        else:
            configs = tuple(button_config)
        if not configs:
            raise ButtonGraphicError("At least one DVD menu button is required")
        return configs

    def _create_button_graphics(
        self, button_config: ButtonConfigs, output_dir: Path
    ) -> Tuple[Path, Path, Path]:
        """Create transparent normal, highlighted, and selected menu layers."""
        if not PIL_AVAILABLE:
            raise ButtonGraphicError("PIL/Pillow not available for button graphics")
        configs = self._normalize_button_configs(button_config)
        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = configs[0].name if len(configs) == 1 else "menu"
        normal_file = output_dir / f"{base_name}_buttons.png"
        highlight_file = output_dir / f"{base_name}_highlight.png"
        select_file = output_dir / f"{base_name}_select.png"
        width = 720
        height = 480 if self.settings.video_format == "NTSC" else 576
        try:
            normal_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            normal_image.save(normal_file, "PNG")

            highlight_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            highlight_draw = ImageDraw.Draw(highlight_image)
            for config in configs:
                highlight_draw.rectangle(
                    (config.x0, config.y0, config.x1 - 1, config.y1 - 1),
                    outline=(100, 150, 255, 255),
                    width=6,
                )
            highlight_image.save(highlight_file, "PNG")

            select_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            select_draw = ImageDraw.Draw(select_image)
            for config in configs:
                select_draw.rectangle(
                    (config.x0, config.y0, config.x1 - 1, config.y1 - 1),
                    outline=(180, 220, 255, 255),
                    width=8,
                )
            select_image.save(select_file, "PNG")
            self.logger.debug(
                "Created button graphics for %d button(s) in %s",
                len(configs),
                output_dir,
            )
            return normal_file, highlight_file, select_file
        except Exception as exc:
            raise ButtonGraphicError(
                f"Failed to create button graphics: {exc}"
            ) from exc

    def _generate_spumux_xml(
        self,
        button_config: ButtonConfigs,
        graphic_files: Tuple[Path, Path, Path],
        output_dir: Path,
        asset_key: Optional[str] = None,
    ) -> Path:
        """Generate Spumux XML containing every visible menu hotspot."""
        del output_dir  # Kept for backward-compatible callers.
        configs = self._normalize_button_configs(button_config)
        cache_dir = self.cache_manager.cache_dir / "build"
        cache_dir.mkdir(parents=True, exist_ok=True)
        xml_file = cache_dir / (
            f"{asset_key}_spumux.xml" if asset_key else "spumux_config.xml"
        )
        normal_file, highlight_file, select_file = graphic_files
        subpictures = ET.Element("subpictures")
        stream = ET.SubElement(subpictures, "stream")
        spu = ET.SubElement(
            stream,
            "spu",
            start="00:00:00.00",
            image=str(normal_file),
            highlight=str(highlight_file),
            select=str(select_file),
            force="yes",
        )
        for config in configs:
            ET.SubElement(
                spu,
                "button",
                name=config.name,
                x0=str(config.x0),
                y0=str(config.y0),
                x1=str(config.x1),
                y1=str(config.y1),
                left=config.left,
                right=config.right,
                up=config.up,
                down=config.down,
            )

        import xml.dom.minidom

        rough_string = ET.tostring(subpictures, encoding="utf-8")
        pretty_xml = xml.dom.minidom.parseString(rough_string).toprettyxml(
            indent="  ", encoding="utf-8"
        )
        with open(xml_file, "wb") as output_file:
            output_file.write(pretty_xml)
        self.logger.debug(f"Generated spumux XML: {xml_file.name}")
        return xml_file

    def _execute_spumux(
        self,
        xml_file: Path,
        menu_video: Path,
        output_dir: Path,
        stream_ids: Sequence[int] = (0,),
    ) -> SubtitleFiles:
        """Multiplex one overlay stream, plus letterbox mapping for widescreen."""
        try:
            spumux_cmd = self.tool_manager.get_tool_command("spumux")
        except Exception as exc:
            raise SpumuxNotAvailableError("spumux not found") from exc

        try:
            for stream_id in stream_ids:
                processed_video = menu_video.with_name(
                    f".{menu_video.stem}.spumux-{stream_id}{menu_video.suffix}"
                )
                if processed_video.exists():
                    processed_video.unlink()
                cmd = spumux_cmd + [
                    "-m",
                    "dvd",
                    "-P",
                    "-s",
                    str(stream_id),
                    str(xml_file),
                ]
                self.logger.debug(f"Executing spumux: {' '.join(cmd)}")
                with (
                    open(menu_video, "rb") as input_file,
                    open(processed_video, "wb") as processed_file,
                ):
                    result = subprocess.run(
                        cmd,
                        stdin=input_file,
                        stdout=processed_file,
                        stderr=subprocess.PIPE,
                        check=True,
                        cwd=output_dir,
                    )
                if result.stderr:
                    self.logger.debug(f"spumux stderr: {result.stderr.decode()}")
                if not processed_video.exists() or processed_video.stat().st_size <= 0:
                    raise SpumuxError(
                        f"spumux produced no output for stream {stream_id}"
                    )
                processed_video.replace(menu_video)
                self.logger.debug(
                    "Embedded button overlay stream %d in %s",
                    stream_id,
                    menu_video.name,
                )
            return SubtitleFiles(None, None)
        except subprocess.CalledProcessError as exc:
            self.logger.error(f"spumux failed with exit code {exc.returncode}")
            self.logger.error(
                f"spumux stderr: {exc.stderr.decode() if exc.stderr else ''}"
            )
            raise SpumuxError(f"spumux execution failed: {exc}") from exc
