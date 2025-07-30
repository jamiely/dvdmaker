"""Tests for the common exception hierarchy."""

import pytest

from src.exceptions import DVDMakerError
from src.services.converter import ConversionError, VideoConverterError
from src.services.downloader import YtDlpError
from src.services.dvd_author import DVDAuthorError, DVDAuthoringError
from src.services.tool_manager import ToolDownloadError, ToolManagerError, ToolValidationError


class TestDVDMakerError:
    """Test the base DVDMakerError class."""

    def test_basic_error_creation(self):
        """Test creating a basic DVDMakerError."""
        error = DVDMakerError("Test error message")
        assert str(error) == "Test error message"
        assert error.context == {}

    def test_error_with_context(self):
        """Test creating an error with context."""
        context = {"video_id": "abc123", "operation": "download"}
        error = DVDMakerError("Test error with context", context)
        
        assert "Test error with context" in str(error)
        assert "video_id=abc123" in str(error)
        assert "operation=download" in str(error)
        assert error.context == context

    def test_error_without_context_string_representation(self):
        """Test string representation without context."""
        error = DVDMakerError("Simple error")
        assert str(error) == "Simple error"

    def test_error_inheritance(self):
        """Test that DVDMakerError inherits from Exception."""
        error = DVDMakerError("Test error")
        assert isinstance(error, Exception)


class TestServiceErrorInheritance:
    """Test that all service errors inherit from DVDMakerError."""

    def test_video_converter_error_inheritance(self):
        """Test VideoConverterError inherits from DVDMakerError."""
        error = VideoConverterError("Conversion failed")
        assert isinstance(error, DVDMakerError)
        assert isinstance(error, Exception)

    def test_conversion_error_inheritance(self):
        """Test ConversionError inherits from VideoConverterError and DVDMakerError."""
        error = ConversionError("Specific conversion failed")
        assert isinstance(error, VideoConverterError)
        assert isinstance(error, DVDMakerError)
        assert isinstance(error, Exception)

    def test_ytdlp_error_inheritance(self):
        """Test YtDlpError inherits from DVDMakerError."""
        error = YtDlpError("Download failed")
        assert isinstance(error, DVDMakerError)
        assert isinstance(error, Exception)

    def test_dvd_author_error_inheritance(self):
        """Test DVDAuthorError inherits from DVDMakerError."""
        error = DVDAuthorError("DVD authoring failed")
        assert isinstance(error, DVDMakerError)
        assert isinstance(error, Exception)

    def test_dvd_authoring_error_inheritance(self):
        """Test DVDAuthoringError inherits from DVDAuthorError and DVDMakerError."""
        error = DVDAuthoringError("Specific authoring failed")
        assert isinstance(error, DVDAuthorError)
        assert isinstance(error, DVDMakerError)
        assert isinstance(error, Exception)

    def test_tool_manager_error_inheritance(self):
        """Test ToolManagerError inherits from DVDMakerError."""
        error = ToolManagerError("Tool management failed")
        assert isinstance(error, DVDMakerError)
        assert isinstance(error, Exception)

    def test_tool_download_error_inheritance(self):
        """Test ToolDownloadError inherits from ToolManagerError and DVDMakerError."""
        error = ToolDownloadError("Tool download failed")
        assert isinstance(error, ToolManagerError)
        assert isinstance(error, DVDMakerError)
        assert isinstance(error, Exception)

    def test_tool_validation_error_inheritance(self):
        """Test ToolValidationError inherits from ToolManagerError and DVDMakerError."""
        error = ToolValidationError("Tool validation failed")
        assert isinstance(error, ToolManagerError)
        assert isinstance(error, DVDMakerError)
        assert isinstance(error, Exception)


class TestErrorContextPropagation:
    """Test that context is properly handled in service errors."""

    def test_service_error_with_context(self):
        """Test that service errors can use context."""
        context = {"tool": "ffmpeg", "command": "--version"}
        error = ToolValidationError("Tool validation failed", context)
        
        assert isinstance(error, DVDMakerError)
        assert error.context == context
        assert "tool=ffmpeg" in str(error)
        assert "command=--version" in str(error)

    def test_nested_error_context(self):
        """Test that nested service errors maintain context."""
        context = {"video_file": "/path/to/video.mp4", "format": "mpeg2"}
        error = ConversionError("Video conversion failed", context)
        
        # Should inherit from all parent classes
        assert isinstance(error, ConversionError)
        assert isinstance(error, VideoConverterError)
        assert isinstance(error, DVDMakerError)
        assert isinstance(error, Exception)
        
        # Should maintain context
        assert error.context == context
        assert "video_file=/path/to/video.mp4" in str(error)


class TestErrorCatchingPatterns:
    """Test common error catching patterns."""

    def test_catch_all_dvd_maker_errors(self):
        """Test catching all DVD Maker errors with base class."""
        errors_to_test = [
            VideoConverterError("Test"),
            ConversionError("Test"),
            YtDlpError("Test"), 
            DVDAuthorError("Test"),
            DVDAuthoringError("Test"),
            ToolManagerError("Test"),
            ToolDownloadError("Test"),
            ToolValidationError("Test"),
        ]
        
        for error in errors_to_test:
            try:
                raise error
            except DVDMakerError:
                # Should catch all DVD Maker errors
                pass
            except Exception:
                pytest.fail(f"DVDMakerError should have caught {type(error).__name__}")

    def test_catch_specific_service_errors(self):
        """Test catching specific service error hierarchies."""
        # Test tool manager error hierarchy
        try:
            raise ToolDownloadError("Download failed")
        except ToolManagerError:
            # Should catch ToolDownloadError via parent class
            pass
        except Exception:
            pytest.fail("ToolManagerError should have caught ToolDownloadError")

        # Test converter error hierarchy
        try:
            raise ConversionError("Conversion failed")
        except VideoConverterError:
            # Should catch ConversionError via parent class
            pass
        except Exception:
            pytest.fail("VideoConverterError should have caught ConversionError")