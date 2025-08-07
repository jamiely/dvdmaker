"""Console output utilities with color support for DVD Maker."""

import sys
from typing import Optional


class Colors:
    """ANSI color codes for console output."""

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"


def supports_color() -> bool:
    """Check if the terminal supports ANSI color codes."""
    # Check if we're in a terminal and not piping output
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False

    # Check environment variables that indicate color support
    term = sys.platform
    if term == "win32":
        # Windows 10+ supports ANSI colors in newer terminals
        import os

        return (
            os.environ.get("TERM", "").lower() in ("xterm", "xterm-256color")
            or "ANSICON" in os.environ
        )

    # Unix-like systems usually support colors
    return True


def print_error(message: str, title: Optional[str] = None) -> None:
    """Print an error message in red color.

    Args:
        message: The error message to display
        title: Optional title/prefix for the error
    """
    if supports_color():
        if title:
            formatted = (
                f"{Colors.RED}{Colors.BOLD}{title}:{Colors.RESET} "
                f"{Colors.RED}{message}{Colors.RESET}"
            )
        else:
            formatted = f"{Colors.RED}{message}{Colors.RESET}"
    else:
        if title:
            formatted = f"{title}: {message}"
        else:
            formatted = message

    print(formatted, file=sys.stderr, flush=True)


def print_warning(message: str, title: Optional[str] = None) -> None:
    """Print a warning message in yellow color.

    Args:
        message: The warning message to display
        title: Optional title/prefix for the warning
    """
    if supports_color():
        if title:
            formatted = (
                f"{Colors.YELLOW}{Colors.BOLD}{title}:{Colors.RESET} "
                f"{Colors.YELLOW}{message}{Colors.RESET}"
            )
        else:
            formatted = f"{Colors.YELLOW}{message}{Colors.RESET}"
    else:
        if title:
            formatted = f"{title}: {message}"
        else:
            formatted = message

    print(formatted, file=sys.stderr, flush=True)


def print_success(message: str, title: Optional[str] = None) -> None:
    """Print a success message in green color.

    Args:
        message: The success message to display
        title: Optional title/prefix for the success message
    """
    if supports_color():
        if title:
            formatted = (
                f"{Colors.GREEN}{Colors.BOLD}{title}:{Colors.RESET} "
                f"{Colors.GREEN}{message}{Colors.RESET}"
            )
        else:
            formatted = f"{Colors.GREEN}{message}{Colors.RESET}"
    else:
        if title:
            formatted = f"{title}: {message}"
        else:
            formatted = message

    print(formatted, flush=True)


def print_info(message: str, title: Optional[str] = None) -> None:
    """Print an info message in blue color.

    Args:
        message: The info message to display
        title: Optional title/prefix for the info message
    """
    if supports_color():
        if title:
            formatted = (
                f"{Colors.BLUE}{Colors.BOLD}{title}:{Colors.RESET} "
                f"{Colors.BLUE}{message}{Colors.RESET}"
            )
        else:
            formatted = f"{Colors.BLUE}{message}{Colors.RESET}"
    else:
        if title:
            formatted = f"{title}: {message}"
        else:
            formatted = message

    print(formatted, flush=True)
