"""Tests for the SpumuxService class."""

import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch

import pytest

from src.config.settings import Settings
from src.services.spumux_service import (
    ButtonConfig,
    ButtonGraphicError,
    ButtonOverlay,
    SpumuxNotAvailableError,
    SpumuxService,
    SubtitleFiles,
)


class TestButtonConfig:
    """Test the ButtonConfig data class."""

    def test_button_config_initialization(self):
        """Test ButtonConfig initialization."""
        config = ButtonConfig(
            name="button01",
            text="PLAY",
            position=(360, 400),
            size=(120, 40),
            navigation_command="g0=1;jump title 1;",
            color="#FFFFFF",
        )

        assert config.name == "button01"
        assert config.text == "PLAY"
        assert config.position == (360, 400)
        assert config.size == (120, 40)
        assert config.navigation_command == "g0=1;jump title 1;"
        assert config.color == "#FFFFFF"

    def test_button_config_coordinates(self):
        """Test ButtonConfig coordinate calculations."""
        config = ButtonConfig(
            name="button01",
            text="PLAY",
            position=(360, 400),  # Center position
            size=(120, 40),  # Width x Height
            navigation_command="g0=1;jump title 1;",
        )

        # Check calculated coordinates
        assert config.x0 == 300  # 360 - 120/2
        assert config.y0 == 380  # 400 - 40/2
        assert config.x1 == 420  # 360 + 120/2
        assert config.y1 == 420  # 400 + 40/2


class TestSubtitleFiles:
    """Test the SubtitleFiles data class."""

    def test_subtitle_files_initialization(self, tmp_path):
        """Test SubtitleFiles initialization."""
        sub_file = tmp_path / "test.sub"
        idx_file = tmp_path / "test.idx"

        subtitle_files = SubtitleFiles(sub_file, idx_file)

        assert subtitle_files.sub_file == sub_file
        assert subtitle_files.idx_file == idx_file

    def test_subtitle_files_exists_when_files_exist(self, tmp_path):
        """Test SubtitleFiles.exists when both files exist."""
        sub_file = tmp_path / "test.sub"
        idx_file = tmp_path / "test.idx"

        # Create the files
        sub_file.touch()
        idx_file.touch()

        subtitle_files = SubtitleFiles(sub_file, idx_file)
        assert subtitle_files.exists is True

    def test_subtitle_files_exists_when_files_missing(self, tmp_path):
        """Test SubtitleFiles.exists when files don't exist."""
        sub_file = tmp_path / "test.sub"
        idx_file = tmp_path / "test.idx"

        subtitle_files = SubtitleFiles(sub_file, idx_file)
        assert subtitle_files.exists is False


class TestButtonOverlay:
    """Test the ButtonOverlay data class."""

    def test_button_overlay_initialization(self, tmp_path):
        """Test ButtonOverlay initialization."""
        config = ButtonConfig(
            name="button01",
            text="PLAY",
            position=(360, 400),
            size=(120, 40),
            navigation_command="g0=1;jump title 1;",
        )

        graphic_file = tmp_path / "button01.png"
        subtitle_files = SubtitleFiles(tmp_path / "test.sub", tmp_path / "test.idx")

        overlay = ButtonOverlay(config, graphic_file, subtitle_files)

        assert overlay.button_config == config
        assert overlay.graphic_file == graphic_file
        assert overlay.subtitle_files == subtitle_files


class TestSpumuxService:
    """Test the SpumuxService class."""

    @pytest.fixture
    def settings(self, tmp_path):
        """Create test settings."""
        return Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
            button_enabled=True,
            button_text="PLAY",
            button_position=(360, 400),
            button_size=(120, 40),
            button_color="#FFFFFF",
        )

    @pytest.fixture
    def mock_tool_manager(self):
        """Create mock tool manager."""
        mock = Mock()
        mock.get_tool_command.return_value = ["spumux"]
        return mock

    @pytest.fixture
    def mock_cache_manager(self):
        """Create mock cache manager."""
        return Mock()

    @pytest.fixture
    def spumux_service(self, settings, mock_tool_manager, mock_cache_manager):
        """Create SpumuxService instance."""
        return SpumuxService(settings, mock_tool_manager, mock_cache_manager)

    def test_spumux_service_initialization(
        self, settings, mock_tool_manager, mock_cache_manager
    ):
        """Test SpumuxService initialization."""
        service = SpumuxService(settings, mock_tool_manager, mock_cache_manager)

        assert service.settings == settings
        assert service.tool_manager == mock_tool_manager
        assert service.cache_manager == mock_cache_manager
        assert service.logger is not None

    def test_is_available_with_all_dependencies(self, spumux_service):
        """Test is_available when all dependencies are present."""
        with patch("src.services.spumux_service.PIL_AVAILABLE", True):
            assert spumux_service.is_available() is True

    def test_is_available_without_pil(self, spumux_service):
        """Test is_available when PIL is not available."""
        with patch("src.services.spumux_service.PIL_AVAILABLE", False):
            assert spumux_service.is_available() is False

    def test_is_available_without_spumux(self, spumux_service):
        """Test is_available when spumux is not available."""
        spumux_service.tool_manager.get_tool_command.side_effect = Exception(
            "spumux not found"
        )

        with patch("src.services.spumux_service.PIL_AVAILABLE", True):
            assert spumux_service.is_available() is False

    def test_create_button_config_with_defaults(self, spumux_service):
        """Test _create_button_config with default settings."""
        config = spumux_service._create_button_config()

        assert config.name == "button01"
        assert config.text == "Play all"  # DVDStyler text
        assert config.position == (169, 298)  # DVDStyler center position
        assert config.size == (99, 24)  # DVDStyler dimensions
        assert config.color == "#FFFFFF"
        assert config.navigation_command == "g0=1;jump title 1;"

    def test_create_button_config_with_custom_settings(
        self, mock_tool_manager, mock_cache_manager, tmp_path
    ):
        """Test _create_button_config always uses DVDStyler for car compatibility."""
        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
            button_text="START",
            button_position=(100, 200),
            button_size=(80, 30),
            button_color="#FF0000",
        )

        service = SpumuxService(settings, mock_tool_manager, mock_cache_manager)
        config = service._create_button_config()

        # DVDStyler settings override custom settings for car DVD compatibility
        assert config.text == "Play all"  # Always DVDStyler text
        assert config.position == (169, 298)  # Always DVDStyler position
        assert config.size == (99, 24)  # Always DVDStyler size
        assert config.color == "#FFFFFF"  # Always DVDStyler color

    @patch("src.services.spumux_service.PIL_AVAILABLE", True)
    @patch("src.services.spumux_service.Image")
    def test_create_button_graphics_success(self, mock_image, spumux_service, tmp_path):
        """Test _create_button_graphics successful creation."""
        # Set up mocks
        mock_img = Mock()
        mock_image.new.return_value = mock_img
        mock_img.load.return_value = None  # Image.load() returns pixel access or None

        config = ButtonConfig(
            name="button01",
            text="PLAY",
            position=(360, 400),
            size=(120, 40),
            navigation_command="g0=1;jump title 1;",
            color="#FFFFFF",
        )

        output_dir = tmp_path / "buttons"
        graphic_files = spumux_service._create_button_graphics(config, output_dir)

        # Check that directory was created
        assert output_dir.exists()

        # Check that image methods were called (3 times for normal, highlight, select)
        assert mock_image.new.call_count == 3
        assert mock_img.save.call_count == 3

        # Check return paths (normal, highlight, select)
        normal_file, highlight_file, select_file = graphic_files
        assert normal_file == output_dir / "button01_buttons.png"
        assert highlight_file == output_dir / "button01_highlight.png"
        assert select_file == output_dir / "button01_select.png"

    def test_create_button_graphics_without_pil(self, spumux_service, tmp_path):
        """Test _create_button_graphics when PIL is not available."""
        with patch("src.services.spumux_service.PIL_AVAILABLE", False):
            config = ButtonConfig(
                name="button01",
                text="PLAY",
                position=(360, 400),
                size=(120, 40),
                navigation_command="g0=1;jump title 1;",
            )

            with pytest.raises(ButtonGraphicError, match="PIL/Pillow not available"):
                spumux_service._create_button_graphics(config, tmp_path)

    def test_generate_spumux_xml(self, mock_tool_manager, mock_cache_manager, tmp_path):
        """Test _generate_spumux_xml creates valid XML."""
        # Setup cache_manager mock
        mock_cache_manager.cache_dir = tmp_path / "cache"

        service = SpumuxService(Settings(), mock_tool_manager, mock_cache_manager)

        # Use the actual DVDStyler button configuration
        config = service._create_button_config()

        # Create graphic files
        normal_file = tmp_path / "button01_buttons.png"
        highlight_file = tmp_path / "button01_highlight.png"
        select_file = tmp_path / "button01_select.png"
        normal_file.touch()
        highlight_file.touch()
        select_file.touch()

        graphic_files = (normal_file, highlight_file, select_file)

        xml_file = service._generate_spumux_xml(config, graphic_files, tmp_path)

        # Check file was created
        assert xml_file.exists()
        assert xml_file.name == "spumux_config.xml"

        # Parse and validate XML
        tree = ET.parse(xml_file)
        root = tree.getroot()

        assert root.tag == "subpictures"
        stream = root.find("stream")
        assert stream is not None

        spu = stream.find("spu")
        assert spu is not None
        assert spu.get("start") == "00:00:00.00"
        assert spu.get("image") == str(normal_file)
        assert spu.get("highlight") == str(highlight_file)
        assert spu.get("select") == str(select_file)
        assert spu.get("force") == "yes"
        # DVDStyler uses absolute coordinates, no offsets

        button = spu.find("button")
        assert button is not None
        assert button.get("name") == "button01"
        # DVDStyler coordinates (120,286) to (218,310)
        assert button.get("x0") == "120"
        assert button.get("y0") == "286"
        assert button.get("x1") == "218"
        assert button.get("y1") == "310"

    @patch("src.services.spumux_service.subprocess.run")
    def test_execute_spumux_success(self, mock_run, spumux_service, tmp_path):
        """Test _execute_spumux successful execution."""
        # Set up mock
        mock_result = Mock()
        mock_result.stderr = b"spumux completed"
        mock_run.return_value = mock_result

        # Create input files
        xml_file = tmp_path / "config.xml"
        xml_file.touch()
        menu_video = tmp_path / "menu.mpg"
        menu_video.touch()

        # Create processed video file that spumux would create
        processed_video = tmp_path / "menu_with_buttons.mpv"
        processed_video.touch()

        subtitle_files = spumux_service._execute_spumux(xml_file, menu_video, tmp_path)

        # Check spumux was called correctly
        expected_cmd = ["spumux", "-m", "dvd", "-P", "-s", "0", str(xml_file)]
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == expected_cmd
        assert call_args[1]["check"] is True
        assert call_args[1]["cwd"] == tmp_path

        # Check that subtitle files are None (spumux embeds data in video stream)
        assert subtitle_files.sub_file is None
        assert subtitle_files.idx_file is None
        assert not subtitle_files.exists

    def test_execute_spumux_tool_not_available(self, spumux_service, tmp_path):
        """Test _execute_spumux when spumux tool is not available."""
        spumux_service.tool_manager.get_tool_command.side_effect = Exception(
            "spumux not found"
        )

        xml_file = tmp_path / "config.xml"
        menu_video = tmp_path / "menu.mpv"

        with pytest.raises(SpumuxNotAvailableError):
            spumux_service._execute_spumux(xml_file, menu_video, tmp_path)

    def test_create_button_overlay_disabled(self, spumux_service, tmp_path):
        """Test create_button_overlay when buttons are disabled."""
        spumux_service.settings.button_enabled = False

        menu_video = tmp_path / "menu.mpg"
        result = spumux_service.create_button_overlay(menu_video, tmp_path)

        assert result is None

    def test_create_button_overlay_service_not_available(
        self, spumux_service, tmp_path
    ):
        """Test create_button_overlay when service is not available."""
        with patch.object(spumux_service, "is_available", return_value=False):
            menu_video = tmp_path / "menu.mpg"
            result = spumux_service.create_button_overlay(menu_video, tmp_path)

            assert result is None

    @patch("src.services.spumux_service.PIL_AVAILABLE", True)
    def test_create_button_overlay_success(
        self, mock_tool_manager, mock_cache_manager, tmp_path
    ):
        """Test create_button_overlay successful execution."""
        # Setup cache_manager mock
        mock_cache_manager.cache_dir = tmp_path / "cache"

        spumux_service = SpumuxService(
            Settings(), mock_tool_manager, mock_cache_manager
        )

        menu_video = tmp_path / "menu.mpv"
        menu_video.touch()

        # Mock the individual methods to return expected results
        with (
            patch.object(spumux_service, "_create_button_graphics") as mock_graphic,
            patch.object(spumux_service, "_generate_spumux_xml") as mock_xml,
            patch.object(spumux_service, "_execute_spumux") as mock_execute,
        ):

            graphic_files = (
                tmp_path / "button01_buttons.png",
                tmp_path / "button01_highlight.png",
                tmp_path / "button01_select.png",
            )
            xml_file = tmp_path / "config.xml"
            subtitle_files = SubtitleFiles(tmp_path / "menu.sub", tmp_path / "menu.idx")

            mock_graphic.return_value = graphic_files
            mock_xml.return_value = xml_file
            mock_execute.return_value = subtitle_files

            overlay = spumux_service.create_button_overlay(menu_video, tmp_path)

            # Check that all methods were called
            mock_graphic.assert_called_once()
            mock_xml.assert_called_once()
            mock_execute.assert_called_once()

            # Check overlay result
            assert overlay is not None
            assert overlay.graphic_file == graphic_files[0]  # Uses normal state file
            assert overlay.subtitle_files == subtitle_files
            assert overlay.button_config.name == "button01"

    def test_create_button_overlay_handles_exception(self, spumux_service, tmp_path):
        """Test create_button_overlay handles exceptions gracefully."""
        menu_video = tmp_path / "menu.mpg"

        # Mock _create_button_graphics to raise an exception
        with patch.object(
            spumux_service,
            "_create_button_graphics",
            side_effect=Exception("Test error"),
        ):
            overlay = spumux_service.create_button_overlay(menu_video, tmp_path)

            # Should return None instead of raising exception
            assert overlay is None


class TestSpumuxServiceIntegration:
    """Integration tests for SpumuxService."""

    @pytest.fixture
    def integration_settings(self, tmp_path):
        """Create settings for integration testing."""
        return Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
            button_enabled=True,
            button_text="TEST",
            button_position=(400, 300),
            button_size=(100, 50),
            button_color="#00FF00",
        )

    def test_full_workflow_without_external_tools(self, integration_settings, tmp_path):
        """Test full workflow without requiring external tools."""
        mock_tool_manager = Mock()
        mock_cache_manager = Mock()
        mock_cache_manager.cache_dir = tmp_path / "cache"

        service = SpumuxService(
            integration_settings, mock_tool_manager, mock_cache_manager
        )

        # Test button config creation - DVDStyler settings override custom settings
        config = service._create_button_config()
        assert config.text == "Play all"  # Always DVDStyler text for compatibility
        assert config.position == (169, 298)  # Always DVDStyler position
        assert config.size == (99, 24)  # Always DVDStyler size
        assert config.color == "#FFFFFF"  # Always DVDStyler color

        # Test XML generation
        normal_file = tmp_path / "button01_buttons.png"
        highlight_file = tmp_path / "button01_highlight.png"
        select_file = tmp_path / "button01_select.png"
        normal_file.touch()
        highlight_file.touch()
        select_file.touch()

        graphic_files = (normal_file, highlight_file, select_file)
        xml_file = service._generate_spumux_xml(config, graphic_files, tmp_path)
        assert xml_file.exists()

        # Parse XML and verify structure
        tree = ET.parse(xml_file)
        root = tree.getroot()
        assert root.tag == "subpictures"

        # Find SPU element and verify DVDStyler-style attributes
        spu = root.find(".//spu")
        assert spu is not None
        assert spu.get("start") == "00:00:00.00"
        assert spu.get("image") == str(normal_file)
        assert spu.get("highlight") == str(highlight_file)
        assert spu.get("select") == str(select_file)
        assert spu.get("force") == "yes"

        # Find button element and verify DVDStyler absolute coordinates
        button = root.find(".//button")
        assert button is not None
        assert button.get("name") == "button01"
        # DVDStyler coordinates (120,286) to (218,310)
        assert button.get("x0") == "120"
        assert button.get("y0") == "286"
        assert button.get("x1") == "218"
        assert button.get("y1") == "310"


class TestSpumuxServiceEdgeCases:
    """Test edge cases and error conditions."""

    def test_button_config_with_zero_size(self):
        """Test ButtonConfig with zero size dimensions."""
        config = ButtonConfig(
            name="test",
            text="TEST",
            position=(100, 100),
            size=(0, 0),
            navigation_command="jump title 1;",
        )

        # Should still calculate coordinates, even if size is zero
        assert config.x0 == 100  # 100 - 0/2
        assert config.y0 == 100  # 100 - 0/2
        assert config.x1 == 100  # 100 + 0/2
        assert config.y1 == 100  # 100 + 0/2

    def test_button_config_with_negative_position(self):
        """Test ButtonConfig with negative position."""
        config = ButtonConfig(
            name="test",
            text="TEST",
            position=(-10, -20),
            size=(40, 30),
            navigation_command="jump title 1;",
        )

        assert config.x0 == -30  # -10 - 40/2
        assert config.y0 == -35  # -20 - 30/2
        assert config.x1 == 10  # -10 + 40/2
        assert config.y1 == -5  # -20 + 30/2

    def test_subtitle_files_with_nonexistent_parent_directory(self, tmp_path):
        """Test SubtitleFiles with files in nonexistent directories."""
        nonexistent_dir = tmp_path / "nonexistent"
        sub_file = nonexistent_dir / "test.sub"
        idx_file = nonexistent_dir / "test.idx"

        subtitle_files = SubtitleFiles(sub_file, idx_file)

        # Should not raise exception, just return False for exists
        assert subtitle_files.exists is False

    def test_spumux_service_with_missing_settings_attributes(self, tmp_path):
        """Test SpumuxService when settings lack button attributes."""
        # Create minimal settings without button attributes
        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        mock_tool_manager = Mock()
        mock_cache_manager = Mock()

        service = SpumuxService(settings, mock_tool_manager, mock_cache_manager)

        # Should use DVDStyler defaults for car DVD compatibility
        config = service._create_button_config()
        assert config.text == "Play all"  # DVDStyler text (overrides settings)
        assert config.position == (169, 298)  # DVDStyler position (overrides settings)
        assert config.size == (99, 24)  # DVDStyler size (overrides settings)
        assert config.color == "#FFFFFF"  # DVDStyler color
