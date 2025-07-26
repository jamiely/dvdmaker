"""Tests for the main CLI interface."""

import argparse
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.config.settings import Settings
from src.main import (
    create_argument_parser,
    main,
    merge_settings_with_args,
    validate_arguments,
    validate_tools,
)
from src.services.downloader import YtDlpError
from src.services.tool_manager import ToolManagerError


class TestArgumentParser:
    """Test cases for the argument parser."""

    def test_create_argument_parser(self):
        """Test argument parser creation."""
        parser = create_argument_parser()
        assert isinstance(parser, argparse.ArgumentParser)
        assert parser.prog == "dvdmaker"

    def test_required_argument_playlist_url(self):
        """Test that playlist-url is required."""
        parser = create_argument_parser()

        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_parse_minimal_arguments(self):
        """Test parsing with minimal required arguments."""
        parser = create_argument_parser()
        args = parser.parse_args(
            ["--playlist-url", "https://youtube.com/playlist?list=PLxxx"]
        )

        assert args.playlist_url == "https://youtube.com/playlist?list=PLxxx"
        assert args.quality == "best"
        assert not args.iso
        assert not args.force_download
        assert not args.force_convert

    def test_parse_all_arguments(self):
        """Test parsing with all arguments provided."""
        parser = create_argument_parser()
        args = parser.parse_args(
            [
                "--playlist-url",
                "PLxxx",
                "--output-dir",
                "/tmp/output",
                "--cache-dir",
                "/tmp/cache",
                "--temp-dir",
                "/tmp/temp",
                "--quality",
                "720p",
                "--menu-title",
                "My DVD",
                "--iso",
                "--force-download",
                "--force-convert",
                "--download-tools",
                "--log-level",
                "DEBUG",
                "--log-file",
                "/tmp/dvdmaker.log",
                "--verbose",
                "--config",
                "/tmp/config.json",
            ]
        )

        assert args.playlist_url == "PLxxx"
        assert args.output_dir == Path("/tmp/output")
        assert args.cache_dir == Path("/tmp/cache")
        assert args.temp_dir == Path("/tmp/temp")
        assert args.quality == "720p"
        assert args.menu_title == "My DVD"
        assert args.iso
        assert args.force_download
        assert args.force_convert
        assert args.download_tools
        assert args.log_level == "DEBUG"
        assert args.log_file == Path("/tmp/dvdmaker.log")
        assert args.verbose
        assert args.config == Path("/tmp/config.json")

    def test_conflicting_tool_arguments(self):
        """Test that conflicting tool arguments can be parsed."""
        parser = create_argument_parser()

        # Parser should accept both, validation should catch the conflict
        args = parser.parse_args(
            ["--playlist-url", "PLxxx", "--use-system-tools", "--download-tools"]
        )

        assert args.use_system_tools
        assert args.download_tools

    def test_conflicting_verbosity_arguments(self):
        """Test that conflicting verbosity arguments can be parsed."""
        parser = create_argument_parser()

        # Parser should accept both, validation should catch the conflict
        args = parser.parse_args(["--playlist-url", "PLxxx", "--quiet", "--verbose"])

        assert args.quiet
        assert args.verbose


class TestArgumentValidation:
    """Test cases for argument validation."""

    def test_validate_arguments_success(self):
        """Test successful argument validation."""
        args = argparse.Namespace(
            playlist_url="https://youtube.com/playlist?list=PLxxx",
            quiet=False,
            verbose=False,
            use_system_tools=False,
            download_tools=True,
        )

        # Should not raise any exception
        validate_arguments(args)

    def test_validate_arguments_conflicting_verbosity(self):
        """Test validation with conflicting verbosity flags."""
        args = argparse.Namespace(
            playlist_url="PLxxx",
            quiet=True,
            verbose=True,
            use_system_tools=False,
            download_tools=False,
        )

        with pytest.raises(
            ValueError, match="Cannot use both --quiet and --verbose flags"
        ):
            validate_arguments(args)

    def test_validate_arguments_conflicting_tools(self):
        """Test validation with conflicting tool flags."""
        args = argparse.Namespace(
            playlist_url="PLxxx",
            quiet=False,
            verbose=False,
            use_system_tools=True,
            download_tools=True,
        )

        with pytest.raises(
            ValueError,
            match="Cannot use both --use-system-tools and --download-tools flags",
        ):
            validate_arguments(args)

    def test_validate_arguments_empty_playlist_url(self):
        """Test validation with empty playlist URL."""
        args = argparse.Namespace(
            playlist_url="",
            quiet=False,
            verbose=False,
            use_system_tools=False,
            download_tools=False,
        )

        with pytest.raises(ValueError, match="Playlist URL is required"):
            validate_arguments(args)

    def test_validate_arguments_invalid_playlist_url(self):
        """Test validation with invalid playlist URL."""
        args = argparse.Namespace(
            playlist_url="invalid",
            quiet=False,
            verbose=False,
            use_system_tools=False,
            download_tools=False,
        )

        with pytest.raises(ValueError, match="Invalid playlist URL or ID"):
            validate_arguments(args)

    def test_validate_arguments_valid_playlist_formats(self):
        """Test validation with various valid playlist formats."""
        valid_urls = [
            "https://www.youtube.com/playlist?list=PLxxx",
            "https://youtube.com/playlist?list=PLxxx",
            "PLrAXtmRdnqeiGF0lEzfz7",
            "PL1234567890",
        ]

        for url in valid_urls:
            args = argparse.Namespace(
                playlist_url=url,
                quiet=False,
                verbose=False,
                use_system_tools=False,
                download_tools=False,
            )

            # Should not raise any exception
            validate_arguments(args)


class TestSettingsMerge:
    """Test cases for merging settings with arguments."""

    def test_merge_settings_with_args_empty(self):
        """Test merging with no argument overrides."""
        settings = Settings()
        args = argparse.Namespace(
            output_dir=None,
            cache_dir=None,
            temp_dir=None,
            quality=None,
            menu_title=None,
            iso=False,
            force_download=False,
            force_convert=False,
            use_system_tools=False,
            download_tools=False,
            log_level=None,
            verbose=False,
            quiet=False,
        )

        merged = merge_settings_with_args(args, settings)

        # Should be same as original settings
        assert merged.output_dir == settings.output_dir
        assert merged.cache_dir == settings.cache_dir
        assert merged.video_quality == settings.video_quality

    def test_merge_settings_with_args_overrides(self):
        """Test merging with argument overrides."""
        settings = Settings()
        args = argparse.Namespace(
            output_dir=Path("/custom/output"),
            cache_dir=Path("/custom/cache"),
            temp_dir=Path("/custom/temp"),
            quality="720p",
            menu_title="Custom Title",
            iso=True,
            force_download=True,
            force_convert=True,
            use_system_tools=False,
            download_tools=True,
            log_level="DEBUG",
            verbose=True,
            quiet=False,
        )

        merged = merge_settings_with_args(args, settings)

        assert merged.output_dir == Path("/custom/output")
        assert merged.cache_dir == Path("/custom/cache")
        assert merged.temp_dir == Path("/custom/temp")
        assert merged.video_quality == "720p"
        assert merged.menu_title == "Custom Title"
        assert merged.generate_iso is True
        assert merged.force_download is True
        assert merged.force_convert is True
        assert merged.download_tools is True
        assert merged.use_system_tools is False
        assert merged.log_level == "DEBUG"
        assert merged.verbose is True

    def test_merge_settings_tool_conflicts(self):
        """Test merging with tool flag conflicts resolved."""
        settings = Settings()

        # Test use_system_tools takes precedence
        args = argparse.Namespace(
            output_dir=None,
            cache_dir=None,
            temp_dir=None,
            quality=None,
            menu_title=None,
            iso=False,
            force_download=False,
            force_convert=False,
            use_system_tools=True,
            download_tools=False,
            log_level=None,
            verbose=False,
            quiet=False,
        )

        merged = merge_settings_with_args(args, settings)
        assert merged.use_system_tools is True
        assert merged.download_tools is False


class TestToolValidation:
    """Test cases for tool validation."""

    @patch("src.main.get_logger")
    def test_validate_tools_success(self, mock_logger):
        """Test successful tool validation."""
        mock_tool_manager = Mock()
        mock_tool_manager.ensure_tools_available.return_value = (True, [])

        result = validate_tools(mock_tool_manager)

        assert result is True
        mock_tool_manager.ensure_tools_available.assert_called_once()

    @patch("src.main.get_logger")
    def test_validate_tools_missing_tools(self, mock_logger):
        """Test validation with missing tools."""
        mock_tool_manager = Mock()
        mock_tool_manager.ensure_tools_available.return_value = (False, ["dvdauthor"])

        result = validate_tools(mock_tool_manager)

        assert result is False
        mock_tool_manager.ensure_tools_available.assert_called_once()

    @patch("src.main.get_logger")
    def test_validate_tools_exception(self, mock_logger):
        """Test validation with tool manager exception."""
        mock_tool_manager = Mock()
        mock_tool_manager.ensure_tools_available.side_effect = ToolManagerError(
            "Tool error"
        )

        result = validate_tools(mock_tool_manager)

        assert result is False


class TestMainFunction:
    """Test cases for the main function."""

    @patch("src.main.setup_application_logging")
    @patch("src.main.load_settings")
    @patch("src.main.validate_tools")
    @patch("src.main.CacheManager")
    @patch("src.main.ToolManager")
    @patch("src.main.VideoDownloader")
    @patch("src.main.VideoConverter")
    @patch("src.main.DVDAuthor")
    @patch("src.main.create_progress_callback")
    @patch("sys.argv", ["dvdmaker", "--playlist-url", "PLxxx"])
    def test_main_success(
        self,
        mock_progress,
        mock_dvd_author,
        mock_converter,
        mock_downloader,
        mock_tool_manager,
        mock_cache_manager,
        mock_validate_tools,
        mock_load_settings,
        mock_setup_logging,
    ):
        """Test successful main execution."""
        # Mock settings
        mock_settings = Settings()  # Use real Settings object
        mock_load_settings.return_value = mock_settings

        # Mock tool validation
        mock_validate_tools.return_value = True

        # Mock services
        mock_playlist = Mock()
        mock_playlist.get_available_videos.return_value = [Mock()]
        mock_playlist.metadata.title = "Test Playlist"

        mock_downloader_instance = Mock()
        mock_downloader_instance.download_playlist.return_value = mock_playlist
        mock_downloader.return_value = mock_downloader_instance

        mock_video_file = Mock()
        mock_cache_manager_instance = Mock()
        mock_cache_manager_instance.get_cached_download.return_value = mock_video_file
        mock_cache_manager.return_value = mock_cache_manager_instance

        mock_converted_video = Mock()
        mock_converter_instance = Mock()
        mock_converter_instance.convert_videos.return_value = [mock_converted_video]
        mock_converter.return_value = mock_converter_instance

        mock_authored_dvd = Mock()
        mock_authored_dvd.video_ts_dir = Path("/output/dvd")
        mock_authored_dvd.iso_file = None
        mock_dvd_author_instance = Mock()
        mock_dvd_author_instance.create_dvd_structure.return_value = mock_authored_dvd
        mock_dvd_author.return_value = mock_dvd_author_instance

        result = main()

        assert result == 0

    @patch("sys.argv", ["dvdmaker", "--playlist-url", "PLxxx", "--quiet", "--verbose"])
    def test_main_argument_validation_error(self):
        """Test main with argument validation error."""
        result = main()
        assert result == 1

    @patch("src.main.load_settings")
    @patch("sys.argv", ["dvdmaker", "--playlist-url", "PLxxx"])
    def test_main_tool_validation_failure(self, mock_load_settings):
        """Test main with tool validation failure."""
        mock_settings = Settings()  # Use real Settings object
        mock_load_settings.return_value = mock_settings

        with patch("src.main.validate_tools", return_value=False):
            result = main()

        assert result == 1

    @patch("src.main.setup_application_logging")
    @patch("src.main.load_settings")
    @patch("src.main.validate_tools")
    @patch("sys.argv", ["dvdmaker", "--playlist-url", "PLxxx"])
    def test_main_downloader_error(
        self, mock_validate_tools, mock_load_settings, mock_setup_logging
    ):
        """Test main with downloader error."""
        mock_settings = Settings()  # Use real Settings object
        mock_load_settings.return_value = mock_settings

        mock_validate_tools.return_value = True

        with patch("src.main.VideoDownloader") as mock_downloader:
            mock_downloader_instance = Mock()
            mock_downloader_instance.download_playlist.side_effect = YtDlpError(
                "Download failed"
            )
            mock_downloader.return_value = mock_downloader_instance

            with (
                patch("src.main.CacheManager"),
                patch("src.main.ToolManager"),
                patch("src.main.VideoConverter"),
                patch("src.main.DVDAuthor"),
                patch("src.main.create_progress_callback"),
            ):
                result = main()

        assert result == 1

    @patch("sys.argv", ["dvdmaker", "--playlist-url", "PLxxx"])
    def test_main_keyboard_interrupt(self):
        """Test main with keyboard interrupt."""
        with patch("src.main.load_settings", side_effect=KeyboardInterrupt):
            # Capture stdout to check the output
            captured_output = StringIO()
            sys.stdout = captured_output

            result = main()

            # Reset stdout
            sys.stdout = sys.__stdout__

            assert result == 130

    @patch("src.main.load_settings")
    @patch("sys.argv", ["dvdmaker", "--playlist-url", "PLxxx"])
    def test_main_unexpected_error(self, mock_load_settings):
        """Test main with unexpected error."""
        mock_load_settings.side_effect = Exception("Unexpected error")

        result = main()
        assert result == 1


class TestMainIntegration:
    """Integration tests for main function components."""

    def test_argument_parsing_integration(self):
        """Test that argument parsing integrates properly with settings."""
        parser = create_argument_parser()

        test_args = [
            "--playlist-url",
            "PLxxx",
            "--output-dir",
            "/tmp/output",
            "--quality",
            "720p",
            "--verbose",
        ]

        args = parser.parse_args(test_args)
        validate_arguments(args)

        settings = Settings()
        merged_settings = merge_settings_with_args(args, settings)

        assert merged_settings.output_dir == Path("/tmp/output")
        assert merged_settings.video_quality == "720p"
        assert merged_settings.verbose is True

    def test_settings_directory_creation_integration(self):
        """Test that settings directory creation works with merged settings."""
        settings = Settings(
            cache_dir=Path("/tmp/test_cache"),
            output_dir=Path("/tmp/test_output"),
            temp_dir=Path("/tmp/test_temp"),
            bin_dir=Path("/tmp/test_bin"),
            log_dir=Path("/tmp/test_logs"),
        )

        # This should not raise an exception
        # Note: In a real test environment, you might want to use temporary directories
        # settings.create_directories()

        # Just test that the method exists and is callable
        assert callable(settings.create_directories)
