"""Configuration settings for DVD Maker application.

This module provides configuration management with Pydantic validation,
environment variable support, and file-based configuration loading.
"""

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..exceptions import DVDMakerError


class ConfigurationError(DVDMakerError):
    """Exception raised for configuration validation errors."""

    pass


class ValidationResult:
    """Container for validation results with error details."""

    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def add_error(self, error: str) -> None:
        """Add a validation error."""
        self.errors.append(error)

    def add_warning(self, warning: str) -> None:
        """Add a validation warning."""
        self.warnings.append(warning)

    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors)."""
        return len(self.errors) == 0

    @property
    def has_warnings(self) -> bool:
        """Check if validation has warnings."""
        return len(self.warnings) > 0

    def get_summary(self) -> str:
        """Get a summary of validation results."""
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        return ", ".join(parts) if parts else "validation passed"

    def raise_if_invalid(self) -> None:
        """Raise ConfigurationError if validation failed."""
        if not self.is_valid:
            error_msg = "Configuration validation failed:\n" + "\n".join(
                f"  - {error}" for error in self.errors
            )
            raise ConfigurationError(
                error_msg, {"errors": self.errors, "warnings": self.warnings}
            )


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
    generate_iso: bool = Field(default=True)
    video_format: str = Field(default="NTSC")
    aspect_ratio: str = Field(default="16:9")
    car_dvd_compatibility: bool = Field(default=True)
    autoplay: bool = Field(default=True)

    # Cache settings
    force_download: bool = Field(default=False)
    force_convert: bool = Field(default=False)
    refresh_playlist: bool = Field(default=False)

    # Console output settings
    verbose: bool = Field(default=False)
    quiet: bool = Field(default=False)

    # Button settings
    button_enabled: bool = Field(default=True)
    button_text: str = Field(default="PLAY")
    button_position: tuple[int, int] = Field(default=(360, 400))
    button_size: tuple[int, int] = Field(default=(120, 40))
    button_color: str = Field(default="#FFFFFF")

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

    @field_validator("video_format")
    @classmethod
    def validate_video_format(cls, v: str) -> str:
        """Validate video format is PAL or NTSC."""
        valid_formats = ["PAL", "NTSC"]
        if v.upper() not in valid_formats:
            raise ValueError(f"Video format must be one of: {', '.join(valid_formats)}")
        return v.upper()

    @field_validator("aspect_ratio")
    @classmethod
    def validate_aspect_ratio(cls, v: str) -> str:
        """Validate aspect ratio format."""
        valid_ratios = ["4:3", "16:9"]
        if v not in valid_ratios:
            raise ValueError(f"Aspect ratio must be one of: {', '.join(valid_ratios)}")
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

    @field_validator("button_color")
    @classmethod
    def validate_button_color(cls, v: str) -> str:
        """Validate button color is a valid hex color."""
        import re

        if not re.match(r"^#[0-9A-Fa-f]{6}$", v):
            raise ValueError("Button color must be a valid hex color (e.g., #FFFFFF)")
        return v.upper()

    @field_validator("button_position")
    @classmethod
    def validate_button_position(cls, v: tuple[int, int]) -> tuple[int, int]:
        """Validate button position is within reasonable bounds."""
        x, y = v
        if x < 0 or y < 0:
            raise ValueError("Button position coordinates must be non-negative")
        if x > 720 or y > 576:  # DVD max resolution
            raise ValueError("Button position must be within DVD resolution bounds")
        return v

    @field_validator("button_size")
    @classmethod
    def validate_button_size(cls, v: tuple[int, int]) -> tuple[int, int]:
        """Validate button size is reasonable."""
        width, height = v
        if width <= 0 or height <= 0:
            raise ValueError("Button size must be positive")
        if width > 720 or height > 576:  # DVD max resolution
            raise ValueError("Button size must be within DVD resolution bounds")
        return v

    @model_validator(mode="after")
    def validate_cross_field_constraints(self) -> "Settings":
        """Comprehensive cross-field validation."""
        result: ValidationResult = ValidationResult()

        # Validate directory configurations
        self._validate_directory_config(result)

        # Validate logging configuration
        self._validate_logging_config(result)

        # Validate tool configuration
        self._validate_tool_config(result)

        # Validate DVD configuration
        self._validate_dvd_config(result)

        # Validate button configuration
        self._validate_button_config(result)

        # Validate performance/resource settings
        self._validate_resource_config(result)

        # Raise if validation failed
        result.raise_if_invalid()

        return self

    def _validate_directory_config(self, result: ValidationResult) -> None:
        """Validate directory configuration."""
        directories = {
            "cache_dir": self.cache_dir,
            "output_dir": self.output_dir,
            "temp_dir": self.temp_dir,
            "bin_dir": self.bin_dir,
            "log_dir": self.log_dir,
        }

        # Check for directory conflicts (same directory used for different purposes)
        resolved_dirs: Dict[str, Path] = {}
        for name, path in directories.items():
            resolved = path.resolve()
            if resolved in resolved_dirs.values():
                conflict_name = next(
                    n for n, p in resolved_dirs.items() if p == resolved
                )
                result.add_error(
                    f"Directory conflict: {name} and {conflict_name} "
                    f"resolve to the same path: {resolved}"
                )
            resolved_dirs[name] = resolved

        # Check for nested directory issues
        for name1, path1 in directories.items():
            for name2, path2 in directories.items():
                if name1 != name2:
                    try:
                        if (
                            path1.resolve() != path2.resolve()
                            and path1.resolve().is_relative_to(path2.resolve())
                        ):
                            result.add_warning(
                                f"{name1} ({path1}) is nested inside {name2} ({path2})"
                            )
                    except (OSError, ValueError):
                        # Handle cases where paths can't be resolved
                        pass

        # Check directory accessibility
        for name, path in directories.items():
            parent = path.parent if not path.exists() else path
            if parent.exists():
                if not os.access(parent, os.R_OK):
                    result.add_error(
                        f"{name} parent directory is not readable: {parent}"
                    )
                if not os.access(parent, os.W_OK):
                    result.add_error(
                        f"{name} parent directory is not writable: {parent}"
                    )

    def _validate_logging_config(self, result: ValidationResult) -> None:
        """Validate logging configuration."""
        # Check log file size limits
        if self.log_file_max_size > 100 * 1024 * 1024:  # 100MB
            size_mb = self.log_file_max_size / (1024 * 1024)
            result.add_warning(f"Log file max size is quite large: {size_mb:.1f}MB")

        if self.log_file_backup_count > 20:
            result.add_warning(
                f"Log file backup count is quite high: {self.log_file_backup_count}"
            )

        # Check for potential disk space issues
        total_log_space = self.log_file_max_size * (self.log_file_backup_count + 1)
        if total_log_space > 500 * 1024 * 1024:  # 500MB
            total_mb = total_log_space / (1024 * 1024)
            result.add_warning(
                f"Total log file space usage could reach {total_mb:.1f}MB"
            )

    def _validate_tool_config(self, result: ValidationResult) -> None:
        """Validate tool configuration."""
        if self.use_system_tools and not self.download_tools:
            # This is fine - using only system tools
            pass
        elif not self.use_system_tools and not self.download_tools:
            result.add_error(
                "Cannot disable both system tools and tool downloads - "
                "no tools would be available"
            )

        # Validate download rate limit format
        if self.download_rate_limit:
            import re

            if not re.match(r"^\d+[KMG]?$", self.download_rate_limit, re.IGNORECASE):
                result.add_error(
                    f"Invalid download rate limit format: {self.download_rate_limit} "
                    "(expected format: 1M, 500K, etc.)"
                )

    def _validate_dvd_config(self, result: ValidationResult) -> None:
        """Validate DVD configuration."""
        # Check for menu title length constraints
        if self.menu_title and len(self.menu_title) > 100:
            title_len = len(self.menu_title)
            result.add_warning(
                f"Menu title is quite long ({title_len} chars) - "
                "may be truncated in DVD player"
            )

        # Check for non-ASCII characters in menu title
        if self.menu_title:
            try:
                self.menu_title.encode("ascii")
            except UnicodeEncodeError:
                result.add_warning(
                    "Menu title contains non-ASCII characters - "
                    "will be normalized for DVD compatibility"
                )

    def _validate_button_config(self, result: ValidationResult) -> None:
        """Validate button configuration."""
        if self.button_enabled:
            # Check button position makes sense for video format
            x, y = self.button_position
            width, height = self.button_size

            # Get expected resolution based on video format
            if self.video_format.upper() == "NTSC":
                max_x, max_y = 720, 480
            else:  # PAL
                max_x, max_y = 720, 576

            # Check if button fits within screen
            if x - width // 2 < 0 or x + width // 2 > max_x:
                result.add_warning(
                    f"Button horizontal position may be off-screen for "
                    f"{self.video_format}: x={x}, width={width}, "
                    f"screen_width={max_x}"
                )

            if y - height // 2 < 0 or y + height // 2 > max_y:
                result.add_warning(
                    f"Button vertical position may be off-screen for "
                    f"{self.video_format}: y={y}, height={height}, "
                    f"screen_height={max_y}"
                )

            # Check button text length
            if len(self.button_text) > 20:
                result.add_warning(
                    f"Button text is quite long ({len(self.button_text)} chars): "
                    f"'{self.button_text}' - may not fit in button"
                )

    def _validate_resource_config(self, result: ValidationResult) -> None:
        """Validate resource and performance configuration."""
        # Check if we're forcing both download and convert (may use excessive space)
        if self.force_download and self.force_convert:
            result.add_warning(
                "Both force_download and force_convert are enabled - "
                "this may use significant disk space"
            )

        # Check available disk space for configured directories
        try:
            for name, path in [
                ("cache", self.cache_dir),
                ("output", self.output_dir),
                ("temp", self.temp_dir),
            ]:
                if path.exists() or path.parent.exists():
                    check_path = path if path.exists() else path.parent
                    usage = shutil.disk_usage(check_path)
                    free_gb = usage.free / (1024**3)
                    if free_gb < 1.0:  # Less than 1GB free
                        result.add_error(
                            f"Insufficient disk space for {name} directory "
                            f"({check_path}): only {free_gb:.1f}GB available"
                        )
                    elif free_gb < 5.0:  # Less than 5GB free
                        result.add_warning(
                            f"Low disk space for {name} directory "
                            f"({check_path}): only {free_gb:.1f}GB available"
                        )
        except (OSError, AttributeError):
            # Can't check disk space on this system
            pass

    def validate_comprehensive(self) -> ValidationResult:
        """Perform comprehensive validation and return detailed results.

        This method provides detailed validation results without raising exceptions,
        allowing callers to handle validation issues as appropriate.

        Returns:
            ValidationResult with detailed error and warning information
        """
        result: ValidationResult = ValidationResult()

        # Re-run all validation checks
        try:
            self._validate_directory_config(result)
            self._validate_logging_config(result)
            self._validate_tool_config(result)
            self._validate_dvd_config(result)
            self._validate_resource_config(result)
        except Exception as e:
            result.add_error(f"Validation error: {e}")

        return result

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


def load_settings(
    config_file: Optional[Path] = None, validate: bool = True
) -> Settings:
    """Load application settings from configuration file and environment.

    Args:
        config_file: Optional path to configuration file.
                    If None, uses default location.
        validate: Whether to perform comprehensive validation and show warnings.

    Returns:
        Settings instance with loaded configuration.

    Raises:
        ConfigurationError: If validation fails with errors.
    """
    if config_file is None:
        config_file = get_default_config_file()

    settings = Settings.load_config(config_file)

    # Perform comprehensive validation if requested
    if validate:
        validation_result = settings.validate_comprehensive()

        # Log warnings
        for warning in validation_result.warnings:
            logging.warning(f"Configuration warning: {warning}")

        # Show validation summary if there are warnings
        if validation_result.has_warnings:
            logging.info(f"Configuration validation: {validation_result.get_summary()}")

    # Create necessary directories
    try:
        settings.create_directories()
    except OSError as e:
        logging.warning(f"Failed to create some directories: {e}")

    return settings


def validate_settings(settings: Settings, strict: bool = False) -> ValidationResult:
    """Validate settings configuration and return detailed results.

    This is a convenience function for validating settings objects
    without having to know the internal validation methods.

    Args:
        settings: Settings object to validate
        strict: If True, treats warnings as errors

    Returns:
        ValidationResult with detailed validation information
    """
    result = settings.validate_comprehensive()

    if strict and result.has_warnings:
        # Convert warnings to errors in strict mode
        for warning in result.warnings:
            result.add_error(f"Strict mode: {warning}")
        result.warnings.clear()

    return result
