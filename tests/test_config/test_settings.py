"""Tests for configuration settings module."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.config.settings import Settings, get_default_config_file, load_settings


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
        assert settings.generate_iso is False
        assert settings.force_download is False
        assert settings.force_convert is False
        assert settings.verbose is False
        assert settings.quiet is False

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
