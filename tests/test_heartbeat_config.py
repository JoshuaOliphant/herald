# ABOUTME: Unit tests for HeartbeatConfig Pydantic model
# ABOUTME: Tests validation, default values, and computed properties

from datetime import timedelta

import pytest
from pydantic import ValidationError

from herald.heartbeat.config import HeartbeatConfig


class TestHeartbeatConfigDefaults:
    """Test default values and basic initialization."""

    def test_default_initialization(self):
        """Test that HeartbeatConfig initializes with sensible defaults."""
        config = HeartbeatConfig()

        assert config.enabled is False
        assert config.every == "30m"
        assert config.prompt is None
        assert config.target == "last"
        assert config.active_hours is None
        assert config.ack_max_chars == 300
        assert config.model is None

    def test_interval_property_default(self):
        """Test that interval property returns parsed timedelta."""
        config = HeartbeatConfig()

        assert config.interval == timedelta(minutes=30)

    def test_custom_values(self):
        """Test initialization with custom values."""
        config = HeartbeatConfig(
            enabled=True,
            every="1h",
            prompt="Custom heartbeat prompt",
            target="general",
            active_hours="09:00-17:00",
            ack_max_chars=500,
            model="claude-haiku-4",
        )

        assert config.enabled is True
        assert config.every == "1h"
        assert config.prompt == "Custom heartbeat prompt"
        assert config.target == "general"
        assert config.active_hours == "09:00-17:00"
        assert config.ack_max_chars == 500
        assert config.model == "claude-haiku-4"


class TestIntervalValidation:
    """Test validation of the 'every' field using parse_interval."""

    def test_valid_interval_formats(self):
        """Test that various valid interval formats are accepted."""
        valid_intervals = [
            ("30m", timedelta(minutes=30)),
            ("1h", timedelta(hours=1)),
            ("2h30m", timedelta(hours=2, minutes=30)),
            ("1d", timedelta(days=1)),
            ("1d12h", timedelta(days=1, hours=12)),
        ]

        for interval_str, expected_delta in valid_intervals:
            config = HeartbeatConfig(every=interval_str)
            assert config.interval == expected_delta

    def test_invalid_interval_raises_validation_error(self):
        """Test that invalid interval formats raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HeartbeatConfig(every="invalid")

        assert "every" in str(exc_info.value)

    def test_negative_interval_raises_validation_error(self):
        """Test that negative intervals are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            HeartbeatConfig(every="-30m")

        assert "every" in str(exc_info.value)

    def test_zero_interval_raises_validation_error(self):
        """Test that zero intervals are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            HeartbeatConfig(every="0m")

        assert "every" in str(exc_info.value)


class TestActiveHoursValidation:
    """Test validation of the 'active_hours' field."""

    def test_valid_active_hours_formats(self):
        """Test that various valid active_hours formats are accepted."""
        valid_formats = [
            "09:00-17:00",
            "9-17",
            "9:30-17:00",
            "22:00-06:00",  # Overnight
            "09:00 - 17:00",  # With spaces
        ]

        for hours_str in valid_formats:
            config = HeartbeatConfig(active_hours=hours_str)
            assert config.active_hours == hours_str

    def test_invalid_active_hours_raises_validation_error(self):
        """Test that invalid active_hours formats raise ValidationError."""
        invalid_formats = [
            "25:00-17:00",  # Invalid hour
            "09:00",  # Missing dash
            "abc-def",  # Non-numeric
            "17:00-09:00-12:00",  # Multiple dashes
        ]

        for hours_str in invalid_formats:
            with pytest.raises(ValidationError) as exc_info:
                HeartbeatConfig(active_hours=hours_str)

            assert "active_hours" in str(exc_info.value)

    def test_none_active_hours_is_valid(self):
        """Test that None is a valid value for active_hours."""
        config = HeartbeatConfig(active_hours=None)
        assert config.active_hours is None

    def test_empty_active_hours_is_valid(self):
        """Test that empty string is treated as None."""
        config = HeartbeatConfig(active_hours="")
        # Empty strings might be normalized to None by validator
        assert config.active_hours in (None, "")


class TestAckMaxCharsValidation:
    """Test validation of the 'ack_max_chars' field."""

    def test_positive_ack_max_chars(self):
        """Test that positive values are accepted."""
        config = HeartbeatConfig(ack_max_chars=100)
        assert config.ack_max_chars == 100

    def test_zero_ack_max_chars_raises_validation_error(self):
        """Test that zero is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            HeartbeatConfig(ack_max_chars=0)

        assert "ack_max_chars" in str(exc_info.value)

    def test_negative_ack_max_chars_raises_validation_error(self):
        """Test that negative values are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            HeartbeatConfig(ack_max_chars=-1)

        assert "ack_max_chars" in str(exc_info.value)


class TestTargetField:
    """Test the 'target' field."""

    def test_default_target(self):
        """Test default target is 'last'."""
        config = HeartbeatConfig()
        assert config.target == "last"

    def test_custom_targets(self):
        """Test that any string value is accepted for target."""
        targets = ["last", "general", "dev-team", "none", "#random-channel"]

        for target in targets:
            config = HeartbeatConfig(target=target)
            assert config.target == target


class TestModelField:
    """Test the 'model' field."""

    def test_default_model(self):
        """Test default model is None."""
        config = HeartbeatConfig()
        assert config.model is None

    def test_custom_model(self):
        """Test that model names are accepted."""
        models = ["claude-haiku-4", "claude-sonnet-4", "claude-opus-4"]

        for model_name in models:
            config = HeartbeatConfig(model=model_name)
            assert config.model == model_name


class TestDictSerialization:
    """Test model serialization and deserialization."""

    def test_model_dump(self):
        """Test that model can be dumped to dict."""
        config = HeartbeatConfig(
            enabled=True,
            every="1h",
            prompt="Test",
            target="general",
            active_hours="09:00-17:00",
            ack_max_chars=500,
            model="claude-haiku-4",
        )

        data = config.model_dump()

        assert data["enabled"] is True
        assert data["every"] == "1h"
        assert data["prompt"] == "Test"
        assert data["target"] == "general"
        assert data["active_hours"] == "09:00-17:00"
        assert data["ack_max_chars"] == 500
        assert data["model"] == "claude-haiku-4"

    def test_model_validate(self):
        """Test that model can be created from dict."""
        data = {
            "enabled": True,
            "every": "2h",
            "prompt": "Check in",
            "target": "dev",
            "active_hours": "10:00-18:00",
            "ack_max_chars": 400,
            "model": "claude-sonnet-4",
        }

        config = HeartbeatConfig.model_validate(data)

        assert config.enabled is True
        assert config.every == "2h"
        assert config.interval == timedelta(hours=2)
        assert config.prompt == "Check in"
        assert config.target == "dev"
        assert config.active_hours == "10:00-18:00"
        assert config.ack_max_chars == 400
        assert config.model == "claude-sonnet-4"
