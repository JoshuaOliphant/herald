# ABOUTME: Pydantic model for heartbeat configuration settings
# ABOUTME: Validates intervals, active hours, and provides computed properties

from datetime import timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, computed_field, field_validator

from herald.heartbeat.active_hours import parse_active_hours
from herald.heartbeat.interval import parse_interval


class HeartbeatConfig(BaseModel):
    """
    Configuration model for heartbeat settings.

    This model validates and stores heartbeat configuration, using utilities
    from the heartbeat module for interval and active hours parsing.

    Attributes:
        enabled: Whether heartbeat monitoring is enabled (default: False)
        every: Interval duration string (default: "30m")
        prompt: Optional custom heartbeat prompt
        target: Delivery target - "last", channel name, or "none" (default: "last")
        active_hours: Optional time window restriction (e.g., "09:00-17:00")
        ack_max_chars: Max chars for acknowledgment suppression (default: 300)
        model: Optional model override for cost efficiency
    """

    enabled: bool = False
    every: str = "30m"
    prompt: str | None = None
    target: str = "last"
    active_hours: str | None = None
    ack_max_chars: Annotated[int, Field(gt=0)] = 300
    timezone: str = "UTC"
    model: str | None = None

    @field_validator("every")
    @classmethod
    def validate_every(cls, v: str) -> str:
        """
        Validate the 'every' interval string using parse_interval.

        This ensures the interval string is valid and can be parsed
        into a timedelta. The actual parsing happens in the computed
        property, but we validate here to catch errors early.

        Args:
            v: The interval string to validate

        Returns:
            The validated interval string

        Raises:
            ValueError: If the interval string is invalid
        """
        try:
            # Parse to validate - we'll do this again in the property
            parse_interval(v)
            return v
        except ValueError as e:
            raise ValueError(f"Invalid interval format: {e}") from e

    @field_validator("active_hours")
    @classmethod
    def validate_active_hours(cls, v: str | None) -> str | None:
        """
        Validate the 'active_hours' string format.

        This ensures the active hours string follows the expected format
        (e.g., "09:00-17:00") and can be parsed. Empty strings are treated
        as None (no restriction).

        Args:
            v: The active hours string to validate

        Returns:
            The validated active hours string, or None

        Raises:
            ValueError: If the active hours format is invalid
        """
        # None or empty string means no restriction
        if not v or not v.strip():
            return None

        try:
            # Validate by parsing
            parse_active_hours(v)
            return v
        except ValueError as e:
            raise ValueError(f"Invalid active_hours format: {e}") from e

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate the timezone string is a known IANA timezone."""
        try:
            ZoneInfo(v)
            return v
        except (KeyError, ValueError) as e:
            raise ValueError(f"Invalid timezone: {v}") from e

    @computed_field  # type: ignore[prop-decorator]
    @property
    def interval(self) -> timedelta:
        """
        Computed property that returns the parsed interval as a timedelta.

        This property uses parse_interval to convert the 'every' string
        into a timedelta object for easy time calculations.

        Returns:
            timedelta object representing the interval
        """
        return parse_interval(self.every)
