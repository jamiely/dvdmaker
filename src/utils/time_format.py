"""Time formatting utilities."""


def format_duration_human_readable(duration_seconds: int) -> str:
    """Format duration in seconds to a human-readable string.

    Args:
        duration_seconds: Duration in seconds

    Returns:
        Formatted duration string (e.g., "1h 23m 45s", "23m 45s", "45s")
    """
    if duration_seconds < 0:
        return "0s"

    hours = duration_seconds // 3600
    minutes = (duration_seconds % 3600) // 60
    seconds = duration_seconds % 60

    parts = []

    if hours > 0:
        parts.append(f"{hours}h")

    if minutes > 0:
        parts.append(f"{minutes}m")

    if (
        seconds > 0 or not parts
    ):  # Always show seconds if it's the only component or if there are seconds
        parts.append(f"{seconds}s")

    return " ".join(parts)
