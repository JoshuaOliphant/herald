# ABOUTME: Interval parsing utility for duration strings
# ABOUTME: Converts duration strings (e.g., "30m", "1h", "2h30m") to timedelta objects

import re
from datetime import timedelta


def parse_interval(duration: str | None) -> timedelta:
    """
    Parse a duration string into a timedelta object.

    Supports formats like:
    - "30m" (30 minutes)
    - "1h" (1 hour)
    - "2h30m" (2 hours 30 minutes)
    - "1d12h30m45s" (1 day, 12 hours, 30 minutes, 45 seconds)

    Units supported: d (days), h (hours), m (minutes), s (seconds)

    Args:
        duration: Duration string to parse, or None/empty for default

    Returns:
        timedelta object representing the parsed duration

    Raises:
        ValueError: If the duration format is invalid or contains invalid values

    Examples:
        >>> parse_interval("30m")
        timedelta(minutes=30)
        >>> parse_interval("2h30m")
        timedelta(hours=2, minutes=30)
        >>> parse_interval("")
        timedelta(minutes=30)
    """
    # Default to 30 minutes if no value provided
    if not duration or not duration.strip():
        return timedelta(minutes=30)

    duration = duration.strip()

    # Check for negative values before processing
    if "-" in duration:
        raise ValueError("Duration values must be positive")

    # Define unit mappings (case-insensitive)
    units = {
        "d": "days",
        "h": "hours",
        "m": "minutes",
        "s": "seconds",
    }

    # Pattern to match number + unit combinations
    # Supports integers and floats, with optional spaces
    pattern = r"(\d+(?:\.\d+)?)\s*([dhms])"

    matches = re.findall(pattern, duration.lower())

    if not matches:
        raise ValueError(
            f"Invalid duration format: '{duration}'. "
            "Expected format like '30m', '1h', '2h30m', etc."
        )

    # Build kwargs for timedelta
    kwargs: dict[str, float] = {}
    for value_str, unit in matches:
        value = float(value_str)

        # Validate positive values
        if value <= 0:
            raise ValueError(f"Duration values must be positive. Got: {value_str}{unit}")

        # Map unit to timedelta parameter
        timedelta_param = units[unit]

        # Accumulate values (in case same unit appears multiple times)
        if timedelta_param in kwargs:
            kwargs[timedelta_param] += value
        else:
            kwargs[timedelta_param] = value

    return timedelta(**kwargs)
