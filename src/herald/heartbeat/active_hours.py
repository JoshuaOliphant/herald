# ABOUTME: Utility for validating whether the current time falls within configured active hours.
# ABOUTME: Supports timezone-aware checking, multiple time formats, and overnight windows.

import re
from datetime import datetime, time
from zoneinfo import ZoneInfo


def parse_time(time_str: str) -> time:
    """
    Parse a time string into a time object.

    Supports formats:
    - "09:00" (HH:MM)
    - "9" (H)
    - "17" (HH)

    Args:
        time_str: Time string to parse

    Returns:
        time object

    Raises:
        ValueError: If time string is invalid
    """
    time_str = time_str.strip()

    # Try HH:MM format
    if ":" in time_str:
        parts = time_str.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid time format: {time_str}")
        try:
            hour = int(parts[0])
            minute = int(parts[1])
            return time(hour=hour, minute=minute)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid time format: {time_str}") from e

    # Try H or HH format (hour only)
    try:
        hour = int(time_str)
        return time(hour=hour, minute=0)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid time format: {time_str}") from e


def parse_active_hours(active_hours: str) -> tuple[time, time]:
    """
    Parse an active hours string into start and end time objects.

    Supports formats:
    - "09:00-17:00"
    - "9-17"
    - "9:30-17:00"
    - "09:00 - 17:00" (with spaces)

    Args:
        active_hours: Active hours string to parse

    Returns:
        Tuple of (start_time, end_time)

    Raises:
        ValueError: If format is invalid
    """
    # Remove spaces and split on dash
    active_hours = active_hours.strip()

    # Split on dash (with optional spaces)
    match = re.match(r"^(.+?)\s*-\s*(.+?)$", active_hours)
    if not match:
        raise ValueError(f"Invalid active_hours format: {active_hours}")

    start_str, end_str = match.groups()

    try:
        start_time = parse_time(start_str)
        end_time = parse_time(end_str)
        return start_time, end_time
    except ValueError as e:
        raise ValueError(f"Invalid active_hours format: {active_hours}") from e


def is_within_active_hours(
    active_hours: str | None,
    tz: str = "UTC",
    now: datetime | None = None,
) -> bool:
    """
    Check if the current time falls within configured active hours.

    Args:
        active_hours: Active hours string (e.g., "09:00-17:00" or "9-17").
                     If None or empty, always returns True (no restriction).
        tz: Timezone string (e.g., "UTC", "America/New_York").
            The active_hours window is interpreted in this timezone.
        now: Optional datetime to use as current time (for testing).
             If None, uses datetime.now() in the specified timezone.

    Returns:
        True if current time is within active hours, False otherwise.

    Raises:
        ValueError: If active_hours format is invalid
        ZoneInfoNotFoundError: If timezone is invalid

    Examples:
        >>> is_within_active_hours("09:00-17:00", tz="UTC")
        True  # If current time is between 9 AM and 5 PM UTC

        >>> is_within_active_hours("22:00-06:00", tz="UTC")
        True  # If current time is between 10 PM and 6 AM UTC (overnight)

        >>> is_within_active_hours(None)
        True  # No restriction
    """
    # If no active_hours specified, always return True (no restriction)
    if not active_hours or not active_hours.strip():
        return True

    # Parse the active hours
    start_time, end_time = parse_active_hours(active_hours)

    # Get current time in the specified timezone
    zone = ZoneInfo(tz)
    current_time = datetime.now(zone) if now is None else now.astimezone(zone)

    # Extract just the time component
    current_time_only = current_time.time()

    # Handle overnight windows (e.g., 22:00-06:00)
    # If end_time <= start_time, we have an overnight window
    if end_time <= start_time:
        # Overnight: we're active if time >= start OR time < end
        return current_time_only >= start_time or current_time_only < end_time
    else:
        # Normal: we're active if start <= time < end
        return start_time <= current_time_only < end_time
