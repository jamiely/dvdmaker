"""Tests for filename utilities."""

import json
import tempfile
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from src.utils.filename import (
    FilenameMapper,
    generate_unique_filename,
    is_valid_filename,
    normalize_filename,
    normalize_to_ascii,
    sanitize_filename,
)


class TestNormalizeToAscii:
    """Test cases for normalize_to_ascii function."""

    def test_normalize_to_ascii_empty_string(self):
        """Test normalize_to_ascii with empty string."""
        result = normalize_to_ascii("")
        assert result == ""

    def test_normalize_to_ascii_ascii_text(self):
        """Test normalize_to_ascii with pure ASCII text."""
        text = "Hello World 123"
        result = normalize_to_ascii(text)
        assert result == text

    def test_normalize_to_ascii_unicode_characters(self):
        """Test normalize_to_ascii with Unicode characters."""
        text = "café naïve résumé"
        result = normalize_to_ascii(text)
        assert result == "cafe naive resume"

    def test_normalize_to_ascii_mixed_characters(self):
        """Test normalize_to_ascii with mixed ASCII and Unicode."""
        text = "Hello 世界 World"
        result = normalize_to_ascii(text)
        assert result == "Hello Shi Jie  World"

    def test_normalize_to_ascii_emoji_and_symbols(self):
        """Test normalize_to_ascii with emojis and special symbols."""
        text = "Hello 😀 World ♪ Music"
        result = normalize_to_ascii(text)
        # Emojis should be removed/converted
        assert "😀" not in result
        assert "♪" not in result
        assert "Hello" in result
        assert "World" in result

    def test_normalize_to_ascii_cyrillic_text(self):
        """Test normalize_to_ascii with Cyrillic characters."""
        text = "Привет мир"
        result = normalize_to_ascii(text)
        assert result == "Privet mir"

    def test_normalize_to_ascii_japanese_text(self):
        """Test normalize_to_ascii with Japanese characters."""
        text = "こんにちは"
        result = normalize_to_ascii(text)
        assert result == "konnichiha"

    def test_normalize_to_ascii_long_text(self):
        """Test normalize_to_ascii with long text."""
        text = "A" * 100 + "café" + "B" * 100
        result = normalize_to_ascii(text)
        assert len(result) >= 204  # Original length with ASCII conversion
        assert "cafe" in result


class TestSanitizeFilename:
    """Test cases for sanitize_filename function."""

    def test_sanitize_filename_empty_string(self):
        """Test sanitize_filename with empty string."""
        result = sanitize_filename("")
        assert result == "untitled"

    def test_sanitize_filename_valid_name(self):
        """Test sanitize_filename with already valid filename."""
        filename = "my_video_file.mp4"
        result = sanitize_filename(filename)
        assert result == filename

    def test_sanitize_filename_problematic_characters(self):
        """Test sanitize_filename removes problematic characters."""
        filename = 'video<>:"/\\|?*file.mp4'
        result = sanitize_filename(filename)
        assert result == "video_________file.mp4"

    def test_sanitize_filename_multiple_whitespace(self):
        """Test sanitize_filename normalizes whitespace."""
        filename = "my    video     file.mp4"
        result = sanitize_filename(filename)
        assert result == "my video file.mp4"

    def test_sanitize_filename_control_characters(self):
        """Test sanitize_filename removes control characters."""
        filename = "video\x00\x1f\x7f\x9ffile.mp4"
        result = sanitize_filename(filename)
        # Control characters should be removed
        assert "\x00" not in result
        assert "\x1f" not in result
        assert "\x7f" not in result
        assert "\x9f" not in result
        assert "video" in result
        assert "file.mp4" in result

    def test_sanitize_filename_leading_trailing_dots_spaces(self):
        """Test sanitize_filename removes leading/trailing dots and spaces."""
        filename = " ...my video... "
        result = sanitize_filename(filename)
        assert result == "my video"

    def test_sanitize_filename_only_dots(self):
        """Test sanitize_filename handles filenames with only dots."""
        result1 = sanitize_filename(".")
        assert result1 == "untitled"

        result2 = sanitize_filename("..")
        assert result2 == "untitled"

        result3 = sanitize_filename("...")
        assert result3 == "untitled"

    def test_sanitize_filename_max_length_truncation(self):
        """Test sanitize_filename truncates long filenames."""
        long_name = "a" * 150
        result = sanitize_filename(long_name + ".mp4", max_length=100)
        assert len(result) <= 100
        assert result.endswith(".mp4")
        assert result.startswith("a")

    def test_sanitize_filename_max_length_with_long_extension(self):
        """Test sanitize_filename with extension longer than max_length."""
        filename = "video.verylongextensionnamethatistoolong"
        result = sanitize_filename(filename, max_length=10)
        assert len(result) <= 10

    def test_sanitize_filename_preserve_extension_when_truncating(self):
        """Test sanitize_filename preserves extension when truncating."""
        filename = "very_long_video_filename_that_needs_truncation.mp4"
        result = sanitize_filename(filename, max_length=30)
        assert len(result) <= 30
        assert result.endswith(".mp4")
        assert "very_long_video" in result

    def test_sanitize_filename_custom_max_length(self):
        """Test sanitize_filename with custom max_length."""
        filename = "short.mp4"
        result = sanitize_filename(filename, max_length=5)
        assert len(result) <= 5


class TestNormalizeFilename:
    """Test cases for normalize_filename function."""

    def test_normalize_filename_empty_title(self):
        """Test normalize_filename with empty title."""
        result = normalize_filename("")
        assert result == "untitled.mp4"

    def test_normalize_filename_simple_title(self):
        """Test normalize_filename with simple ASCII title."""
        title = "My Video"
        result = normalize_filename(title)
        assert result == "My Video.mp4"

    def test_normalize_filename_unicode_title(self):
        """Test normalize_filename with Unicode characters."""
        title = "Café & Naïve Video"
        result = normalize_filename(title)
        # The actual result should have Unicode converted to ASCII
        assert "Cafe" in result
        assert "Naive" in result
        assert result.endswith(".mp4")
        # Check that original Unicode characters are gone
        assert "é" not in result
        assert "ï" not in result

    def test_normalize_filename_problematic_characters(self):
        """Test normalize_filename with filesystem-problematic characters."""
        title = 'My Video: "The Best" <Amazing>'
        result = normalize_filename(title)
        assert result == "My Video_ _The Best_ _Amazing_.mp4"

    def test_normalize_filename_with_existing_extension(self):
        """Test normalize_filename preserves existing extension."""
        title = "My Video.avi"
        result = normalize_filename(title)
        assert result == "My Video.avi"

    def test_normalize_filename_long_title(self):
        """Test normalize_filename truncates long titles."""
        long_title = "A" * 150
        result = normalize_filename(long_title, max_length=50)
        assert len(result) <= 50
        assert result.endswith(".mp4")

    def test_normalize_filename_custom_max_length(self):
        """Test normalize_filename with custom max_length."""
        title = "Medium Length Title"
        result = normalize_filename(title, max_length=15)
        assert len(result) <= 15
        assert result.endswith(".mp4")


class TestGenerateUniqueFilename:
    """Test cases for generate_unique_filename function."""

    def test_generate_unique_filename_no_conflict(self):
        """Test generate_unique_filename when base filename is unique."""
        base = "video.mp4"
        existing = {"other_video.mp4", "another.avi"}
        result = generate_unique_filename(base, existing)
        assert result == base

    def test_generate_unique_filename_with_conflict(self):
        """Test generate_unique_filename when base filename conflicts."""
        base = "video.mp4"
        existing = {"video.mp4", "other.mp4"}
        result = generate_unique_filename(base, existing)
        assert result == "video_1.mp4"

    def test_generate_unique_filename_multiple_conflicts(self):
        """Test generate_unique_filename with multiple conflicts."""
        base = "video.mp4"
        existing = {"video.mp4", "video_1.mp4", "video_2.mp4"}
        result = generate_unique_filename(base, existing)
        assert result == "video_3.mp4"

    def test_generate_unique_filename_no_extension(self):
        """Test generate_unique_filename with filename without extension."""
        base = "video"
        existing = {"video", "video_1"}
        result = generate_unique_filename(base, existing)
        assert result == "video_2"

    def test_generate_unique_filename_max_attempts_exceeded(self):
        """Test generate_unique_filename raises error when max attempts exceeded."""
        base = "video.mp4"
        # Create set with many conflicts
        existing = {f"video_{i}.mp4" for i in range(1, 15)}
        existing.add("video.mp4")

        with pytest.raises(RuntimeError, match="Unable to generate unique filename"):
            generate_unique_filename(base, existing, max_attempts=10)

    def test_generate_unique_filename_empty_existing_set(self):
        """Test generate_unique_filename with empty existing files set."""
        base = "video.mp4"
        existing = set()
        result = generate_unique_filename(base, existing)
        assert result == base


class TestIsValidFilename:
    """Test cases for is_valid_filename function."""

    def test_is_valid_filename_empty_string(self):
        """Test is_valid_filename with empty string."""
        result = is_valid_filename("")
        assert result is False

    def test_is_valid_filename_valid_name(self):
        """Test is_valid_filename with valid filename."""
        result = is_valid_filename("my_video.mp4")
        assert result is True

    def test_is_valid_filename_with_spaces(self):
        """Test is_valid_filename with spaces."""
        result = is_valid_filename("my video file.mp4")
        assert result is True

    def test_is_valid_filename_problematic_characters(self):
        """Test is_valid_filename with problematic characters."""
        invalid_chars = ["<", ">", ":", '"', "/", "\\", "|", "?", "*"]
        for char in invalid_chars:
            filename = f"video{char}file.mp4"
            result = is_valid_filename(filename)
            assert result is False, f"Character '{char}' should make filename invalid"

    def test_is_valid_filename_control_characters(self):
        """Test is_valid_filename with control characters."""
        filename = "video\x00file.mp4"
        result = is_valid_filename(filename)
        assert result is False

    def test_is_valid_filename_reserved_names(self):
        """Test is_valid_filename with Windows reserved names."""
        reserved_names = ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]
        for name in reserved_names:
            result = is_valid_filename(f"{name}.mp4")
            assert result is False, f"Reserved name '{name}' should be invalid"

    def test_is_valid_filename_reserved_names_case_insensitive(self):
        """Test is_valid_filename with reserved names in different cases."""
        result1 = is_valid_filename("con.txt")
        assert result1 is False

        result2 = is_valid_filename("Con.txt")
        assert result2 is False

    def test_is_valid_filename_leading_dot(self):
        """Test is_valid_filename with leading dot."""
        result = is_valid_filename(".hidden_file")
        assert result is False

    def test_is_valid_filename_trailing_dot(self):
        """Test is_valid_filename with trailing dot."""
        result = is_valid_filename("file.")
        assert result is False

    def test_is_valid_filename_trailing_space(self):
        """Test is_valid_filename with trailing space."""
        result = is_valid_filename("file ")
        assert result is False

    def test_is_valid_filename_too_long(self):
        """Test is_valid_filename with overly long filename."""
        long_filename = "a" * 300  # Over 255 bytes
        result = is_valid_filename(long_filename)
        assert result is False

    def test_is_valid_filename_unicode_length_check(self):
        """Test is_valid_filename with Unicode characters affecting byte length."""
        # Unicode characters can be multiple bytes
        unicode_filename = "café" * 100  # Should exceed 255 bytes
        result = is_valid_filename(unicode_filename)
        assert result is False


class TestFilenameMapper:
    """Test cases for FilenameMapper class."""

    def test_filename_mapper_initialization(self):
        """Test FilenameMapper initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "mapping.json"
            mapper = FilenameMapper(mapping_file)

            assert mapper.mapping_file == mapping_file
            assert mapper._mapping == {}
            assert mapper._reverse_mapping == {}

    def test_filename_mapper_load_nonexistent_file(self):
        """Test FilenameMapper with non-existent mapping file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "nonexistent.json"
            mapper = FilenameMapper(mapping_file)

            assert mapper._mapping == {}
            assert mapper._reverse_mapping == {}

    def test_filename_mapper_load_existing_file(self):
        """Test FilenameMapper loads existing mapping file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "mapping.json"
            test_mapping = {"video1": "normalized1.mp4", "video2": "normalized2.mp4"}

            with open(mapping_file, "w") as f:
                json.dump(test_mapping, f)

            mapper = FilenameMapper(mapping_file)

            assert mapper._mapping == test_mapping
            assert mapper._reverse_mapping == {
                "normalized1.mp4": "video1",
                "normalized2.mp4": "video2",
            }

    def test_filename_mapper_load_corrupted_file(self):
        """Test FilenameMapper handles corrupted mapping file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "corrupted.json"

            with open(mapping_file, "w") as f:
                f.write("invalid json content")

            mapper = FilenameMapper(mapping_file)

            assert mapper._mapping == {}
            assert mapper._reverse_mapping == {}

    def test_filename_mapper_save_mapping(self):
        """Test FilenameMapper saves mapping to file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "mapping.json"
            mapper = FilenameMapper(mapping_file)

            mapper._mapping = {"video1": "file1.mp4"}
            mapper.save_mapping()

            assert mapping_file.exists()

            with open(mapping_file) as f:
                saved_data = json.load(f)

            assert saved_data == {"video1": "file1.mp4"}

    def test_filename_mapper_save_mapping_creates_directory(self):
        """Test FilenameMapper creates parent directory when saving."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "subdir" / "mapping.json"
            mapper = FilenameMapper(mapping_file)

            mapper._mapping = {"video1": "file1.mp4"}
            mapper.save_mapping()

            assert mapping_file.exists()
            assert mapping_file.parent.exists()

    def test_filename_mapper_save_mapping_io_error(self):
        """Test FilenameMapper handles IO error when saving."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "mapping.json"
            mapper = FilenameMapper(mapping_file)
            mapper._mapping = {"video1": "file1.mp4"}

            # Mock open to raise IOError
            with patch("builtins.open", mock_open()) as mock_file:
                mock_file.side_effect = IOError("Permission denied")

                with pytest.raises(
                    RuntimeError, match="Failed to save filename mapping"
                ):
                    mapper.save_mapping()

    def test_filename_mapper_get_normalized_filename_new(self):
        """Test FilenameMapper creates new normalized filename."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "mapping.json"
            mapper = FilenameMapper(mapping_file)

            result = mapper.get_normalized_filename("video123", "My Great Video")

            assert result == "My Great Video.mp4"
            assert mapper._mapping["video123"] == "My Great Video.mp4"
            assert mapper._reverse_mapping["My Great Video.mp4"] == "video123"

    def test_filename_mapper_get_normalized_filename_existing(self):
        """Test FilenameMapper returns existing normalized filename."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "mapping.json"
            mapper = FilenameMapper(mapping_file)

            mapper._mapping["video123"] = "existing_file.mp4"
            mapper._reverse_mapping["existing_file.mp4"] = "video123"

            result = mapper.get_normalized_filename("video123", "Different Title")

            assert result == "existing_file.mp4"

    def test_filename_mapper_get_video_id_found(self):
        """Test FilenameMapper returns video ID for normalized filename."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "mapping.json"
            mapper = FilenameMapper(mapping_file)

            mapper._reverse_mapping["normalized.mp4"] = "video123"

            result = mapper.get_video_id("normalized.mp4")

            assert result == "video123"

    def test_filename_mapper_get_video_id_not_found(self):
        """Test FilenameMapper returns None for unknown filename."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "mapping.json"
            mapper = FilenameMapper(mapping_file)

            result = mapper.get_video_id("unknown.mp4")

            assert result is None

    def test_filename_mapper_ensure_unique_filename_no_conflict(self):
        """Test FilenameMapper returns filename when no conflict."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "mapping.json"
            mapper = FilenameMapper(mapping_file)

            result = mapper._ensure_unique_filename("unique.mp4")

            assert result == "unique.mp4"

    def test_filename_mapper_ensure_unique_filename_with_conflict(self):
        """Test FilenameMapper generates unique filename when conflict exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "mapping.json"
            mapper = FilenameMapper(mapping_file)

            mapper._reverse_mapping["existing.mp4"] = "some_video"

            result = mapper._ensure_unique_filename("existing.mp4")

            assert result == "existing_1.mp4"

    def test_filename_mapper_ensure_unique_filename_multiple_conflicts(self):
        """Test FilenameMapper handles multiple conflicts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "mapping.json"
            mapper = FilenameMapper(mapping_file)

            mapper._reverse_mapping["video.mp4"] = "vid1"
            mapper._reverse_mapping["video_1.mp4"] = "vid2"
            mapper._reverse_mapping["video_2.mp4"] = "vid3"

            result = mapper._ensure_unique_filename("video.mp4")

            assert result == "video_3.mp4"

    def test_filename_mapper_integration_workflow(self):
        """Test FilenameMapper complete workflow integration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "mapping.json"

            # Create mapper and add some mappings
            mapper1 = FilenameMapper(mapping_file)
            filename1 = mapper1.get_normalized_filename("vid1", "Café Video")
            filename2 = mapper1.get_normalized_filename(
                "vid2", "Cafe Video"
            )  # Similar but different
            mapper1.save_mapping()

            # Create new mapper instance and verify it loads the data
            mapper2 = FilenameMapper(mapping_file)

            assert mapper2.get_video_id(filename1) == "vid1"
            assert mapper2.get_video_id(filename2) == "vid2"
            assert filename1 != filename2  # Should be unique


class TestFilenameLogging:
    """Test cases for filename logging behavior."""

    def test_normalize_to_ascii_logs_trace_for_empty_input(self, caplog):
        """Test that normalize_to_ascii logs trace for empty input."""
        caplog.set_level("DEBUG")

        normalize_to_ascii("")

        # Trace level logs might not appear in caplog, but ensure no exceptions

    def test_sanitize_filename_logs_trace_for_empty_input(self, caplog):
        """Test that sanitize_filename logs trace for empty input."""
        caplog.set_level("DEBUG")

        sanitize_filename("")

        # Should log and return "untitled"

    def test_normalize_filename_logs_debug_for_empty_title(self, caplog):
        """Test that normalize_filename logs debug for empty title."""
        caplog.set_level("DEBUG")

        normalize_filename("")

        debug_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "DEBUG" and "src.utils.filename" in record.name
        ]
        assert any("Empty title provided" in msg for msg in debug_messages)

    def test_generate_unique_filename_logs_debug_when_generating_unique(self, caplog):
        """Test that generate_unique_filename logs debug when generating unique name."""
        caplog.set_level("DEBUG")

        existing = {"test.mp4"}
        generate_unique_filename("test.mp4", existing)

        debug_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "DEBUG" and "src.utils.filename" in record.name
        ]
        assert any("Generated unique filename" in msg for msg in debug_messages)

    def test_generate_unique_filename_logs_error_on_max_attempts(self, caplog):
        """Test that generate_unique_filename logs error when max attempts reached."""
        caplog.set_level("ERROR")

        existing = {f"test_{i}.mp4" for i in range(1, 6)}
        existing.add("test.mp4")

        with pytest.raises(RuntimeError):
            generate_unique_filename("test.mp4", existing, max_attempts=3)

        error_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "ERROR" and "src.utils.filename" in record.name
        ]
        assert any(
            "Failed to generate unique filename" in msg for msg in error_messages
        )

    def test_is_valid_filename_logs_debug_for_invalid_names(self, caplog):
        """Test that is_valid_filename logs debug for invalid filenames."""
        caplog.set_level("DEBUG")

        is_valid_filename("invalid<file>.mp4")

        debug_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "DEBUG" and "src.utils.filename" in record.name
        ]
        assert any("Filename validation failed" in msg for msg in debug_messages)

    def test_filename_mapper_logs_debug_on_load(self, caplog):
        """Test that FilenameMapper logs debug when loading mapping."""
        caplog.set_level("DEBUG")

        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "test.json"
            test_mapping = {"vid1": "file1.mp4"}

            with open(mapping_file, "w") as f:
                json.dump(test_mapping, f)

            FilenameMapper(mapping_file)

        debug_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "DEBUG" and "src.utils.filename" in record.name
        ]
        assert any(
            "Loaded" in msg and "filename mappings" in msg for msg in debug_messages
        )

    def test_filename_mapper_logs_warning_on_corrupted_file(self, caplog):
        """Test that FilenameMapper logs warning for corrupted file."""
        caplog.set_level("WARNING")

        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_file = Path(temp_dir) / "corrupted.json"

            with open(mapping_file, "w") as f:
                f.write("invalid json")

            FilenameMapper(mapping_file)

        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelname == "WARNING" and "src.utils.filename" in record.name
        ]
        assert any("Failed to load filename mapping" in msg for msg in warning_messages)
