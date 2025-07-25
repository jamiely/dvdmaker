"""Filename utilities for ASCII normalization and sanitization."""

import json
import re
from pathlib import Path
from typing import Dict, Optional

from unidecode import unidecode

from .logging import get_logger

logger = get_logger(__name__)


class FilenameMapper:
    """Manages mapping between original video IDs and normalized filenames."""

    def __init__(self, mapping_file: Path) -> None:
        """Initialize the filename mapper.

        Args:
            mapping_file: Path to the JSON file storing filename mappings
        """
        self.mapping_file = mapping_file
        self._mapping: Dict[str, str] = {}
        self._reverse_mapping: Dict[str, str] = {}
        self.load_mapping()

    def load_mapping(self) -> None:
        """Load filename mappings from disk."""
        logger.trace(  # type: ignore[attr-defined]
            f"Loading filename mapping from {self.mapping_file}"
        )

        if self.mapping_file.exists():
            try:
                with open(self.mapping_file, "r", encoding="utf-8") as f:
                    self._mapping = json.load(f)
                    self._reverse_mapping = {v: k for k, v in self._mapping.items()}
                logger.debug(
                    f"Loaded {len(self._mapping)} filename mappings from "
                    f"{self.mapping_file}"
                )
            except (json.JSONDecodeError, IOError) as e:
                # If file is corrupted, start fresh
                logger.warning(
                    f"Failed to load filename mapping from {self.mapping_file}: {e}, "
                    f"starting fresh"
                )
                self._mapping = {}
                self._reverse_mapping = {}
        else:
            logger.debug(
                f"Filename mapping file {self.mapping_file} does not exist, "
                f"starting with empty mapping"
            )

    def save_mapping(self) -> None:
        """Save filename mappings to disk."""
        logger.trace(  # type: ignore[attr-defined]
            f"Saving filename mapping to {self.mapping_file}"
        )
        self.mapping_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.mapping_file, "w", encoding="utf-8") as f:
                json.dump(self._mapping, f, indent=2, ensure_ascii=False)
            logger.debug(
                f"Saved {len(self._mapping)} filename mappings to {self.mapping_file}"
            )
        except IOError as e:
            logger.error(f"Failed to save filename mapping to {self.mapping_file}: {e}")
            raise RuntimeError(f"Failed to save filename mapping: {e}")

    def get_normalized_filename(self, video_id: str, original_title: str) -> str:
        """Get normalized filename for a video.

        Args:
            video_id: The video ID (used as key)
            original_title: The original video title

        Returns:
            The normalized filename
        """
        logger.trace(  # type: ignore[attr-defined]
            f"Getting normalized filename for video_id={video_id}, "
            f"title='{original_title}'"
        )

        if video_id in self._mapping:
            existing_filename = self._mapping[video_id]
            logger.debug(
                f"Found existing filename mapping for {video_id}: {existing_filename}"
            )
            return existing_filename

        # Generate new normalized filename
        normalized = normalize_filename(original_title)
        logger.trace(  # type: ignore[attr-defined]
            f"Normalized title '{original_title}' to '{normalized}'"
        )

        # Ensure uniqueness
        unique_normalized = self._ensure_unique_filename(normalized)

        # Store mapping
        self._mapping[video_id] = unique_normalized
        self._reverse_mapping[unique_normalized] = video_id
        logger.debug(f"Created new filename mapping: {video_id} -> {unique_normalized}")

        return unique_normalized

    def get_video_id(self, normalized_filename: str) -> Optional[str]:
        """Get video ID from normalized filename.

        Args:
            normalized_filename: The normalized filename

        Returns:
            The video ID if found, None otherwise
        """
        video_id = self._reverse_mapping.get(normalized_filename)
        if video_id:
            logger.trace(  # type: ignore[attr-defined]
                f"Found video_id {video_id} for filename '{normalized_filename}'"
            )
        else:
            logger.trace(  # type: ignore[attr-defined]
                f"No video_id found for filename '{normalized_filename}'"
            )
        return video_id

    def _ensure_unique_filename(self, filename: str) -> str:
        """Ensure filename is unique by adding suffix if needed.

        Args:
            filename: The base filename

        Returns:
            A unique filename
        """
        if filename not in self._reverse_mapping:
            logger.trace(  # type: ignore[attr-defined]
                f"Filename '{filename}' is unique"
            )
            return filename

        logger.trace(  # type: ignore[attr-defined]
            f"Filename '{filename}' already exists, finding unique variant"
        )

        # Extract name and extension
        path = Path(filename)
        name = path.stem
        suffix = path.suffix

        # Try with numeric suffixes
        counter = 1
        while True:
            candidate = f"{name}_{counter}{suffix}"
            if candidate not in self._reverse_mapping:
                logger.debug(
                    f"Generated unique filename: '{filename}' -> '{candidate}'"
                )
                return candidate
            counter += 1


def normalize_to_ascii(text: str) -> str:
    """Convert Unicode text to ASCII equivalents.

    Args:
        text: The text to normalize

    Returns:
        ASCII-normalized text
    """
    if not text:
        logger.trace(  # type: ignore[attr-defined]
            "normalize_to_ascii called with empty text"
        )
        return ""

    logger.trace(  # type: ignore[attr-defined]
        f"Normalizing text to ASCII: '{text[:50]}{'...' if len(text) > 50 else ''}'"
    )

    # Use unidecode to convert Unicode to ASCII
    ascii_text = unidecode(text)

    # Remove any remaining non-ASCII characters
    ascii_text = re.sub(r"[^\x00-\x7F]+", "", ascii_text)

    logger.trace(  # type: ignore[attr-defined]
        f"ASCII normalization result: '{ascii_text[:50]}"
        f"{'...' if len(ascii_text) > 50 else ''}'"
    )
    return ascii_text


def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """Sanitize a filename for filesystem compatibility.

    Args:
        filename: The filename to sanitize
        max_length: Maximum length for the filename

    Returns:
        Sanitized filename
    """
    if not filename:
        logger.trace(  # type: ignore[attr-defined]
            "sanitize_filename called with empty filename"
        )
        return "untitled"

    logger.trace(  # type: ignore[attr-defined]
        f"Sanitizing filename: '{filename}' (max_length={max_length})"
    )
    original_filename = filename

    # Remove or replace problematic characters
    # Replace multiple whitespace with single space
    sanitized = re.sub(r"\s+", " ", filename.strip())

    # Remove control characters
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", sanitized)

    # Replace filesystem-problematic characters
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", sanitized)

    # Remove leading/trailing dots and spaces (Windows issues)
    sanitized = sanitized.strip(". ")

    # Ensure we don't have only dots or empty string
    if not sanitized or sanitized == "." or sanitized == "..":
        logger.debug(
            f"Filename '{original_filename}' sanitized to 'untitled' (invalid result)"
        )
        sanitized = "untitled"

    # Truncate if too long, preserving extension
    if len(sanitized) > max_length:
        path = Path(sanitized)
        name = path.stem
        suffix = path.suffix

        # Calculate available space for name
        available_length = max_length - len(suffix)
        if available_length > 0:
            truncated_name = name[:available_length].rstrip()
            sanitized = f"{truncated_name}{suffix}"
            logger.debug(
                f"Filename truncated to fit max_length: '{original_filename}' -> "
                f"'{sanitized}'"
            )
        else:
            # Suffix is too long, just truncate everything
            sanitized = sanitized[:max_length]
            logger.debug(
                f"Filename truncated (including suffix): '{original_filename}' -> "
                f"'{sanitized}'"
            )

    if sanitized != original_filename:
        logger.debug(f"Filename sanitized: '{original_filename}' -> '{sanitized}'")
    else:
        logger.trace(  # type: ignore[attr-defined]
            f"Filename required no sanitization: '{filename}'"
        )

    return sanitized


def normalize_filename(original_title: str, max_length: int = 100) -> str:
    """Normalize a video title to a filesystem-safe ASCII filename.

    Args:
        original_title: The original video title
        max_length: Maximum length for the filename

    Returns:
        Normalized filename suitable for DVD filesystem
    """
    logger.trace(  # type: ignore[attr-defined]
        f"Normalizing filename from title: '{original_title}' "
        f"(max_length={max_length})"
    )

    if not original_title:
        logger.debug("Empty title provided, using default filename 'untitled.mp4'")
        return "untitled.mp4"

    # First normalize to ASCII
    ascii_title = normalize_to_ascii(original_title)

    # Then sanitize for filesystem
    sanitized = sanitize_filename(
        ascii_title, max_length - 4
    )  # Reserve space for extension

    # Add extension if not present
    if not Path(sanitized).suffix:
        sanitized += ".mp4"
        logger.trace(  # type: ignore[attr-defined]
            f"Added .mp4 extension to filename: '{sanitized}'"
        )

    logger.debug(f"Normalized filename: '{original_title}' -> '{sanitized}'")
    return sanitized


def generate_unique_filename(
    base_filename: str, existing_files: set[str], max_attempts: int = 1000
) -> str:
    """Generate a unique filename by adding numeric suffix if needed.

    Args:
        base_filename: The desired base filename
        existing_files: Set of existing filenames to avoid
        max_attempts: Maximum number of attempts to find unique name

    Returns:
        A unique filename

    Raises:
        RuntimeError: If unable to generate unique filename
    """
    logger.trace(  # type: ignore[attr-defined]
        f"Generating unique filename from base: '{base_filename}' "
        f"(checking against {len(existing_files)} existing files)"
    )

    if base_filename not in existing_files:
        logger.trace(  # type: ignore[attr-defined]
            f"Base filename '{base_filename}' is already unique"
        )
        return base_filename

    logger.debug(
        f"Base filename '{base_filename}' conflicts, generating unique variant"
    )
    path = Path(base_filename)
    name = path.stem
    suffix = path.suffix

    for i in range(1, max_attempts + 1):
        candidate = f"{name}_{i}{suffix}"
        if candidate not in existing_files:
            logger.debug(
                f"Generated unique filename: '{base_filename}' -> '{candidate}' "
                f"(attempt {i})"
            )
            return candidate

    logger.error(
        f"Failed to generate unique filename after {max_attempts} attempts "
        f"for '{base_filename}'"
    )
    raise RuntimeError(
        f"Unable to generate unique filename after {max_attempts} attempts"
    )


def is_valid_filename(filename: str) -> bool:
    """Check if a filename is valid for cross-platform use.

    Args:
        filename: The filename to validate

    Returns:
        True if filename is valid, False otherwise
    """
    logger.trace(f"Validating filename: '{filename}'")  # type: ignore[attr-defined]

    if not filename:
        logger.trace(  # type: ignore[attr-defined]
            "Filename validation failed: empty filename"
        )
        return False

    # Check for problematic characters
    if re.search(r'[<>:"/\\|?*\x00-\x1f\x7f-\x9f]', filename):
        logger.debug(
            f"Filename validation failed: problematic characters in '{filename}'"
        )
        return False

    # Check for reserved names on Windows
    reserved_names = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }

    name_without_ext = Path(filename).stem.upper()
    if name_without_ext in reserved_names:
        logger.debug(
            f"Filename validation failed: reserved name '{name_without_ext}' "
            f"in '{filename}'"
        )
        return False

    # Check for leading/trailing dots or spaces
    if filename.startswith(".") or filename.endswith(".") or filename.endswith(" "):
        logger.debug(
            f"Filename validation failed: invalid leading/trailing characters "
            f"in '{filename}'"
        )
        return False

    # Check length (filesystem dependent, but 255 is common limit)
    if len(filename.encode("utf-8")) > 255:
        logger.debug(
            f"Filename validation failed: too long "
            f"({len(filename.encode('utf-8'))} bytes) '{filename}'"
        )
        return False

    logger.trace(  # type: ignore[attr-defined]
        f"Filename validation passed: '{filename}'"
    )
    return True
