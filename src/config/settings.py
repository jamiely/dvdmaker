"""Configuration settings for DVD Maker application.

This module provides configuration management with Pydantic validation,
environment variable support, and file-based configuration loading.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation."""

    # Directory settings
    cache_dir: Path = Field(default_factory=lambda: Path.cwd() / "cache")
    output_dir: Path = Field(default_factory=lambda: Path.cwd() / "output")
    temp_dir: Path = Field(default_factory=lambda: Path.cwd() / "temp")
    bin_dir: Path = Field(default_factory=lambda: Path.cwd() / "bin")
    log_dir: Path = Field(default_factory=lambda: Path.cwd() / "logs")

    # Logging settings
    log_level: str = Field(default="INFO")
    log_file_max_size: int = Field(default=10 * 1024 * 1024)  # 10MB
    log_file_backup_count: int = Field(default=5)

    # Download settings
    download_rate_limit: str = Field(default="1M")
    video_quality: str = Field(default="best")

    # Tool settings
    use_system_tools: bool = Field(default=False)
    download_tools: bool = Field(default=True)

    # DVD settings
    menu_title: Optional[str] = Field(default=None)
    generate_iso: bool = Field(default=False)

    # Cache settings
    force_download: bool = Field(default=False)
    force_convert: bool = Field(default=False)

    # Console output settings
    verbose: bool = Field(default=False)
    quiet: bool = Field(default=False)

    model_config = SettingsConfigDict(
        env_prefix="DVDMAKER_",
        case_sensitive=False,
        env_ignore_empty=True,
        json_file_encoding="utf-8",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is supported."""
        valid_levels = ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {', '.join(valid_levels)}")
        return v.upper()

    @field_validator("log_file_max_size")
    @classmethod
    def validate_log_file_max_size(cls, v: int) -> int:
        """Validate log file max size is positive."""
        if v <= 0:
            raise ValueError("Log file max size must be positive")
        return v

    @field_validator("log_file_backup_count")
    @classmethod
    def validate_log_file_backup_count(cls, v: int) -> int:
        """Validate log file backup count is non-negative."""
        if v < 0:
            raise ValueError("Log file backup count must be non-negative")
        return v

    @field_validator("video_quality")
    @classmethod
    def validate_video_quality(cls, v: str) -> str:
        """Validate video quality setting."""
        valid_qualities = ["best", "worst", "bestvideo", "worstvideo"]
        # Also allow specific formats like 'mp4', '720p', etc.
        if v not in valid_qualities and not v.replace("p", "").isdigit():
            # For now, allow any string - yt-dlp will validate
            pass
        return v

    @field_validator("cache_dir", "output_dir", "temp_dir", "bin_dir", "log_dir")
    @classmethod
    def validate_directories(cls, v: Union[str, Path]) -> Path:
        """Convert string paths to Path objects and validate."""
        if isinstance(v, str):
            v = Path(v)

        # Expand user home directory
        v = v.expanduser()

        # Convert to absolute path
        if not v.is_absolute():
            v = Path.cwd() / v

        return v

    @field_validator("quiet")
    @classmethod
    def validate_quiet_verbose_conflict(cls, v: bool, info: Any) -> bool:
        """Ensure quiet and verbose are not both True."""
        if v and info.data.get("verbose", False):
            raise ValueError("Cannot use both --quiet and --verbose flags")
        return v

    def create_directories(self) -> None:
        """Create all configured directories if they don't exist."""
        directories = [
            self.cache_dir,
            self.output_dir,
            self.temp_dir,
            self.bin_dir,
            self.log_dir,
            self.cache_dir / "downloads",
            self.cache_dir / "converted",
            self.cache_dir / "metadata",
            self.cache_dir / "downloads" / ".in-progress",
            self.cache_dir / "converted" / ".in-progress",
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def get_effective_log_level(self) -> str:
        """Get the effective log level considering verbose/quiet flags."""
        if self.quiet:
            return "ERROR"
        elif self.verbose:
            return "DEBUG"
        else:
            return self.log_level

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary for serialization."""
        return {
            key: str(value) if isinstance(value, Path) else value
            for key, value in self.model_dump().items()
        }

    @classmethod
    def load_from_file(cls, config_file: Path) -> "Settings":
        """Load configuration from JSON file."""
        if not config_file.exists():
            return cls()

        try:
            with open(config_file, "r") as f:
                config_data = json.load(f)
            return cls(**config_data)
        except (json.JSONDecodeError, TypeError) as e:
            logging.warning(f"Failed to load config from {config_file}: {e}")
            return cls()

    def save_to_file(self, config_file: Path) -> None:
        """Save configuration to JSON file."""
        config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_config(cls, config_file: Optional[Path] = None) -> "Settings":
        """Load configuration from file and environment variables.

        Priority order:
        1. Environment variables (handled automatically by BaseSettings)
        2. Config file
        3. Default values
        """
        init_kwargs = {}

        # Load file config if provided
        if config_file and config_file.exists():
            try:
                with open(config_file, "r") as f:
                    file_config = json.load(f)
                init_kwargs.update(file_config)
            except (json.JSONDecodeError, TypeError) as e:
                logging.warning(f"Failed to load config from {config_file}: {e}")

        # BaseSettings will automatically override with environment variables
        return cls(**init_kwargs)


def get_default_config_file() -> Path:
    """Get the default configuration file path."""
    # Check XDG config directory first
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / "dvdmaker" / "config.json"

    # Fall back to user home directory
    return Path.home() / ".config" / "dvdmaker" / "config.json"


def load_settings(config_file: Optional[Path] = None) -> Settings:
    """Load application settings from configuration file and environment.

    Args:
        config_file: Optional path to configuration file.
                    If None, uses default location.

    Returns:
        Settings instance with loaded configuration.
    """
    if config_file is None:
        config_file = get_default_config_file()

    settings = Settings.load_config(config_file)

    # Create necessary directories
    try:
        settings.create_directories()
    except OSError as e:
        logging.warning(f"Failed to create some directories: {e}")

    return settings
