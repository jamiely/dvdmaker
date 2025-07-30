"""Tests for the BaseService class."""

from unittest.mock import Mock, patch

from src.config.settings import Settings
from src.services.base import BaseService


class TestBaseService:
    """Test the BaseService class."""

    def test_base_service_initialization(self, tmp_path):
        """Test basic BaseService initialization."""
        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        service = BaseService(settings)

        assert service.settings == settings
        assert service.logger is not None
        assert service.logger.name == "src.services.base"

    def test_base_service_logger_uses_module_name(self, tmp_path):
        """Test that logger uses the class module name."""
        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        with patch("src.services.base.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            service = BaseService(settings)

            mock_get_logger.assert_called_once_with("src.services.base")
            assert service.logger == mock_logger

    def test_validate_tools_not_implemented(self, tmp_path):
        """Test that _validate_tools is a placeholder method."""
        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        service = BaseService(settings)

        # Should not raise an exception - it's just a placeholder
        service._validate_tools(["ffmpeg", "yt-dlp"])

    def test_log_operation_start_without_context(self, tmp_path):
        """Test logging operation start without context."""
        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        service = BaseService(settings)

        with patch.object(service.logger, "info") as mock_info:
            service._log_operation_start("test_operation")
            mock_info.assert_called_once_with("Starting test_operation")

    def test_log_operation_start_with_context(self, tmp_path):
        """Test logging operation start with context."""
        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        service = BaseService(settings)

        with patch.object(service.logger, "info") as mock_info:
            service._log_operation_start(
                "test_operation", video_id="abc123", format="mp4"
            )

            # Should include context in the log message
            call_args = mock_info.call_args[0][0]
            assert "Starting test_operation" in call_args
            assert "context:" in call_args
            assert "video_id=abc123" in call_args
            assert "format=mp4" in call_args

    def test_log_operation_complete_without_context(self, tmp_path):
        """Test logging operation completion without context."""
        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        service = BaseService(settings)

        with patch.object(service.logger, "info") as mock_info:
            service._log_operation_complete("test_operation")
            mock_info.assert_called_once_with("Completed test_operation")

    def test_log_operation_complete_with_context(self, tmp_path):
        """Test logging operation completion with context."""
        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        service = BaseService(settings)

        with patch.object(service.logger, "info") as mock_info:
            service._log_operation_complete(
                "test_operation", result="success", duration=5.2
            )

            # Should include context in the log message
            call_args = mock_info.call_args[0][0]
            assert "Completed test_operation" in call_args
            assert "context:" in call_args
            assert "result=success" in call_args
            assert "duration=5.2" in call_args

    def test_log_operation_error_without_context(self, tmp_path):
        """Test logging operation error without context."""
        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        service = BaseService(settings)
        error = ValueError("Something went wrong")

        with patch.object(service.logger, "error") as mock_error:
            service._log_operation_error("test_operation", error)
            mock_error.assert_called_once_with(
                "Failed test_operation: Something went wrong"
            )

    def test_log_operation_error_with_context(self, tmp_path):
        """Test logging operation error with context."""
        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        service = BaseService(settings)
        error = ValueError("Something went wrong")

        with patch.object(service.logger, "error") as mock_error:
            service._log_operation_error(
                "test_operation", error, file_path="/test/file.mp4"
            )

            # Should include context in the log message
            call_args = mock_error.call_args[0][0]
            assert "Failed test_operation: Something went wrong" in call_args
            assert "context:" in call_args
            assert "file_path=/test/file.mp4" in call_args

    def test_service_initialization_logs_debug_message(self, tmp_path):
        """Test that service initialization logs a debug message."""
        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        with patch("src.services.base.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            BaseService(settings)

            mock_logger.debug.assert_called_once_with(
                "BaseService initialized with settings"
            )


class TestServiceInheritance:
    """Test that existing services properly inherit from BaseService."""

    def test_cache_manager_inheritance(self, tmp_path):
        """Test that CacheManager inherits from BaseService."""
        from src.services.base import BaseService
        from src.services.cache_manager import CacheManager

        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        cache_manager = CacheManager(cache_dir=tmp_path / "cache", settings=settings)

        assert isinstance(cache_manager, BaseService)
        assert hasattr(cache_manager, "logger")
        # CacheManager only inherits BaseService when settings are provided
        if hasattr(cache_manager, "settings"):
            assert cache_manager.settings == settings

    def test_video_converter_inheritance(self, tmp_path):
        """Test that VideoConverter inherits from BaseService."""
        from unittest.mock import Mock

        from src.services.base import BaseService
        from src.services.converter import VideoConverter

        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        tool_manager = Mock()
        cache_manager = Mock()

        converter = VideoConverter(
            settings=settings,
            tool_manager=tool_manager,
            cache_manager=cache_manager,
        )

        assert isinstance(converter, BaseService)
        assert hasattr(converter, "logger")
        assert converter.settings == settings

    def test_video_downloader_inheritance(self, tmp_path):
        """Test that VideoDownloader inherits from BaseService."""
        from unittest.mock import Mock

        from src.services.base import BaseService
        from src.services.downloader import VideoDownloader

        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        tool_manager = Mock()
        cache_manager = Mock()

        downloader = VideoDownloader(
            settings=settings,
            cache_manager=cache_manager,
            tool_manager=tool_manager,
        )

        assert isinstance(downloader, BaseService)
        assert hasattr(downloader, "logger")
        assert downloader.settings == settings

    def test_dvd_author_inheritance(self, tmp_path):
        """Test that DVDAuthor inherits from BaseService."""
        from unittest.mock import Mock

        from src.services.base import BaseService
        from src.services.dvd_author import DVDAuthor

        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
        )

        tool_manager = Mock()
        cache_manager = Mock()

        dvd_author = DVDAuthor(
            settings=settings,
            tool_manager=tool_manager,
            cache_manager=cache_manager,
        )

        assert isinstance(dvd_author, BaseService)
        assert hasattr(dvd_author, "logger")
        assert dvd_author.settings == settings

    def test_tool_manager_inheritance(self, tmp_path):
        """Test that ToolManager inherits from BaseService."""
        from src.services.base import BaseService
        from src.services.tool_manager import ToolManager

        settings = Settings(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            temp_dir=tmp_path / "temp",
            bin_dir=tmp_path / "bin",
        )

        tool_manager = ToolManager(settings=settings)

        assert isinstance(tool_manager, BaseService)
        assert hasattr(tool_manager, "logger")
        assert tool_manager.settings == settings
