# ABOUTME: Tests for Herald configuration module
# ABOUTME: Validates settings parsing and validation logic

import os
from pathlib import Path
from unittest.mock import patch

from herald.config import Settings


class TestSettings:
    """Tests for Settings configuration class."""

    def test_parse_user_ids_from_string(self):
        """User IDs should be parsed from comma-separated string."""
        result = Settings.parse_user_ids("123,456,789")
        assert result == [123, 456, 789]

    def test_parse_user_ids_with_spaces(self):
        """User IDs parsing should handle whitespace."""
        result = Settings.parse_user_ids("123, 456 , 789")
        assert result == [123, 456, 789]

    def test_parse_user_ids_empty_string(self):
        """Empty string should return empty list."""
        result = Settings.parse_user_ids("")
        assert result == []

    def test_parse_user_ids_already_list(self):
        """List input should pass through unchanged."""
        result = Settings.parse_user_ids([123, 456])
        assert result == [123, 456]

    def test_parse_user_ids_single_int(self):
        """Single int should be wrapped in a list."""
        result = Settings.parse_user_ids(6360227946)
        assert result == [6360227946]

    def test_validate_ready_missing_token(self):
        """Validation should fail when token is missing."""
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "",
            "ALLOWED_TELEGRAM_USER_IDS": "123",
        }, clear=True):
            settings = Settings(
                telegram_bot_token="",
                allowed_telegram_user_ids=[123],
                second_brain_path=Path("/tmp"),
            )
            errors = settings.validate_ready()
            assert any("TELEGRAM_BOT_TOKEN" in e for e in errors)

    def test_validate_ready_missing_user_ids(self):
        """Validation should fail when no user IDs configured."""
        settings = Settings(
            telegram_bot_token="test_token",
            allowed_telegram_user_ids=[],
            second_brain_path=Path("/tmp"),
        )
        errors = settings.validate_ready()
        assert any("ALLOWED_TELEGRAM_USER_IDS" in e for e in errors)

    def test_validate_ready_invalid_second_brain_path(self):
        """Validation should fail when second_brain_path doesn't exist."""
        settings = Settings(
            telegram_bot_token="test_token",
            allowed_telegram_user_ids=[123],
            second_brain_path=Path("/nonexistent/path"),
        )
        errors = settings.validate_ready()
        assert any("SECOND_BRAIN_PATH" in e for e in errors)

    def test_validate_ready_success(self, tmp_path):
        """Validation should pass with valid configuration."""
        settings = Settings(
            telegram_bot_token="test_token",
            allowed_telegram_user_ids=[123],
            second_brain_path=tmp_path,
        )
        errors = settings.validate_ready()
        assert errors == []
