"""Test time formatting utilities."""

from src.utils.time_format import format_duration_human_readable


class TestFormatDurationHumanReadable:
    """Test format_duration_human_readable function."""

    def test_seconds_only(self):
        """Test formatting seconds only."""
        assert format_duration_human_readable(0) == "0s"
        assert format_duration_human_readable(1) == "1s"
        assert format_duration_human_readable(30) == "30s"
        assert format_duration_human_readable(59) == "59s"

    def test_minutes_and_seconds(self):
        """Test formatting minutes and seconds."""
        assert format_duration_human_readable(60) == "1m"
        assert format_duration_human_readable(61) == "1m 1s"
        assert format_duration_human_readable(90) == "1m 30s"
        assert format_duration_human_readable(120) == "2m"
        assert format_duration_human_readable(3599) == "59m 59s"

    def test_hours_minutes_seconds(self):
        """Test formatting hours, minutes, and seconds."""
        assert format_duration_human_readable(3600) == "1h"
        assert format_duration_human_readable(3601) == "1h 1s"
        assert format_duration_human_readable(3660) == "1h 1m"
        assert format_duration_human_readable(3661) == "1h 1m 1s"
        assert format_duration_human_readable(7200) == "2h"
        assert format_duration_human_readable(7260) == "2h 1m"
        assert format_duration_human_readable(7261) == "2h 1m 1s"

    def test_common_durations(self):
        """Test common real-world durations."""
        # 5 minutes
        assert format_duration_human_readable(300) == "5m"

        # 10 minutes 30 seconds
        assert format_duration_human_readable(630) == "10m 30s"

        # 1 hour 27 minutes 34 seconds (from user example)
        assert format_duration_human_readable(1654) == "27m 34s"

        # 1 hour 30 minutes
        assert format_duration_human_readable(5400) == "1h 30m"

        # 2 hours 15 minutes 45 seconds
        assert format_duration_human_readable(8145) == "2h 15m 45s"

    def test_edge_cases(self):
        """Test edge cases."""
        # Negative values
        assert format_duration_human_readable(-1) == "0s"
        assert format_duration_human_readable(-100) == "0s"

        # Large values
        assert format_duration_human_readable(86400) == "24h"  # 1 day
        assert format_duration_human_readable(90061) == "25h 1m 1s"  # > 1 day

    def test_exact_boundaries(self):
        """Test exact boundary values."""
        # Exactly 1 minute
        assert format_duration_human_readable(60) == "1m"

        # Exactly 1 hour
        assert format_duration_human_readable(3600) == "1h"

        # Just under 1 minute
        assert format_duration_human_readable(59) == "59s"

        # Just under 1 hour
        assert format_duration_human_readable(3599) == "59m 59s"
