"""Tests for configuration settings module."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.config.settings import (
    ConfigurationError,
    Settings,
    ValidationResult,
    get_default_config_file,
    load_settings,
    validate_settings,
)


class TestSettings:
    """Test cases for Settings class."""

    def test_default_settings(self):
        """Test that default settings are created correctly."""
        settings = Settings()

        assert settings.cache_dir == Path.cwd() / "cache"
        assert settings.output_dir == Path.cwd() / "output"
        assert settings.temp_dir == Path.cwd() / "temp"
        assert settings.bin_dir == Path.cwd() / "bin"
        assert settings.log_dir == Path.cwd() / "logs"
        assert settings.log_level == "INFO"
        assert settings.log_file_max_size == 10 * 1024 * 1024
        assert settings.log_file_backup_count == 5
        assert settings.download_rate_limit == "1M"
        assert settings.video_quality == "best"
        assert settings.use_system_tools is False
        assert settings.download_tools is True
        assert settings.menu_title is None
        assert settings.generate_iso is True
        assert settings.force_download is False
        assert settings.force_convert is False
        assert settings.verbose is False
        assert settings.quiet is False
        assert settings.video_format == "NTSC"
        assert settings.aspect_ratio == "16:9"

    def test_custom_settings(self):
        """Test creating settings with custom values."""
        custom_cache = Path("/tmp/custom_cache")
        settings = Settings(
            cache_dir=custom_cache,
            log_level="DEBUG",
            video_quality="720p",
            verbose=True,
        )

        assert settings.cache_dir == custom_cache
        assert settings.log_level == "DEBUG"
        assert settings.video_quality == "720p"
        assert settings.verbose is True

    def test_log_level_validation(self):
        """Test log level validation."""
        # Valid log levels should work
        for level in ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR"]:
            settings = Settings(log_level=level)
            assert settings.log_level == level

        # Case insensitive
        settings = Settings(log_level="debug")
        assert settings.log_level == "DEBUG"

        # Invalid log level should raise error
        with pytest.raises(ValidationError):
            Settings(log_level="INVALID")

    def test_log_file_max_size_validation(self):
        """Test log file max size validation."""
        # Positive values should work
        settings = Settings(log_file_max_size=1024)
        assert settings.log_file_max_size == 1024

        # Zero and negative values should raise error
        with pytest.raises(ValidationError):
            Settings(log_file_max_size=0)

        with pytest.raises(ValidationError):
            Settings(log_file_max_size=-1)

    def test_log_file_backup_count_validation(self):
        """Test log file backup count validation."""
        # Non-negative values should work
        settings = Settings(log_file_backup_count=0)
        assert settings.log_file_backup_count == 0

        settings = Settings(log_file_backup_count=10)
        assert settings.log_file_backup_count == 10

        # Negative values should raise error
        with pytest.raises(ValidationError):
            Settings(log_file_backup_count=-1)

    def test_video_format_validation(self):
        """Test video format validation."""
        # Valid video formats should work
        for format_type in ["NTSC", "PAL"]:
            settings = Settings(video_format=format_type)
            assert settings.video_format == format_type

        # Case insensitive
        settings = Settings(video_format="ntsc")
        assert settings.video_format == "NTSC"

        settings = Settings(video_format="pal")
        assert settings.video_format == "PAL"

        # Invalid video format should raise error
        with pytest.raises(ValidationError):
            Settings(video_format="INVALID")

        with pytest.raises(ValidationError):
            Settings(video_format="SECAM")

    def test_aspect_ratio_validation(self):
        """Test aspect ratio validation."""
        # Valid aspect ratios should work
        for ratio in ["4:3", "16:9"]:
            settings = Settings(aspect_ratio=ratio)
            assert settings.aspect_ratio == ratio

        # Invalid aspect ratio should raise error
        with pytest.raises(ValidationError):
            Settings(aspect_ratio="INVALID")

        with pytest.raises(ValidationError):
            Settings(aspect_ratio="2.35:1")

    def test_quiet_verbose_conflict(self):
        """Test that quiet and verbose cannot both be True."""
        # Individual flags should work
        Settings(quiet=True)
        Settings(verbose=True)

        # Both True should raise error
        with pytest.raises(ValidationError):
            Settings(quiet=True, verbose=True)

    def test_directory_path_conversion(self):
        """Test that string paths are converted to Path objects."""
        settings = Settings(cache_dir="/tmp/cache", output_dir="~/output")

        assert isinstance(settings.cache_dir, Path)
        assert isinstance(settings.output_dir, Path)
        assert settings.cache_dir == Path("/tmp/cache")
        # Should expand user home directory
        assert settings.output_dir == Path.home() / "output"

    def test_relative_path_conversion(self):
        """Test that relative paths are made absolute."""
        settings = Settings(cache_dir="relative/path")

        assert settings.cache_dir.is_absolute()
        assert settings.cache_dir == Path.cwd() / "relative/path"

    def test_create_directories(self):
        """Test directory creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = Settings(
                cache_dir=temp_path / "cache",
                output_dir=temp_path / "output",
                temp_dir=temp_path / "temp",
                bin_dir=temp_path / "bin",
                log_dir=temp_path / "logs",
            )

            settings.create_directories()

            # Check that all directories were created
            assert (temp_path / "cache").exists()
            assert (temp_path / "output").exists()
            assert (temp_path / "temp").exists()
            assert (temp_path / "bin").exists()
            assert (temp_path / "logs").exists()
            assert (temp_path / "cache" / "downloads").exists()
            assert (temp_path / "cache" / "converted").exists()
            assert (temp_path / "cache" / "metadata").exists()
            assert (temp_path / "cache" / "downloads" / ".in-progress").exists()
            assert (temp_path / "cache" / "converted" / ".in-progress").exists()

    def test_get_effective_log_level(self):
        """Test effective log level based on flags."""
        # Default log level
        settings = Settings(log_level="INFO")
        assert settings.get_effective_log_level() == "INFO"

        # Quiet flag
        settings = Settings(log_level="INFO", quiet=True)
        assert settings.get_effective_log_level() == "ERROR"

        # Verbose flag
        settings = Settings(log_level="INFO", verbose=True)
        assert settings.get_effective_log_level() == "DEBUG"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        settings = Settings(
            cache_dir=Path("/tmp/cache"), log_level="DEBUG", verbose=True
        )

        result = settings.to_dict()

        assert isinstance(result, dict)
        assert result["cache_dir"] == "/tmp/cache"  # Path converted to string
        assert result["log_level"] == "DEBUG"
        assert result["verbose"] is True

    def test_load_from_file_nonexistent(self):
        """Test loading from non-existent file returns defaults."""
        non_existent_file = Path("/path/that/does/not/exist.json")
        settings = Settings.load_from_file(non_existent_file)

        # Should return default settings
        assert settings.log_level == "INFO"
        assert settings.verbose is False

    def test_load_from_file_valid(self):
        """Test loading from valid JSON file."""
        config_data = {
            "log_level": "DEBUG",
            "verbose": True,
            "cache_dir": "/tmp/test_cache",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = Path(f.name)

        try:
            settings = Settings.load_from_file(config_file)

            assert settings.log_level == "DEBUG"
            assert settings.verbose is True
            assert settings.cache_dir == Path("/tmp/test_cache")
        finally:
            config_file.unlink()

    def test_load_from_file_invalid_json(self):
        """Test loading from invalid JSON file returns defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content")
            config_file = Path(f.name)

        try:
            with patch("logging.warning") as mock_warning:
                settings = Settings.load_from_file(config_file)

                # Should return default settings
                assert settings.log_level == "INFO"
                assert settings.verbose is False

                # Should log warning
                mock_warning.assert_called_once()
        finally:
            config_file.unlink()

    def test_save_to_file(self):
        """Test saving configuration to file."""
        settings = Settings(
            log_level="DEBUG", verbose=True, cache_dir=Path("/tmp/test_cache")
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            settings.save_to_file(config_file)

            assert config_file.exists()

            # Load and verify content
            with open(config_file, "r") as f:
                saved_data = json.load(f)

            assert saved_data["log_level"] == "DEBUG"
            assert saved_data["verbose"] is True
            assert saved_data["cache_dir"] == "/tmp/test_cache"

    def test_load_from_env(self):
        """Test loading from environment variables."""
        env_vars = {
            "DVDMAKER_LOG_LEVEL": "ERROR",
            "DVDMAKER_VERBOSE": "true",
            "DVDMAKER_CACHE_DIR": "/tmp/env_cache",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            settings = Settings()

            assert settings.log_level == "ERROR"
            assert settings.verbose is True
            assert settings.cache_dir == Path("/tmp/env_cache")

    def test_load_config_from_file(self):
        """Test loading configuration from file."""
        # Create config file
        config_data = {
            "log_level": "DEBUG",
            "verbose": True,
            "cache_dir": "/tmp/file_cache",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = Path(f.name)

        try:
            settings = Settings.load_config(config_file)

            assert settings.log_level == "DEBUG"
            assert settings.verbose is True
            assert settings.cache_dir == Path("/tmp/file_cache")
        finally:
            config_file.unlink()


class TestConfigHelpers:
    """Test cases for configuration helper functions."""

    def test_get_default_config_file_xdg(self):
        """Test default config file with XDG_CONFIG_HOME."""
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/xdg_config"}):
            config_file = get_default_config_file()
            assert config_file == Path("/tmp/xdg_config/dvdmaker/config.json")

    def test_get_default_config_file_home(self):
        """Test default config file without XDG_CONFIG_HOME."""
        env_without_xdg = {
            k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"
        }
        with patch.dict(os.environ, env_without_xdg, clear=True):
            config_file = get_default_config_file()
            assert config_file == Path.home() / ".config" / "dvdmaker" / "config.json"

    def test_load_settings_basic(self):
        """Test basic settings loading."""
        settings = load_settings()
        assert isinstance(settings, Settings)
        assert settings.log_level == "INFO"  # Default value


class TestConfigurationError:
    """Test cases for ConfigurationError exception."""

    def test_configuration_error_basic(self):
        """Test basic ConfigurationError creation."""
        error = ConfigurationError("Test error")
        assert str(error) == "Test error"
        assert error.context == {}

    def test_configuration_error_with_context(self):
        """Test ConfigurationError with context."""
        context = {"field": "log_level", "value": "INVALID"}
        error = ConfigurationError("Invalid log level", context)

        assert "Invalid log level" in str(error)
        assert "field=log_level" in str(error)
        assert "value=INVALID" in str(error)
        assert error.context == context

    def test_configuration_error_inheritance(self):
        """Test ConfigurationError inherits from DVDMakerError."""
        from src.exceptions import DVDMakerError

        error = ConfigurationError("Test error")
        assert isinstance(error, DVDMakerError)


class TestValidationResult:
    """Test cases for ValidationResult class."""

    def test_validation_result_empty(self):
        """Test empty ValidationResult."""
        result = ValidationResult()

        assert result.is_valid is True
        assert result.has_warnings is False
        assert result.errors == []
        assert result.warnings == []
        assert result.get_summary() == "validation passed"

    def test_validation_result_with_errors(self):
        """Test ValidationResult with errors."""
        result = ValidationResult()
        result.add_error("First error")
        result.add_error("Second error")

        assert result.is_valid is False
        assert result.has_warnings is False
        assert len(result.errors) == 2
        assert result.errors[0] == "First error"
        assert result.errors[1] == "Second error"
        assert result.get_summary() == "2 error(s)"

    def test_validation_result_with_warnings(self):
        """Test ValidationResult with warnings."""
        result = ValidationResult()
        result.add_warning("First warning")
        result.add_warning("Second warning")

        assert result.is_valid is True
        assert result.has_warnings is True
        assert len(result.warnings) == 2
        assert result.warnings[0] == "First warning"
        assert result.warnings[1] == "Second warning"
        assert result.get_summary() == "2 warning(s)"

    def test_validation_result_with_both(self):
        """Test ValidationResult with both errors and warnings."""
        result = ValidationResult()
        result.add_error("Error message")
        result.add_warning("Warning message")

        assert result.is_valid is False
        assert result.has_warnings is True
        assert result.get_summary() == "1 error(s), 1 warning(s)"

    def test_validation_result_raise_if_valid(self):
        """Test raise_if_invalid with valid result."""
        result = ValidationResult()
        result.add_warning("Just a warning")

        # Should not raise
        result.raise_if_invalid()

    def test_validation_result_raise_if_invalid(self):
        """Test raise_if_invalid with invalid result."""
        result = ValidationResult()
        result.add_error("Critical error")
        result.add_warning("Warning")

        with pytest.raises(ConfigurationError) as exc_info:
            result.raise_if_invalid()

        error = exc_info.value
        assert "Configuration validation failed:" in str(error)
        assert "Critical error" in str(error)
        assert error.context["errors"] == ["Critical error"]
        assert error.context["warnings"] == ["Warning"]


class TestSettingsValidation:
    """Test cases for Settings validation functionality."""

    def test_directory_conflict_validation(self):
        """Test directory conflict validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Same directory for cache and output should cause conflict
            with pytest.raises((ValidationError, ConfigurationError)) as exc_info:
                Settings(
                    cache_dir=temp_path / "shared",
                    output_dir=temp_path / "shared",
                )

            # Check that the validation error mentions directory conflict
            error_str = str(exc_info.value)
            assert (
                "Directory conflict" in error_str
                or "Configuration validation failed" in error_str
            )

    def test_nested_directory_warning(self):
        """Test nested directory warnings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            settings = Settings(
                cache_dir=temp_path / "parent",
                output_dir=temp_path / "parent" / "child",
            )

            # Should create settings but have warnings
            result = settings.validate_comprehensive()
            assert result.is_valid
            assert result.has_warnings
            assert any("nested inside" in warning for warning in result.warnings)

    def test_tool_configuration_validation(self):
        """Test tool configuration validation."""
        # Both use_system_tools and download_tools disabled should error
        with pytest.raises((ValidationError, ConfigurationError)) as exc_info:
            Settings(
                use_system_tools=False,
                download_tools=False,
            )

        error_str = str(exc_info.value)
        assert (
            "no tools would be available" in error_str
            or "Configuration validation failed" in error_str
        )

    def test_download_rate_limit_validation(self):
        """Test download rate limit format validation."""
        # Valid formats should work
        Settings(download_rate_limit="1M")
        Settings(download_rate_limit="500K")
        Settings(download_rate_limit="10G")
        Settings(download_rate_limit="1000")

        # Invalid format should error
        with pytest.raises((ValidationError, ConfigurationError)) as exc_info:
            Settings(download_rate_limit="invalid-format")

        error_str = str(exc_info.value)
        assert (
            "Invalid download rate limit format" in error_str
            or "Configuration validation failed" in error_str
        )

    def test_menu_title_length_warning(self):
        """Test menu title length warnings."""
        long_title = "A" * 150  # Very long title
        settings = Settings(menu_title=long_title)

        result = settings.validate_comprehensive()
        assert result.is_valid  # Should be valid but with warnings
        assert result.has_warnings
        assert any("quite long" in warning for warning in result.warnings)

    def test_menu_title_non_ascii_warning(self):
        """Test menu title non-ASCII character warnings."""
        non_ascii_title = "Título con caracteres especiales ñáéíóú"
        settings = Settings(menu_title=non_ascii_title)

        result = settings.validate_comprehensive()
        assert result.is_valid  # Should be valid but with warnings
        assert result.has_warnings
        assert any("non-ASCII characters" in warning for warning in result.warnings)

    def test_logging_config_warnings(self):
        """Test logging configuration warnings."""
        # Large log file size should warn
        settings = Settings(
            log_file_max_size=200 * 1024 * 1024,  # 200MB
            log_file_backup_count=30,
        )

        result = settings.validate_comprehensive()
        assert result.is_valid  # Should be valid but with warnings
        assert result.has_warnings

        warnings_text = " ".join(result.warnings)
        assert "quite large" in warnings_text or "quite high" in warnings_text

    def test_force_flags_warning(self):
        """Test force download and convert flags warning."""
        settings = Settings(
            force_download=True,
            force_convert=True,
        )

        result = settings.validate_comprehensive()
        assert result.is_valid  # Should be valid but with warnings
        assert result.has_warnings
        assert any("significant disk space" in warning for warning in result.warnings)

    def test_disk_space_validation_method(self):
        """Test disk space validation through direct method call."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create settings first (without the problematic validation in constructor)
            settings = Settings(
                cache_dir=temp_path / "cache",
                output_dir=temp_path / "output",
                temp_dir=temp_path / "temp",
            )

            # Mock disk usage for the validation method
            with patch.object(settings, "_validate_resource_config") as mock_validate:

                def mock_resource_validation(result):
                    result.add_error(
                        "Insufficient disk space for cache directory: "
                        "only 0.5GB available"
                    )

                mock_validate.side_effect = mock_resource_validation

                # Test that validation fails with disk space error
                result = settings.validate_comprehensive()
                assert not result.is_valid
                assert any("disk space" in error for error in result.errors)

    def test_validate_comprehensive_method(self):
        """Test validate_comprehensive method directly."""
        settings = Settings(
            menu_title="Very long title " * 10,  # Trigger warning
            force_download=True,
            force_convert=True,
        )

        result = settings.validate_comprehensive()

        assert isinstance(result, ValidationResult)
        assert result.is_valid  # No errors, just warnings
        assert result.has_warnings
        assert len(result.warnings) >= 2  # At least title length and force flags


class TestValidateSettingsFunction:
    """Test cases for validate_settings helper function."""

    def test_validate_settings_basic(self):
        """Test basic validate_settings function."""
        settings = Settings()
        result = validate_settings(settings)

        assert isinstance(result, ValidationResult)
        assert result.is_valid

    def test_validate_settings_with_warnings(self):
        """Test validate_settings with warnings."""
        settings = Settings(
            menu_title="Very long title " * 10,
            force_download=True,
            force_convert=True,
        )

        result = validate_settings(settings)
        assert result.is_valid
        assert result.has_warnings

    def test_validate_settings_strict_mode(self):
        """Test validate_settings in strict mode."""
        settings = Settings(
            menu_title="Very long title " * 10,  # This will trigger a warning
        )

        # Normal mode: should be valid with warnings
        result = validate_settings(settings, strict=False)
        assert result.is_valid
        assert result.has_warnings

        # Strict mode: warnings become errors
        result = validate_settings(settings, strict=True)
        assert not result.is_valid
        assert not result.has_warnings  # Warnings were converted to errors
        assert len(result.errors) > 0
        assert any("Strict mode:" in error for error in result.errors)


class TestLoadSettingsValidation:
    """Test cases for load_settings with validation."""

    def test_load_settings_with_validation_enabled(self):
        """Test load_settings with validation enabled."""
        with patch("src.config.settings.logging"):
            settings = load_settings(validate=True)

            assert isinstance(settings, Settings)
            # Should call logging for any warnings if present
            # (hard to test specific warnings without creating invalid config)

    def test_load_settings_with_validation_disabled(self):
        """Test load_settings with validation disabled."""
        settings = load_settings(validate=False)

        assert isinstance(settings, Settings)

    def test_load_settings_validation_with_warnings(self):
        """Test load_settings handles validation warnings properly."""
        # Create a config file with settings that will trigger warnings
        config_data = {
            "menu_title": "Very long title " * 10,
            "force_download": True,
            "force_convert": True,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = Path(f.name)

        try:
            with patch("src.config.settings.logging") as mock_logging:
                settings = load_settings(config_file, validate=True)

                assert isinstance(settings, Settings)
                assert settings.menu_title.startswith("Very long title")

                # Should have logged warnings
                mock_logging.warning.assert_called()
                mock_logging.info.assert_called()
        finally:
            config_file.unlink()
