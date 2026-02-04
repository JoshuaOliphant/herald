# ABOUTME: Tests for Herald webhook handler
# ABOUTME: Validates user authorization, message routing, and /reset command

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from herald.config import Settings
from herald.executor import ClaudeExecutor, ExecutionResult
from herald.webhook import TelegramUpdate, WebhookHandler


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    return Settings(
        telegram_bot_token="test_token_123",
        allowed_telegram_user_ids=[12345, 67890],
        second_brain_path=Path("/tmp"),
    )


@pytest.fixture
def mock_executor():
    """Create mock executor for testing."""
    executor = MagicMock(spec=ClaudeExecutor)
    executor.execute = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            output="Test response",
        )
    )
    executor.reset_chat = AsyncMock()
    executor.shutdown = AsyncMock()
    return executor


class TestWebhookHandler:
    """Tests for WebhookHandler class."""

    def test_is_user_allowed_valid(self, mock_settings, mock_executor):
        """Allowed users should be authorized."""
        handler = WebhookHandler(mock_settings, mock_executor)
        assert handler._is_user_allowed(12345) is True
        assert handler._is_user_allowed(67890) is True

    def test_is_user_allowed_invalid(self, mock_settings, mock_executor):
        """Unknown users should be rejected."""
        handler = WebhookHandler(mock_settings, mock_executor)
        assert handler._is_user_allowed(99999) is False
        assert handler._is_user_allowed(None) is False

    def test_is_user_allowed_empty_whitelist(self, mock_executor):
        """Empty whitelist should reject all users (fail secure)."""
        settings = Settings(
            telegram_bot_token="test_token",
            allowed_telegram_user_ids=[],
            second_brain_path=Path("/tmp"),
        )
        handler = WebhookHandler(settings, mock_executor)
        assert handler._is_user_allowed(12345) is False


class TestTelegramUpdate:
    """Tests for TelegramUpdate parsing."""

    def test_parse_message(self):
        """Should parse standard message update."""
        data = {
            "update_id": 123,
            "message": {
                "message_id": 1,
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "Hello bot",
            },
        }
        update = TelegramUpdate(**data)
        assert update.update_id == 123
        assert update.message is not None
        assert update.message["text"] == "Hello bot"

    def test_parse_edited_message(self):
        """Should parse edited message update."""
        data = {
            "update_id": 124,
            "edited_message": {
                "message_id": 1,
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "Edited message",
            },
        }
        update = TelegramUpdate(**data)
        assert update.update_id == 124
        assert update.edited_message is not None
        assert update.message is None

    def test_parse_update_no_message(self):
        """Should handle updates without messages (e.g., callbacks)."""
        data = {"update_id": 125}
        update = TelegramUpdate(**data)
        assert update.update_id == 125
        assert update.message is None
        assert update.edited_message is None


@pytest.mark.asyncio
class TestWebhookHandlerAsync:
    """Async tests for WebhookHandler."""

    async def test_handle_update_unauthorized(self, mock_settings, mock_executor):
        """Unauthorized users should receive rejection message."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        update = TelegramUpdate(
            update_id=1,
            message={
                "from": {"id": 99999, "username": "hacker"},
                "chat": {"id": 99999},
                "text": "I want in",
            },
        )

        await handler.handle_update(update)

        # Should send unauthorized message, not execute claude
        mock_executor.execute.assert_not_called()
        handler._http_client.post.assert_called()
        call_args = handler._http_client.post.call_args
        assert "Unauthorized" in str(call_args)

    async def test_handle_update_no_text(self, mock_settings, mock_executor):
        """Messages without text should be ignored."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()

        update = TelegramUpdate(
            update_id=1,
            message={
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                # No text field
            },
        )

        await handler.handle_update(update)

        # Should not execute or send any message
        mock_executor.execute.assert_not_called()

    async def test_handle_update_success(self, mock_settings, mock_executor):
        """Valid messages should be processed through Claude Code."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        update = TelegramUpdate(
            update_id=1,
            message={
                "from": {"id": 12345, "username": "laboeuf"},
                "chat": {"id": 12345},
                "text": "What's on my todo list?",
            },
        )

        await handler.handle_update(update)

        # Should execute the prompt with chat_id
        mock_executor.execute.assert_called_once_with("What's on my todo list?", 12345)
        # Should send the response
        assert handler._http_client.post.call_count >= 1

    async def test_handle_reset_command(self, mock_settings, mock_executor):
        """The /reset command should clear conversation history."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        update = TelegramUpdate(
            update_id=1,
            message={
                "from": {"id": 12345, "username": "laboeuf"},
                "chat": {"id": 12345},
                "text": "/reset",
            },
        )

        await handler.handle_update(update)

        # Should call reset_chat, not execute
        mock_executor.reset_chat.assert_called_once_with(12345)
        mock_executor.execute.assert_not_called()
        # Should send confirmation message
        handler._http_client.post.assert_called()
        call_args = handler._http_client.post.call_args
        assert "reset" in str(call_args).lower()

    async def test_handle_reset_command_case_insensitive(self, mock_settings, mock_executor):
        """The /reset command should be case insensitive."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        update = TelegramUpdate(
            update_id=1,
            message={
                "from": {"id": 12345, "username": "laboeuf"},
                "chat": {"id": 12345},
                "text": "/RESET",
            },
        )

        await handler.handle_update(update)

        mock_executor.reset_chat.assert_called_once_with(12345)
        mock_executor.execute.assert_not_called()

    async def test_stop_calls_executor_shutdown(self, mock_settings, mock_executor):
        """Stopping the handler should shutdown the executor."""
        handler = WebhookHandler(mock_settings, mock_executor)
        mock_http_client = AsyncMock()
        mock_http_client.aclose = AsyncMock()
        handler._http_client = mock_http_client

        await handler.stop()

        mock_executor.shutdown.assert_called_once()
        mock_http_client.aclose.assert_called_once()

    async def test_deduplication_prevents_double_processing(self, mock_settings, mock_executor):
        """Same update ID should only be processed once."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        update = TelegramUpdate(
            update_id=1,
            message={
                "from": {"id": 12345, "username": "laboeuf"},
                "chat": {"id": 12345},
                "text": "Hello",
            },
        )

        # Process same update twice
        await handler.handle_update(update)
        await handler.handle_update(update)

        # Should only execute once
        mock_executor.execute.assert_called_once()
