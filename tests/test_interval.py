# ABOUTME: Tests for interval parsing utility
# ABOUTME: Verifies parsing of duration strings like "30m", "1h", "2h30m" into timedelta objects

from datetime import timedelta

import pytest

from herald.heartbeat.interval import parse_interval


class TestParseInterval:
    """Test suite for interval parsing functionality."""

    def test_parse_minutes_only(self):
        """Test parsing minutes-only duration strings."""
        result = parse_interval("30m")
        assert result == timedelta(minutes=30)

    def test_parse_hours_only(self):
        """Test parsing hours-only duration strings."""
        result = parse_interval("1h")
        assert result == timedelta(hours=1)

    def test_parse_seconds_only(self):
        """Test parsing seconds-only duration strings."""
        result = parse_interval("90s")
        assert result == timedelta(seconds=90)

    def test_parse_days_only(self):
        """Test parsing days-only duration strings."""
        result = parse_interval("2d")
        assert result == timedelta(days=2)

    def test_parse_combined_hours_minutes(self):
        """Test parsing combined hour and minute durations."""
        result = parse_interval("2h30m")
        assert result == timedelta(hours=2, minutes=30)

    def test_parse_combined_days_hours(self):
        """Test parsing combined day and hour durations."""
        result = parse_interval("1d12h")
        assert result == timedelta(days=1, hours=12)

    def test_parse_complex_combination(self):
        """Test parsing complex multi-unit durations."""
        result = parse_interval("1d2h30m45s")
        assert result == timedelta(days=1, hours=2, minutes=30, seconds=45)

    def test_parse_empty_string_uses_default(self):
        """Test that empty string defaults to 30 minutes."""
        result = parse_interval("")
        assert result == timedelta(minutes=30)

    def test_parse_none_uses_default(self):
        """Test that None defaults to 30 minutes."""
        result = parse_interval(None)
        assert result == timedelta(minutes=30)

    def test_parse_whitespace_only_uses_default(self):
        """Test that whitespace-only string defaults to 30 minutes."""
        result = parse_interval("   ")
        assert result == timedelta(minutes=30)

    def test_parse_invalid_format_raises_error(self):
        """Test that invalid formats raise ValueError."""
        with pytest.raises(ValueError, match="Invalid duration format"):
            parse_interval("invalid")

    def test_parse_unknown_unit_raises_error(self):
        """Test that unknown units raise ValueError."""
        with pytest.raises(ValueError, match="Invalid duration format"):
            parse_interval("30x")

    def test_parse_negative_value_raises_error(self):
        """Test that negative values raise ValueError."""
        with pytest.raises(ValueError, match="Duration values must be positive"):
            parse_interval("-30m")

    def test_parse_zero_value_raises_error(self):
        """Test that zero values raise ValueError."""
        with pytest.raises(ValueError, match="Duration values must be positive"):
            parse_interval("0m")

    def test_parse_float_values(self):
        """Test that float values are supported."""
        result = parse_interval("1.5h")
        assert result == timedelta(hours=1.5)

    def test_parse_large_numbers(self):
        """Test parsing large duration values."""
        result = parse_interval("365d")
        assert result == timedelta(days=365)

    def test_parse_case_insensitive(self):
        """Test that units are case-insensitive."""
        result = parse_interval("30M")
        assert result == timedelta(minutes=30)

    def test_parse_with_spaces(self):
        """Test parsing durations with spaces between components."""
        result = parse_interval("2h 30m")
        assert result == timedelta(hours=2, minutes=30)
