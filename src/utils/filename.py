"""Filename utilities for ASCII normalization and sanitization."""

import json
import re
from pathlib import Path
from typing import Dict, Optional

from unidecode import unidecode


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
        if self.mapping_file.exists():
            try:
                with open(self.mapping_file, "r", encoding="utf-8") as f:
                    self._mapping = json.load(f)
                    self._reverse_mapping = {v: k for k, v in self._mapping.items()}
            except (json.JSONDecodeError, IOError):
                # If file is corrupted, start fresh
                self._mapping = {}
                self._reverse_mapping = {}

    def save_mapping(self) -> None:
        """Save filename mappings to disk."""
        self.mapping_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.mapping_file, "w", encoding="utf-8") as f:
                json.dump(self._mapping, f, indent=2, ensure_ascii=False)
        except IOError as e:
            raise RuntimeError(f"Failed to save filename mapping: {e}")

    def get_normalized_filename(self, video_id: str, original_title: str) -> str:
        """Get normalized filename for a video.

        Args:
            video_id: The video ID (used as key)
            original_title: The original video title

        Returns:
            The normalized filename
        """
        if video_id in self._mapping:
            return self._mapping[video_id]

        # Generate new normalized filename
        normalized = normalize_filename(original_title)

        # Ensure uniqueness
        unique_normalized = self._ensure_unique_filename(normalized)

        # Store mapping
        self._mapping[video_id] = unique_normalized
        self._reverse_mapping[unique_normalized] = video_id

        return unique_normalized

    def get_video_id(self, normalized_filename: str) -> Optional[str]:
        """Get video ID from normalized filename.

        Args:
            normalized_filename: The normalized filename

        Returns:
            The video ID if found, None otherwise
        """
        return self._reverse_mapping.get(normalized_filename)

    def _ensure_unique_filename(self, filename: str) -> str:
        """Ensure filename is unique by adding suffix if needed.

        Args:
            filename: The base filename

        Returns:
            A unique filename
        """
        if filename not in self._reverse_mapping:
            return filename

        # Extract name and extension
        path = Path(filename)
        name = path.stem
        suffix = path.suffix

        # Try with numeric suffixes
        counter = 1
        while True:
            candidate = f"{name}_{counter}{suffix}"
            if candidate not in self._reverse_mapping:
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
        return ""

    # Use unidecode to convert Unicode to ASCII
    ascii_text = unidecode(text)

    # Remove any remaining non-ASCII characters
    ascii_text = re.sub(r"[^\x00-\x7F]+", "", ascii_text)

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
        return "untitled"

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
        else:
            # Suffix is too long, just truncate everything
            sanitized = sanitized[:max_length]

    return sanitized


def normalize_filename(original_title: str, max_length: int = 100) -> str:
    """Normalize a video title to a filesystem-safe ASCII filename.

    Args:
        original_title: The original video title
        max_length: Maximum length for the filename

    Returns:
        Normalized filename suitable for DVD filesystem
    """
    if not original_title:
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
    if base_filename not in existing_files:
        return base_filename

    path = Path(base_filename)
    name = path.stem
    suffix = path.suffix

    for i in range(1, max_attempts + 1):
        candidate = f"{name}_{i}{suffix}"
        if candidate not in existing_files:
            return candidate

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
    if not filename:
        return False

    # Check for problematic characters
    if re.search(r'[<>:"/\\|?*\x00-\x1f\x7f-\x9f]', filename):
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
        return False

    # Check for leading/trailing dots or spaces
    if filename.startswith(".") or filename.endswith(".") or filename.endswith(" "):
        return False

    # Check length (filesystem dependent, but 255 is common limit)
    if len(filename.encode("utf-8")) > 255:
        return False

    return True
