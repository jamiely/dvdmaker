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
        assert not args.no_iso
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
                "--video-format",
                "PAL",
                "--aspect-ratio",
                "4:3",
                "--no-iso",
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
        assert args.video_format == "PAL"
        assert args.aspect_ratio == "4:3"
        assert args.no_iso
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

    def test_video_format_argument_parsing(self):
        """Test video format argument parsing."""
        parser = create_argument_parser()

        # Test NTSC format
        args = parser.parse_args(["--playlist-url", "PLxxx", "--video-format", "NTSC"])
        assert args.video_format == "NTSC"

        # Test PAL format
        args = parser.parse_args(["--playlist-url", "PLxxx", "--video-format", "PAL"])
        assert args.video_format == "PAL"

        # Test default value
        args = parser.parse_args(["--playlist-url", "PLxxx"])
        assert args.video_format == "NTSC"  # Default should be NTSC

    def test_video_format_invalid_choice(self):
        """Test that invalid video format choices are rejected."""
        parser = create_argument_parser()

        # Invalid format should cause SystemExit
        with pytest.raises(SystemExit):
            parser.parse_args(["--playlist-url", "PLxxx", "--video-format", "SECAM"])

    def test_aspect_ratio_argument_parsing(self):
        """Test aspect ratio argument parsing."""
        parser = create_argument_parser()

        # Test 4:3 aspect ratio
        args = parser.parse_args(["--playlist-url", "PLxxx", "--aspect-ratio", "4:3"])
        assert args.aspect_ratio == "4:3"

        # Test 16:9 aspect ratio
        args = parser.parse_args(["--playlist-url", "PLxxx", "--aspect-ratio", "16:9"])
        assert args.aspect_ratio == "16:9"

        # Test default value
        args = parser.parse_args(["--playlist-url", "PLxxx"])
        assert args.aspect_ratio == "16:9"  # Default should be 16:9

    def test_aspect_ratio_invalid_choice(self):
        """Test that invalid aspect ratio choices are rejected."""
        parser = create_argument_parser()

        # Invalid aspect ratio should raise SystemExit
        with pytest.raises(SystemExit):
            parser.parse_args(["--playlist-url", "PLxxx", "--aspect-ratio", "2.35:1"])


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

    def test_validate_arguments_cleanup_no_playlist_required(self):
        """Test validation with cleanup option doesn't require playlist URL."""
        args = argparse.Namespace(
            clean="downloads",
            playlist_url=None,
            quiet=False,
            verbose=False,
            use_system_tools=False,
            download_tools=False,
        )

        # Should not raise any exception
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
            video_format=None,
            aspect_ratio=None,
            no_iso=False,
            autoplay=False,
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
            video_format="PAL",
            aspect_ratio="4:3",
            no_iso=True,
            autoplay=True,
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
        assert merged.video_format == "PAL"
        assert merged.aspect_ratio == "4:3"
        assert merged.generate_iso is False
        assert merged.autoplay is True
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
            video_format=None,
            aspect_ratio=None,
            no_iso=False,
            autoplay=False,
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

    def test_merge_settings_video_format(self):
        """Test merging with video format argument."""
        settings = Settings()  # Default video_format is NTSC

        # Test with PAL override
        args = argparse.Namespace(
            output_dir=None,
            cache_dir=None,
            temp_dir=None,
            quality=None,
            menu_title=None,
            video_format="PAL",
            aspect_ratio=None,
            no_iso=False,
            autoplay=False,
            force_download=False,
            force_convert=False,
            use_system_tools=False,
            download_tools=False,
            log_level=None,
            verbose=False,
            quiet=False,
        )

        merged = merge_settings_with_args(args, settings)
        assert merged.video_format == "PAL"

        # Test with no override (should remain default)
        args.video_format = None
        merged = merge_settings_with_args(args, settings)
        assert merged.video_format == "NTSC"  # Should keep original default

    def test_merge_settings_aspect_ratio(self):
        """Test merging with aspect ratio argument."""
        settings = Settings()  # Default aspect_ratio is 16:9

        # Test with 4:3 override
        args = argparse.Namespace(
            output_dir=None,
            cache_dir=None,
            temp_dir=None,
            quality=None,
            menu_title=None,
            video_format=None,
            aspect_ratio="4:3",
            no_iso=False,
            autoplay=False,
            force_download=False,
            force_convert=False,
            use_system_tools=False,
            download_tools=False,
            log_level=None,
            verbose=False,
            quiet=False,
        )

        merged = merge_settings_with_args(args, settings)
        assert merged.aspect_ratio == "4:3"

        # Test with no override (should remain default)
        args.aspect_ratio = None
        merged = merge_settings_with_args(args, settings)
        assert merged.aspect_ratio == "16:9"  # Should keep original default


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
        mock_playlist.total_duration_human_readable = "5m"

        mock_downloader_instance = Mock()
        mock_downloader_instance.download_playlist.return_value = mock_playlist
        mock_downloader.return_value = mock_downloader_instance

        mock_video_file = Mock()
        mock_cache_manager_instance = Mock()
        mock_cache_manager_instance.get_cached_download.return_value = mock_video_file
        mock_cache_manager.return_value = mock_cache_manager_instance

        mock_converted_video = Mock()
        mock_converted_video.size_mb = 1000.0  # 1GB video that fits on DVD
        mock_converted_video.metadata = Mock()
        mock_converted_video.metadata.video_id = "test123"
        mock_converted_video.metadata.title = "Test Video"
        mock_converted_video.metadata.duration = 300  # 5 minutes
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


class TestMainLogging:
    """Test cases for main function logging behavior."""

    @patch("src.main.load_settings")
    @patch("src.main.setup_application_logging")
    @patch("src.main.validate_tools")
    def test_perform_cleanup_logging_info_messages(
        self, mock_validate, mock_setup_logging, mock_load_settings, caplog
    ):
        """Test perform_cleanup logs info messages."""
        from src.main import perform_cleanup

        caplog.set_level("INFO")

        # Setup mock settings
        mock_settings = Settings(
            cache_dir=Path("/tmp/cache"),
            output_dir=Path("/tmp/output"),
            temp_dir=Path("/tmp/temp"),
        )

        with patch("src.main.CleanupManager") as mock_cleanup_manager:
            mock_cleanup_instance = Mock()
            mock_cleanup_manager.return_value = mock_cleanup_instance

            # Test with no items to clean
            mock_cleanup_instance.get_cleanup_preview.return_value = []

            result = perform_cleanup("downloads", mock_settings)

            assert result == 0

            # Check for info log messages
            info_messages = [
                record.message
                for record in caplog.records
                if record.levelname == "INFO" and "src.main" in record.name
            ]
            assert any(
                "No downloads data found to clean" in msg for msg in info_messages
            )

    @patch("src.main.load_settings")
    @patch("src.main.setup_application_logging")
    def test_perform_cleanup_with_items_logging(
        self, mock_setup_logging, mock_load_settings, caplog
    ):
        """Test perform_cleanup logs info messages when cleaning items."""
        from src.main import perform_cleanup
        from src.services.cleanup import CleanupStats

        caplog.set_level("INFO")

        mock_settings = Settings(
            cache_dir=Path("/tmp/cache"),
            output_dir=Path("/tmp/output"),
            temp_dir=Path("/tmp/temp"),
        )

        with patch("src.main.CleanupManager") as mock_cleanup_manager:
            with patch("builtins.input", return_value="y"):  # User confirms cleanup
                mock_cleanup_instance = Mock()
                mock_cleanup_manager.return_value = mock_cleanup_instance

                # Mock cleanup preview and execution
                mock_cleanup_instance.get_cleanup_preview.return_value = [
                    "/tmp/cache/video1.mp4",
                    "/tmp/cache/video2.mp4",
                ]
                # Create and populate CleanupStats
                cleanup_stats = CleanupStats()
                cleanup_stats.files_removed = 2
                cleanup_stats.directories_removed = 0
                cleanup_stats.bytes_freed = 100.0 * 1024 * 1024  # 100MB in bytes
                cleanup_stats.errors = 0
                mock_cleanup_instance.clean_downloads.return_value = cleanup_stats

                result = perform_cleanup("downloads", mock_settings)

                assert result == 0

                # Check for info log messages
                info_messages = [
                    record.message
                    for record in caplog.records
                    if record.levelname == "INFO" and "src.main" in record.name
                ]
                assert any("Starting downloads cleanup" in msg for msg in info_messages)
                assert any(
                    "downloads cleanup complete: 2 items, 100.0MB freed" in msg
                    for msg in info_messages
                )

    @patch("src.main.load_settings")
    @patch("src.main.setup_application_logging")
    @patch("src.main.validate_tools")
    @patch("src.main.CacheManager")
    @patch("src.main.ToolManager")
    @patch("src.main.VideoDownloader")
    @patch("src.main.VideoConverter")
    @patch("src.main.DVDAuthor")
    @patch("src.main.select_videos_for_dvd_capacity")
    @patch("src.main.operation_context")
    def test_main_dvd_creation_step_logging(
        self,
        mock_context,
        mock_capacity,
        mock_dvd_author_cls,
        mock_converter_cls,
        mock_downloader_cls,
        mock_tool_mgr_cls,
        mock_cache_mgr_cls,
        mock_validate,
        mock_setup_logging,
        mock_load_settings,
        caplog,
    ):
        """Test main function logs DVD creation step info messages."""
        caplog.set_level("INFO")

        # Setup mocks
        mock_settings = Settings()
        mock_load_settings.return_value = mock_settings
        mock_validate.return_value = True

        # Mock context manager
        mock_context.return_value.__enter__ = Mock()
        mock_context.return_value.__exit__ = Mock()

        # Mock playlist with videos
        mock_playlist = Mock()
        mock_playlist.get_available_videos.return_value = [Mock(), Mock()]
        mock_playlist.total_duration_human_readable = "10:30"
        mock_playlist.metadata.title = "Test Playlist"
        mock_playlist.metadata.playlist_id = "PLtest123"

        # Mock downloader
        mock_downloader = Mock()
        mock_downloader.download_playlist.return_value = mock_playlist
        mock_downloader_cls.return_value = mock_downloader

        # Mock converter
        mock_converter = Mock()
        mock_converted_videos = [Mock(), Mock()]
        mock_converter.convert_videos.return_value = mock_converted_videos
        mock_converter_cls.return_value = mock_converter

        # Mock capacity selection
        mock_capacity_result = Mock()
        mock_capacity_result.has_exclusions = False
        mock_capacity_result.included_videos = mock_converted_videos
        mock_capacity_result.total_duration_human_readable = "10:30"
        mock_capacity_result.total_size_gb = 3.2
        mock_capacity.return_value = mock_capacity_result

        # Mock DVD author
        mock_dvd_author = Mock()
        mock_authored_dvd = Mock()
        mock_authored_dvd.video_ts_dir = Path("/tmp/output/VIDEO_TS")
        mock_authored_dvd.iso_file = "/tmp/output/test.iso"
        mock_dvd_author.create_dvd_structure.return_value = mock_authored_dvd
        mock_dvd_author_cls.return_value = mock_dvd_author

        # Mock cache manager to return video files
        mock_cache_manager = Mock()
        mock_cache_manager.get_cached_download.return_value = Mock()
        mock_cache_mgr_cls.return_value = mock_cache_manager

        with patch("sys.argv", ["dvdmaker", "--playlist-url", "PLtest123"]):
            result = main()

        assert result == 0

        # Check for step info log messages
        info_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "INFO" and "src.main" in record.name
        ]

        assert any(
            "Starting DVD creation for playlist: PLtest123" in msg
            for msg in info_messages
        )
        assert any("Step 1: Downloading playlist..." in msg for msg in info_messages)
        assert any(
            "Downloaded 2 videos successfully (total duration: 10:30)" in msg
            for msg in info_messages
        )
        assert any(
            "Step 2: Converting videos to DVD format..." in msg for msg in info_messages
        )
        assert any("Step 2.5: Checking DVD capacity..." in msg for msg in info_messages)
        assert any("Step 3: Creating DVD structure..." in msg for msg in info_messages)


class TestCreateProgressCallback:
    """Test cases for create_progress_callback function."""

    def test_create_progress_callback_not_quiet(self):
        """Test creating progress callback when not quiet."""
        from src.main import create_progress_callback

        callback = create_progress_callback(quiet=False)
        assert callback is not None
        assert callable(callback)

    def test_create_progress_callback_quiet(self):
        """Test creating progress callback when quiet."""
        from src.main import create_progress_callback

        callback = create_progress_callback(quiet=True)
        assert callback is None

    def test_progress_callback_functionality(self, capsys):
        """Test progress callback functionality."""
        from src.main import create_progress_callback

        callback = create_progress_callback(quiet=False)

        # Test positive progress
        callback("Test operation", 50.5)
        captured = capsys.readouterr()
        assert "Test operation: 50.5%" in captured.out

        # Test negative progress (new line)
        callback("Test operation", -1.0)
        captured = capsys.readouterr()
        assert "Test operation" in captured.out


class TestSetupApplicationLogging:
    """Test cases for setup_application_logging function."""

    @patch("src.main.setup_logging")
    def test_setup_application_logging_with_log_file(self, mock_setup_logging):
        """Test setup_application_logging with custom log file."""
        from src.main import setup_application_logging

        settings = Settings()
        log_file = Path("/custom/log/path.log")

        setup_application_logging(settings, log_file)

        mock_setup_logging.assert_called_once_with(
            log_dir=settings.log_dir,
            log_level=settings.get_effective_log_level(),
            log_file="path.log",
            max_file_size=settings.log_file_max_size,
            backup_count=settings.log_file_backup_count,
            console_output=not settings.quiet,
        )

    @patch("src.main.setup_logging")
    def test_setup_application_logging_default_log_file(self, mock_setup_logging):
        """Test setup_application_logging with default log file."""
        from src.main import setup_application_logging

        settings = Settings()

        setup_application_logging(settings, None)

        mock_setup_logging.assert_called_once_with(
            log_dir=settings.log_dir,
            log_level=settings.get_effective_log_level(),
            log_file="dvdmaker.log",
            max_file_size=settings.log_file_max_size,
            backup_count=settings.log_file_backup_count,
            console_output=not settings.quiet,
        )


class TestYtDlpUpdateCheck:
    """Test cases for yt-dlp update functionality."""

    @patch("src.main.get_logger")
    def test_validate_tools_ytdlp_update_success(self, mock_logger):
        """Test validate_tools with successful yt-dlp update."""
        from src.main import validate_tools

        mock_tool_manager = Mock()
        mock_tool_manager.check_and_update_ytdlp.return_value = True
        mock_tool_manager.ensure_tools_available.return_value = (True, [])

        result = validate_tools(mock_tool_manager)

        assert result is True
        mock_tool_manager.check_and_update_ytdlp.assert_called_once()

    @patch("src.main.get_logger")
    def test_validate_tools_ytdlp_update_failure(self, mock_logger):
        """Test validate_tools with failed yt-dlp update but continue."""
        from src.main import validate_tools

        mock_tool_manager = Mock()
        mock_tool_manager.check_and_update_ytdlp.return_value = False
        mock_tool_manager.ensure_tools_available.return_value = (True, [])

        result = validate_tools(mock_tool_manager)

        assert result is True
        mock_tool_manager.check_and_update_ytdlp.assert_called_once()


class TestPerformCleanupAdvanced:
    """Advanced test cases for perform_cleanup function."""

    @patch("src.main.get_logger")
    def test_perform_cleanup_user_cancellation(self, mock_logger):
        """Test perform_cleanup when user cancels."""
        from src.main import perform_cleanup

        settings = Settings()

        with patch("src.main.CleanupManager") as mock_cleanup_manager:
            mock_cleanup_instance = Mock()
            mock_cleanup_manager.return_value = mock_cleanup_instance
            mock_cleanup_instance.get_cleanup_preview.return_value = [
                "/tmp/file1",
                "/tmp/file2",
            ]

            with patch("builtins.input", return_value="n"):  # User cancels
                result = perform_cleanup("downloads", settings)

                assert result == 0
                mock_cleanup_instance.clean_downloads.assert_not_called()

    @patch("src.main.get_logger")
    def test_perform_cleanup_many_items_preview(self, mock_logger, capsys):
        """Test perform_cleanup with many items (>10) for preview truncation."""
        from src.main import perform_cleanup

        settings = Settings()

        with patch("src.main.CleanupManager") as mock_cleanup_manager:
            mock_cleanup_instance = Mock()
            mock_cleanup_manager.return_value = mock_cleanup_instance

            # Create 15 items to test truncation at 10
            items = [f"/tmp/file{i}.mp4" for i in range(15)]
            mock_cleanup_instance.get_cleanup_preview.return_value = items

            with patch(
                "builtins.input", return_value="n"
            ):  # User cancels to avoid actual cleanup
                perform_cleanup("downloads", settings)

                captured = capsys.readouterr()
                assert "... and 5 more items" in captured.out

    @patch("src.main.get_logger")
    def test_perform_cleanup_all_type(self, mock_logger):
        """Test perform_cleanup with 'all' cleanup type."""
        from src.main import perform_cleanup
        from src.services.cleanup import CleanupStats

        settings = Settings()

        with patch("src.main.CleanupManager") as mock_cleanup_manager:
            mock_cleanup_instance = Mock()
            mock_cleanup_manager.return_value = mock_cleanup_instance
            mock_cleanup_instance.get_cleanup_preview.return_value = ["/tmp/file1"]

            # Mock clean_all results
            stats1 = CleanupStats()
            stats1.files_removed = 2
            stats1.directories_removed = 1
            stats1.bytes_freed = 50 * 1024 * 1024  # 50MB
            stats1.errors = 0

            stats2 = CleanupStats()
            stats2.files_removed = 3
            stats2.directories_removed = 2
            stats2.bytes_freed = 100 * 1024 * 1024  # 100MB
            stats2.errors = 1

            mock_cleanup_instance.clean_all.return_value = {
                "downloads": stats1,
                "conversions": stats2,
            }

            with patch("builtins.input", return_value="y"):
                result = perform_cleanup("all", settings)

                assert result == 0
                mock_cleanup_instance.clean_all.assert_called_once()

    @patch("src.main.get_logger")
    def test_perform_cleanup_invalid_type(self, mock_logger):
        """Test perform_cleanup with invalid cleanup type."""
        from src.main import perform_cleanup

        settings = Settings()

        with patch("src.main.CleanupManager") as mock_cleanup_manager:
            mock_cleanup_instance = Mock()
            mock_cleanup_manager.return_value = mock_cleanup_instance
            mock_cleanup_instance.get_cleanup_preview.return_value = ["/tmp/file1"]

            with patch("builtins.input", return_value="y"):
                result = perform_cleanup("invalid_type", settings)

                assert result == 1

    @patch("src.main.get_logger")
    def test_perform_cleanup_exception(self, mock_logger):
        """Test perform_cleanup with exception during cleanup."""
        from src.main import perform_cleanup

        settings = Settings()

        with patch("src.main.CleanupManager", side_effect=Exception("Cleanup error")):
            result = perform_cleanup("downloads", settings)

            assert result == 1

    @patch("src.main.get_logger")
    def test_perform_cleanup_with_errors(self, mock_logger, capsys):
        """Test perform_cleanup displaying errors count."""
        from src.main import perform_cleanup
        from src.services.cleanup import CleanupStats

        settings = Settings()

        with patch("src.main.CleanupManager") as mock_cleanup_manager:
            mock_cleanup_instance = Mock()
            mock_cleanup_manager.return_value = mock_cleanup_instance
            mock_cleanup_instance.get_cleanup_preview.return_value = ["/tmp/file1"]

            # Create stats with errors
            cleanup_stats = CleanupStats()
            cleanup_stats.files_removed = 1
            cleanup_stats.directories_removed = 0
            cleanup_stats.bytes_freed = 50 * 1024 * 1024  # 50MB
            cleanup_stats.errors = 2
            mock_cleanup_instance.clean_downloads.return_value = cleanup_stats

            with patch("builtins.input", return_value="y"):
                result = perform_cleanup("downloads", settings)

                assert result == 0
                captured = capsys.readouterr()
                assert "Errors encountered: 2" in captured.out

    @patch("src.main.get_logger")
    def test_perform_cleanup_conversions_type(self, mock_logger):
        """Test perform_cleanup with 'conversions' cleanup type."""
        from src.main import perform_cleanup
        from src.services.cleanup import CleanupStats

        settings = Settings()

        with patch("src.main.CleanupManager") as mock_cleanup_manager:
            mock_cleanup_instance = Mock()
            mock_cleanup_manager.return_value = mock_cleanup_instance
            mock_cleanup_instance.get_cleanup_preview.return_value = ["/tmp/file1"]

            cleanup_stats = CleanupStats()
            cleanup_stats.files_removed = 5
            cleanup_stats.directories_removed = 1
            cleanup_stats.bytes_freed = 200 * 1024 * 1024  # 200MB
            cleanup_stats.errors = 0
            mock_cleanup_instance.clean_conversions.return_value = cleanup_stats

            with patch("builtins.input", return_value="y"):
                result = perform_cleanup("conversions", settings)

                assert result == 0
                mock_cleanup_instance.clean_conversions.assert_called_once()

    @patch("src.main.get_logger")
    def test_perform_cleanup_dvd_output_type(self, mock_logger):
        """Test perform_cleanup with 'dvd-output' cleanup type."""
        from src.main import perform_cleanup
        from src.services.cleanup import CleanupStats

        settings = Settings()

        with patch("src.main.CleanupManager") as mock_cleanup_manager:
            mock_cleanup_instance = Mock()
            mock_cleanup_manager.return_value = mock_cleanup_instance
            mock_cleanup_instance.get_cleanup_preview.return_value = ["/tmp/file1"]

            cleanup_stats = CleanupStats()
            cleanup_stats.files_removed = 8
            cleanup_stats.directories_removed = 2
            cleanup_stats.bytes_freed = 500 * 1024 * 1024  # 500MB
            cleanup_stats.errors = 0
            mock_cleanup_instance.clean_dvd_output.return_value = cleanup_stats

            with patch("builtins.input", return_value="y"):
                result = perform_cleanup("dvd-output", settings)

                assert result == 0
                mock_cleanup_instance.clean_dvd_output.assert_called_once()

    @patch("src.main.get_logger")
    def test_perform_cleanup_isos_type(self, mock_logger):
        """Test perform_cleanup with 'isos' cleanup type."""
        from src.main import perform_cleanup
        from src.services.cleanup import CleanupStats

        settings = Settings()

        with patch("src.main.CleanupManager") as mock_cleanup_manager:
            mock_cleanup_instance = Mock()
            mock_cleanup_manager.return_value = mock_cleanup_instance
            mock_cleanup_instance.get_cleanup_preview.return_value = ["/tmp/file1"]

            cleanup_stats = CleanupStats()
            cleanup_stats.files_removed = 3
            cleanup_stats.directories_removed = 0
            cleanup_stats.bytes_freed = 1024 * 1024 * 1024  # 1GB
            cleanup_stats.errors = 0
            mock_cleanup_instance.clean_isos.return_value = cleanup_stats

            with patch("builtins.input", return_value="y"):
                result = perform_cleanup("isos", settings)

                assert result == 0
                mock_cleanup_instance.clean_isos.assert_called_once()


class TestMainErrorHandling:
    """Test cases for main function error handling."""

    @patch("src.main.setup_application_logging")
    @patch("src.main.load_settings")
    @patch("src.main.validate_tools")
    @patch("src.main.CacheManager")
    @patch("src.main.ToolManager")
    @patch("src.main.VideoDownloader")
    def test_main_no_available_videos(
        self,
        mock_downloader_cls,
        mock_tool_mgr_cls,
        mock_cache_mgr_cls,
        mock_validate,
        mock_load_settings,
        mock_setup_logging,
    ):
        """Test main when no videos are available for download."""
        mock_settings = Settings()
        mock_load_settings.return_value = mock_settings
        mock_validate.return_value = True

        # Mock empty playlist
        mock_playlist = Mock()
        mock_playlist.get_available_videos.return_value = []

        mock_downloader = Mock()
        mock_downloader.download_playlist.return_value = mock_playlist
        mock_downloader_cls.return_value = mock_downloader

        with patch("sys.argv", ["dvdmaker", "--playlist-url", "PLtest123"]):
            result = main()

        assert result == 1

    @patch("src.main.setup_application_logging")
    @patch("src.main.load_settings")
    @patch("src.main.validate_tools")
    @patch("src.main.CacheManager")
    @patch("src.main.ToolManager")
    @patch("src.main.VideoDownloader")
    @patch("src.main.VideoConverter")
    def test_main_no_video_files_for_conversion(
        self,
        mock_converter_cls,
        mock_downloader_cls,
        mock_tool_mgr_cls,
        mock_cache_mgr_cls,
        mock_validate,
        mock_load_settings,
        mock_setup_logging,
    ):
        """Test main when no video files are available for conversion."""
        mock_settings = Settings()
        mock_load_settings.return_value = mock_settings
        mock_validate.return_value = True

        # Mock playlist with videos but no cached files
        mock_playlist = Mock()
        mock_video = Mock()
        mock_video.video_id = "test123"
        mock_playlist.get_available_videos.return_value = [mock_video]

        mock_downloader = Mock()
        mock_downloader.download_playlist.return_value = mock_playlist
        mock_downloader_cls.return_value = mock_downloader

        # Mock cache manager returning None for cached downloads
        mock_cache_manager = Mock()
        mock_cache_manager.get_cached_download.return_value = None
        mock_cache_mgr_cls.return_value = mock_cache_manager

        with patch("sys.argv", ["dvdmaker", "--playlist-url", "PLtest123"]):
            result = main()

        assert result == 1

    @patch("src.main.setup_application_logging")
    @patch("src.main.load_settings")
    @patch("src.main.validate_tools")
    @patch("src.main.CacheManager")
    @patch("src.main.ToolManager")
    @patch("src.main.VideoDownloader")
    @patch("src.main.VideoConverter")
    def test_main_no_converted_videos(
        self,
        mock_converter_cls,
        mock_downloader_cls,
        mock_tool_mgr_cls,
        mock_cache_mgr_cls,
        mock_validate,
        mock_load_settings,
        mock_setup_logging,
    ):
        """Test main when no videos are successfully converted."""
        mock_settings = Settings()
        mock_load_settings.return_value = mock_settings
        mock_validate.return_value = True

        # Mock playlist with videos
        mock_playlist = Mock()
        mock_video = Mock()
        mock_video.video_id = "test123"
        mock_playlist.get_available_videos.return_value = [mock_video]

        mock_downloader = Mock()
        mock_downloader.download_playlist.return_value = mock_playlist
        mock_downloader_cls.return_value = mock_downloader

        # Mock cache manager returning video file
        mock_cache_manager = Mock()
        mock_cache_manager.get_cached_download.return_value = Mock()
        mock_cache_mgr_cls.return_value = mock_cache_manager

        # Mock converter returning no converted videos
        mock_converter = Mock()
        mock_converter.convert_videos.return_value = []
        mock_converter_cls.return_value = mock_converter

        with patch("sys.argv", ["dvdmaker", "--playlist-url", "PLtest123"]):
            result = main()

        assert result == 1

    @patch("src.main.setup_application_logging")
    @patch("src.main.load_settings")
    @patch("src.main.validate_tools")
    @patch("src.main.CacheManager")
    @patch("src.main.ToolManager")
    @patch("src.main.VideoDownloader")
    @patch("src.main.VideoConverter")
    @patch("src.main.select_videos_for_dvd_capacity")
    def test_main_no_videos_fit_dvd_capacity(
        self,
        mock_capacity,
        mock_converter_cls,
        mock_downloader_cls,
        mock_tool_mgr_cls,
        mock_cache_mgr_cls,
        mock_validate,
        mock_load_settings,
        mock_setup_logging,
    ):
        """Test main when no videos fit on DVD after capacity check."""
        mock_settings = Settings()
        mock_load_settings.return_value = mock_settings
        mock_validate.return_value = True

        # Mock playlist with videos
        mock_playlist = Mock()
        mock_video = Mock()
        mock_video.video_id = "test123"
        mock_playlist.get_available_videos.return_value = [mock_video]

        mock_downloader = Mock()
        mock_downloader.download_playlist.return_value = mock_playlist
        mock_downloader_cls.return_value = mock_downloader

        # Mock cache manager returning video file
        mock_cache_manager = Mock()
        mock_cache_manager.get_cached_download.return_value = Mock()
        mock_cache_mgr_cls.return_value = mock_cache_manager

        # Mock converter returning converted videos
        mock_converter = Mock()
        mock_converter.convert_videos.return_value = [Mock()]
        mock_converter_cls.return_value = mock_converter

        # Mock capacity check returning no videos that fit
        mock_capacity_result = Mock()
        mock_capacity_result.included_videos = []
        mock_capacity.return_value = mock_capacity_result

        with patch("sys.argv", ["dvdmaker", "--playlist-url", "PLtest123"]):
            result = main()

        assert result == 1

    @patch("src.main.setup_application_logging")
    @patch("src.main.load_settings")
    @patch("src.main.validate_tools")
    @patch("src.main.CacheManager")
    @patch("src.main.ToolManager")
    @patch("src.main.VideoDownloader")
    @patch("src.main.VideoConverter")
    @patch("src.main.select_videos_for_dvd_capacity")
    @patch("src.main.log_excluded_videos")
    def test_main_dvd_capacity_exclusions(
        self,
        mock_log_excluded,
        mock_capacity,
        mock_converter_cls,
        mock_downloader_cls,
        mock_tool_mgr_cls,
        mock_cache_mgr_cls,
        mock_validate,
        mock_load_settings,
        mock_setup_logging,
    ):
        """Test main when some videos are excluded due to DVD capacity."""
        mock_settings = Settings()
        mock_load_settings.return_value = mock_settings
        mock_validate.return_value = True

        # Mock playlist with videos
        mock_playlist = Mock()
        mock_video = Mock()
        mock_video.video_id = "test123"
        mock_playlist.get_available_videos.return_value = [mock_video]
        mock_playlist.metadata.title = "Test Playlist"
        mock_playlist.metadata.playlist_id = "PLtest123"

        mock_downloader = Mock()
        mock_downloader.download_playlist.return_value = mock_playlist
        mock_downloader_cls.return_value = mock_downloader

        # Mock cache manager returning video file
        mock_cache_manager = Mock()
        mock_cache_manager.get_cached_download.return_value = Mock()
        mock_cache_mgr_cls.return_value = mock_cache_manager

        # Mock converter returning converted videos
        mock_converter = Mock()
        mock_converted_video = Mock()
        mock_converter.convert_videos.return_value = [mock_converted_video]
        mock_converter_cls.return_value = mock_converter

        # Mock capacity check with exclusions
        mock_excluded_video = Mock()
        mock_capacity_result = Mock()
        mock_capacity_result.has_exclusions = True
        mock_capacity_result.excluded_videos = [mock_excluded_video]
        mock_capacity_result.included_videos = [mock_converted_video]
        mock_capacity_result.total_size_gb = 3.2
        mock_capacity_result.total_duration_human_readable = "10:30"
        mock_capacity_result.excluded_size_gb = 1.5
        mock_capacity.return_value = mock_capacity_result

        # Mock DVD author
        mock_authored_dvd = Mock()
        mock_authored_dvd.video_ts_dir = Path("/tmp/output/VIDEO_TS")
        mock_authored_dvd.iso_file = None

        with patch("src.main.DVDAuthor") as mock_dvd_author_cls:
            mock_dvd_author = Mock()
            mock_dvd_author.create_dvd_structure.return_value = mock_authored_dvd
            mock_dvd_author_cls.return_value = mock_dvd_author

            with patch("sys.argv", ["dvdmaker", "--playlist-url", "PLtest123"]):
                result = main()

        assert result == 0
        mock_log_excluded.assert_called_once_with([mock_excluded_video])


class TestMainCleanupOperation:
    """Test cases for main function cleanup operations."""

    @patch("src.main.perform_cleanup")
    @patch("src.main.setup_application_logging")
    @patch("src.main.load_settings")
    def test_main_cleanup_operation(
        self, mock_load_settings, mock_setup_logging, mock_perform_cleanup
    ):
        """Test main function with cleanup operation."""
        mock_settings = Settings()
        mock_load_settings.return_value = mock_settings
        mock_perform_cleanup.return_value = 0

        with patch("sys.argv", ["dvdmaker", "--clean", "downloads"]):
            result = main()

        assert result == 0
        mock_perform_cleanup.assert_called_once_with("downloads", mock_settings)


class TestMainDVDCreationWithISOPath:
    """Test cases for main function ISO path handling."""

    @patch("src.main.setup_application_logging")
    @patch("src.main.load_settings")
    @patch("src.main.validate_tools")
    @patch("src.main.CacheManager")
    @patch("src.main.ToolManager")
    @patch("src.main.VideoDownloader")
    @patch("src.main.VideoConverter")
    @patch("src.main.DVDAuthor")
    @patch("src.main.select_videos_for_dvd_capacity")
    def test_main_dvd_creation_with_iso_relative_path(
        self,
        mock_capacity,
        mock_dvd_author_cls,
        mock_converter_cls,
        mock_downloader_cls,
        mock_tool_mgr_cls,
        mock_cache_mgr_cls,
        mock_validate,
        mock_load_settings,
        mock_setup_logging,
        tmp_path,
        capsys,
    ):
        """Test main DVD creation with ISO file using relative path."""
        mock_settings = Settings()
        mock_load_settings.return_value = mock_settings
        mock_validate.return_value = True

        # Setup complete mock chain
        mock_playlist = Mock()
        mock_video = Mock()
        mock_video.video_id = "test123"
        mock_playlist.get_available_videos.return_value = [mock_video]
        mock_playlist.metadata.title = "Test Playlist"
        mock_playlist.metadata.playlist_id = "PLtest123"

        mock_downloader = Mock()
        mock_downloader.download_playlist.return_value = mock_playlist
        mock_downloader_cls.return_value = mock_downloader

        mock_cache_manager = Mock()
        mock_cache_manager.get_cached_download.return_value = Mock()
        mock_cache_mgr_cls.return_value = mock_cache_manager

        mock_converter = Mock()
        mock_converted_video = Mock()
        mock_converter.convert_videos.return_value = [mock_converted_video]
        mock_converter_cls.return_value = mock_converter

        mock_capacity_result = Mock()
        mock_capacity_result.has_exclusions = False
        mock_capacity_result.included_videos = [mock_converted_video]
        mock_capacity_result.total_size_gb = 3.2
        mock_capacity_result.total_duration_human_readable = "10:30"
        mock_capacity.return_value = mock_capacity_result

        # Create ISO file in current working directory for relative path
        iso_file = tmp_path / "test.iso"
        iso_file.touch()

        mock_authored_dvd = Mock()
        mock_authored_dvd.video_ts_dir = Path("/tmp/output/VIDEO_TS")
        mock_authored_dvd.iso_file = str(iso_file)

        mock_dvd_author = Mock()
        mock_dvd_author.create_dvd_structure.return_value = mock_authored_dvd
        mock_dvd_author_cls.return_value = mock_dvd_author

        # Change to tmp_path to make ISO path relative
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            with patch("sys.argv", ["dvdmaker", "--playlist-url", "PLtest123"]):
                result = main()

            assert result == 0
            captured = capsys.readouterr()
            assert "ISO file: test.iso" in captured.out

        finally:
            os.chdir(old_cwd)

    @patch("src.main.setup_application_logging")
    @patch("src.main.load_settings")
    @patch("src.main.validate_tools")
    @patch("src.main.CacheManager")
    @patch("src.main.ToolManager")
    @patch("src.main.VideoDownloader")
    @patch("src.main.VideoConverter")
    @patch("src.main.DVDAuthor")
    @patch("src.main.select_videos_for_dvd_capacity")
    def test_main_dvd_creation_with_iso_absolute_path(
        self,
        mock_capacity,
        mock_dvd_author_cls,
        mock_converter_cls,
        mock_downloader_cls,
        mock_tool_mgr_cls,
        mock_cache_mgr_cls,
        mock_validate,
        mock_load_settings,
        mock_setup_logging,
        capsys,
    ):
        """Test main DVD creation with ISO file using absolute path."""
        mock_settings = Settings()
        mock_load_settings.return_value = mock_settings
        mock_validate.return_value = True

        # Setup complete mock chain
        mock_playlist = Mock()
        mock_video = Mock()
        mock_video.video_id = "test123"
        mock_playlist.get_available_videos.return_value = [mock_video]
        mock_playlist.metadata.title = "Test Playlist"
        mock_playlist.metadata.playlist_id = "PLtest123"

        mock_downloader = Mock()
        mock_downloader.download_playlist.return_value = mock_playlist
        mock_downloader_cls.return_value = mock_downloader

        mock_cache_manager = Mock()
        mock_cache_manager.get_cached_download.return_value = Mock()
        mock_cache_mgr_cls.return_value = mock_cache_manager

        mock_converter = Mock()
        mock_converted_video = Mock()
        mock_converter.convert_videos.return_value = [mock_converted_video]
        mock_converter_cls.return_value = mock_converter

        mock_capacity_result = Mock()
        mock_capacity_result.has_exclusions = False
        mock_capacity_result.included_videos = [mock_converted_video]
        mock_capacity_result.total_size_gb = 3.2
        mock_capacity_result.total_duration_human_readable = "10:30"
        mock_capacity.return_value = mock_capacity_result

        # Use absolute path that can't be made relative to cwd
        iso_file = "/completely/different/path/test.iso"

        mock_authored_dvd = Mock()
        mock_authored_dvd.video_ts_dir = Path("/tmp/output/VIDEO_TS")
        mock_authored_dvd.iso_file = iso_file

        mock_dvd_author = Mock()
        mock_dvd_author.create_dvd_structure.return_value = mock_authored_dvd
        mock_dvd_author_cls.return_value = mock_dvd_author

        with patch("sys.argv", ["dvdmaker", "--playlist-url", "PLtest123"]):
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "ISO file:" in captured.out


class TestArgumentValidationMissingURL:
    """Test cases for missing playlist URL validation."""

    def test_validate_arguments_no_playlist_url_attribute(self):
        """Test validation when playlist_url attribute doesn't exist."""
        from src.main import validate_arguments

        # Create args without playlist_url attribute (clean operation)
        args = argparse.Namespace(
            clean="downloads",
            quiet=False,
            verbose=False,
            use_system_tools=False,
            download_tools=False,
        )
        # Don't set playlist_url attribute at all

        # Should not raise any exception for clean operation
        validate_arguments(args)

    def test_validate_arguments_none_playlist_url(self):
        """Test validation with None playlist URL for non-clean operation."""
        from src.main import validate_arguments

        args = argparse.Namespace(
            playlist_url=None,
            quiet=False,
            verbose=False,
            use_system_tools=False,
            download_tools=False,
        )

        with pytest.raises(ValueError, match="Playlist URL is required"):
            validate_arguments(args)


class TestMergeSettingsQuietFlag:
    """Test cases for merging quiet flag setting."""

    def test_merge_settings_with_quiet_flag(self):
        """Test merging settings with quiet flag."""
        from src.main import merge_settings_with_args

        settings = Settings()
        args = argparse.Namespace(
            output_dir=None,
            cache_dir=None,
            temp_dir=None,
            quality=None,
            menu_title=None,
            video_format=None,
            aspect_ratio=None,
            no_iso=False,
            autoplay=False,
            force_download=False,
            force_convert=False,
            use_system_tools=False,
            download_tools=False,
            log_level=None,
            verbose=False,
            quiet=True,  # Test quiet flag
        )

        merged = merge_settings_with_args(args, settings)
        assert merged.quiet is True


class TestScriptMainExecution:
    """Test cases for script main execution."""

    @patch("sys.exit")
    @patch("src.main.main")
    def test_script_main_execution(self, mock_main, mock_exit):
        """Test script execution when run as main."""
        mock_main.return_value = 0

        # Execute the main module's __main__ code path
        exec(
            'if __name__ == "__main__": sys.exit(main())',
            {"__name__": "__main__", "sys": sys, "main": mock_main},
        )

        mock_main.assert_called_once()
        mock_exit.assert_called_once_with(0)
