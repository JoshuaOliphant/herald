# ABOUTME: Unit tests for active hours validation and time window checking.
# ABOUTME: Tests parsing, timezone handling, and edge cases like overnight windows.

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from herald.heartbeat.active_hours import is_within_active_hours


class TestActiveHoursBasic:
    """Test basic active hours validation."""

    def test_none_active_hours_always_returns_true(self):
        """When active_hours is None, there are no restrictions."""
        assert is_within_active_hours(None) is True

    def test_empty_string_always_returns_true(self):
        """When active_hours is empty string, there are no restrictions."""
        assert is_within_active_hours("") is True
        assert is_within_active_hours("  ") is True

    def test_within_simple_range(self):
        """Test time within a simple range like 09:00-17:00."""
        # Mock current time to 12:00 UTC
        now = datetime(2026, 2, 3, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("09:00-17:00", tz="UTC", now=now)
        assert result is True

    def test_before_simple_range(self):
        """Test time before the active window."""
        # Mock current time to 08:00 UTC
        now = datetime(2026, 2, 3, 8, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("09:00-17:00", tz="UTC", now=now)
        assert result is False

    def test_after_simple_range(self):
        """Test time after the active window."""
        # Mock current time to 18:00 UTC
        now = datetime(2026, 2, 3, 18, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("09:00-17:00", tz="UTC", now=now)
        assert result is False

    def test_at_start_boundary(self):
        """Test time exactly at the start of the window."""
        # Mock current time to 09:00 UTC
        now = datetime(2026, 2, 3, 9, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("09:00-17:00", tz="UTC", now=now)
        assert result is True

    def test_at_end_boundary(self):
        """Test time exactly at the end of the window."""
        # Mock current time to 17:00 UTC
        now = datetime(2026, 2, 3, 17, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("09:00-17:00", tz="UTC", now=now)
        assert result is False  # End is exclusive


class TestActiveHoursFormatParsing:
    """Test parsing of different active hours formats."""

    def test_short_format_without_minutes(self):
        """Test format like '9-17' without minutes."""
        now = datetime(2026, 2, 3, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("9-17", tz="UTC", now=now)
        assert result is True

    def test_mixed_format(self):
        """Test format like '9:30-17:00' with mixed precision."""
        now = datetime(2026, 2, 3, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("9:30-17:00", tz="UTC", now=now)
        assert result is True

    def test_format_with_spaces(self):
        """Test format with spaces like '09:00 - 17:00'."""
        now = datetime(2026, 2, 3, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("09:00 - 17:00", tz="UTC", now=now)
        assert result is True

    def test_invalid_format_raises_error(self):
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid active_hours format"):
            is_within_active_hours("invalid", tz="UTC")


class TestActiveHoursTimezones:
    """Test timezone-aware checking."""

    def test_different_timezone(self):
        """Test checking with non-UTC timezone."""
        # 12:00 in America/New_York
        now = datetime(2026, 2, 3, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        result = is_within_active_hours("09:00-17:00", tz="America/New_York", now=now)
        assert result is True

    def test_utc_to_local_conversion(self):
        """Test that time is correctly converted to target timezone."""
        # 17:00 UTC = 12:00 EST (during standard time)
        now = datetime(2026, 2, 3, 17, 0, 0, tzinfo=ZoneInfo("UTC"))
        # Should be within 09:00-17:00 EST
        result = is_within_active_hours("09:00-17:00", tz="America/New_York", now=now)
        assert result is True


class TestActiveHoursOvernightWindows:
    """Test handling of overnight windows like 22:00-06:00."""

    def test_overnight_window_late_evening(self):
        """Test overnight window in the late evening portion."""
        # 23:00 UTC should be within 22:00-06:00
        now = datetime(2026, 2, 3, 23, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("22:00-06:00", tz="UTC", now=now)
        assert result is True

    def test_overnight_window_early_morning(self):
        """Test overnight window in the early morning portion."""
        # 03:00 UTC should be within 22:00-06:00
        now = datetime(2026, 2, 3, 3, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("22:00-06:00", tz="UTC", now=now)
        assert result is True

    def test_overnight_window_outside_before(self):
        """Test time before overnight window."""
        # 20:00 UTC should be outside 22:00-06:00
        now = datetime(2026, 2, 3, 20, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("22:00-06:00", tz="UTC", now=now)
        assert result is False

    def test_overnight_window_outside_middle(self):
        """Test time in the middle gap of overnight window."""
        # 12:00 UTC should be outside 22:00-06:00
        now = datetime(2026, 2, 3, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("22:00-06:00", tz="UTC", now=now)
        assert result is False

    def test_overnight_boundary_at_start(self):
        """Test exactly at overnight window start."""
        # 22:00 UTC should be within 22:00-06:00
        now = datetime(2026, 2, 3, 22, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("22:00-06:00", tz="UTC", now=now)
        assert result is True

    def test_overnight_boundary_at_end(self):
        """Test exactly at overnight window end."""
        # 06:00 UTC should be outside 22:00-06:00 (end is exclusive)
        now = datetime(2026, 2, 3, 6, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("22:00-06:00", tz="UTC", now=now)
        assert result is False


class TestActiveHoursEdgeCases:
    """Test edge cases and error handling."""

    def test_24_hour_window(self):
        """Test 24-hour window (should always return True)."""
        now = datetime(2026, 2, 3, 15, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("00:00-23:59", tz="UTC", now=now)
        assert result is True

    def test_invalid_timezone_raises_error(self):
        """Test that invalid timezone raises error."""
        from zoneinfo import ZoneInfoNotFoundError

        with pytest.raises(ZoneInfoNotFoundError):
            is_within_active_hours("09:00-17:00", tz="Invalid/Timezone")

    def test_backwards_range_treated_as_overnight(self):
        """Test that end < start is treated as overnight window."""
        # 23:00 should be within 17:00-09:00 (overnight)
        now = datetime(2026, 2, 3, 23, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = is_within_active_hours("17:00-09:00", tz="UTC", now=now)
        assert result is True
