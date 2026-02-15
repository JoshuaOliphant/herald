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
        result = Settings.parse_user_ids(123456789)
        assert result == [123456789]

    def test_validate_ready_missing_token(self):
        """Validation should fail when token is missing."""
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "",
                "ALLOWED_TELEGRAM_USER_IDS": "123",
            },
            clear=True,
        ):
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


class TestHeraldMemoryPath:
    """Tests for herald_memory_path property."""

    def test_default_memory_path(self, tmp_path):
        """Should default to areas/herald under second_brain_path."""
        settings = Settings(
            telegram_bot_token="test_token",
            allowed_telegram_user_ids=[123],
            second_brain_path=tmp_path,
        )
        assert settings.herald_memory_path == tmp_path / "areas" / "herald"

    def test_custom_memory_path(self, tmp_path):
        """Should use custom memory_path relative to second_brain_path."""
        settings = Settings(
            telegram_bot_token="test_token",
            allowed_telegram_user_ids=[123],
            second_brain_path=tmp_path,
            memory_path=Path("custom/memory"),
        )
        assert settings.herald_memory_path == tmp_path / "custom" / "memory"


class TestChatHistoryPath:
    """Tests for chat_history_path property."""

    def test_chat_history_path_default(self, tmp_path):
        """Should default to areas/herald/chat-history under second_brain_path."""
        settings = Settings(
            telegram_bot_token="test_token",
            allowed_telegram_user_ids=[123],
            second_brain_path=tmp_path,
        )
        assert settings.chat_history_path == tmp_path / "areas" / "herald" / "chat-history"

    def test_chat_history_path_follows_memory_path(self, tmp_path):
        """Should derive from herald_memory_path when MEMORY_PATH is set."""
        settings = Settings(
            telegram_bot_token="test_token",
            allowed_telegram_user_ids=[123],
            second_brain_path=tmp_path,
            memory_path=Path("custom/memory"),
        )
        assert settings.chat_history_path == tmp_path / "custom" / "memory" / "chat-history"

    def test_chat_history_path_explicit_override(self, tmp_path):
        """Should respect CHAT_HISTORY_PATH override."""
        settings = Settings(
            telegram_bot_token="test_token",
            allowed_telegram_user_ids=[123],
            second_brain_path=tmp_path,
            chat_history_path_override=Path("my/custom/history"),
        )
        assert settings.chat_history_path == tmp_path / "my" / "custom" / "history"


class TestModelAndAgentTeamsSettings:
    """Tests for Claude model and agent teams configuration."""

    def test_claude_model_defaults_to_none(self, tmp_path, monkeypatch):
        """Model should default to None (use SDK default)."""
        monkeypatch.chdir(tmp_path)  # Avoid loading .env from project root
        monkeypatch.delenv("CLAUDE_MODEL", raising=False)
        settings = Settings(
            telegram_bot_token="test_token",
            allowed_telegram_user_ids=[123],
            second_brain_path=tmp_path,
        )
        assert settings.claude_model is None

    def test_claude_model_from_constructor(self, tmp_path, monkeypatch):
        """Model should be settable via constructor."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CLAUDE_MODEL", raising=False)
        settings = Settings(
            telegram_bot_token="test_token",
            allowed_telegram_user_ids=[123],
            second_brain_path=tmp_path,
            claude_model="claude-opus-4-6",
        )
        assert settings.claude_model == "claude-opus-4-6"

    def test_agent_teams_defaults_to_false(self, tmp_path, monkeypatch):
        """Agent teams should be disabled by default."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("AGENT_TEAMS", raising=False)
        settings = Settings(
            telegram_bot_token="test_token",
            allowed_telegram_user_ids=[123],
            second_brain_path=tmp_path,
        )
        assert settings.agent_teams is False

    def test_agent_teams_enabled(self, tmp_path, monkeypatch):
        """Agent teams should be settable via constructor."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("AGENT_TEAMS", raising=False)
        settings = Settings(
            telegram_bot_token="test_token",
            allowed_telegram_user_ids=[123],
            second_brain_path=tmp_path,
            agent_teams=True,
        )
        assert settings.agent_teams is True
