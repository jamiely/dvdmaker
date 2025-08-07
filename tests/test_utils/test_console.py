"""Tests for console output utilities."""

import io
import unittest
from unittest.mock import patch

from src.utils.console import (
    Colors,
    print_error,
    print_info,
    print_success,
    print_warning,
    supports_color,
)


class TestColors(unittest.TestCase):
    """Test color constants."""

    def test_color_constants_exist(self):
        """Test that all color constants are defined."""
        self.assertTrue(hasattr(Colors, "RED"))
        self.assertTrue(hasattr(Colors, "GREEN"))
        self.assertTrue(hasattr(Colors, "YELLOW"))
        self.assertTrue(hasattr(Colors, "BLUE"))
        self.assertTrue(hasattr(Colors, "RESET"))
        self.assertTrue(hasattr(Colors, "BOLD"))


class TestSupportsColor(unittest.TestCase):
    """Test color support detection."""

    @patch("sys.stdout")
    def test_supports_color_no_tty(self, mock_stdout):
        """Test color support when not in a TTY."""
        mock_stdout.isatty.return_value = False
        self.assertFalse(supports_color())

    @patch("sys.platform", "linux")
    @patch("sys.stdout")
    def test_supports_color_unix_with_tty(self, mock_stdout):
        """Test color support on Unix systems with TTY."""
        mock_stdout.isatty.return_value = True
        self.assertTrue(supports_color())


class TestColoredPrint(unittest.TestCase):
    """Test colored print functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.stderr_buffer = io.StringIO()
        self.stdout_buffer = io.StringIO()

    def test_print_error_with_color_support(self):
        """Test print_error with color support."""
        with patch("src.utils.console.supports_color", return_value=True):
            with patch("sys.stderr", self.stderr_buffer):
                print_error("Test error message")
                output = self.stderr_buffer.getvalue()
                self.assertIn("Test error message", output)
                self.assertIn(Colors.RED, output)
                self.assertIn(Colors.RESET, output)

    def test_print_error_without_color_support(self):
        """Test print_error without color support."""
        with patch("src.utils.console.supports_color", return_value=False):
            with patch("sys.stderr", self.stderr_buffer):
                print_error("Test error message")
                output = self.stderr_buffer.getvalue()
                self.assertIn("Test error message", output)
                self.assertNotIn(Colors.RED, output)

    def test_print_error_with_title(self):
        """Test print_error with title."""
        with patch("src.utils.console.supports_color", return_value=True):
            with patch("sys.stderr", self.stderr_buffer):
                print_error("Test error message", "ERROR")
                output = self.stderr_buffer.getvalue()
                self.assertIn("ERROR:", output)
                self.assertIn("Test error message", output)

    def test_print_warning_with_color_support(self):
        """Test print_warning with color support."""
        with patch("src.utils.console.supports_color", return_value=True):
            with patch("sys.stderr", self.stderr_buffer):
                print_warning("Test warning message")
                output = self.stderr_buffer.getvalue()
                self.assertIn("Test warning message", output)
                self.assertIn(Colors.YELLOW, output)

    def test_print_success_with_color_support(self):
        """Test print_success with color support."""
        with patch("src.utils.console.supports_color", return_value=True):
            with patch("sys.stdout", self.stdout_buffer):
                print_success("Test success message")
                output = self.stdout_buffer.getvalue()
                self.assertIn("Test success message", output)
                self.assertIn(Colors.GREEN, output)

    def test_print_info_with_color_support(self):
        """Test print_info with color support."""
        with patch("src.utils.console.supports_color", return_value=True):
            with patch("sys.stdout", self.stdout_buffer):
                print_info("Test info message")
                output = self.stdout_buffer.getvalue()
                self.assertIn("Test info message", output)
                self.assertIn(Colors.BLUE, output)
