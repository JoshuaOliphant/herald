"""Tests for chat history integration with webhook handler."""

import shutil
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from herald.config import Settings
from herald.executor import ExecutionResult
from herald.webhook import TelegramUpdate, WebhookHandler


@pytest.fixture
def temp_history_dir(tmp_path):
    """Create a temporary directory for chat history."""
    history_dir = tmp_path / "areas" / "herald" / "chat-history"
    history_dir.mkdir(parents=True)
    yield history_dir
    if history_dir.exists():
        shutil.rmtree(history_dir.parent.parent.parent)


@pytest.fixture
def temp_second_brain(tmp_path):
    """Create a temporary second brain directory."""
    second_brain = tmp_path / "second-brain"
    second_brain.mkdir()
    return second_brain


@pytest.fixture
def mock_settings(temp_second_brain):
    """Create mock settings with chat history path."""
    settings = Mock(spec=Settings)
    settings.telegram_bot_token = "test-token"
    settings.allowed_telegram_user_ids = [12345]
    settings.second_brain_path = temp_second_brain
    settings.chat_history_path = temp_second_brain / "areas" / "herald" / "chat-history"
    return settings


@pytest.fixture
def mock_executor():
    """Create a mock executor."""
    executor = AsyncMock()
    executor.execute.return_value = ExecutionResult(
        success=True,
        output="Hello! How can I help you?",
    )
    executor.shutdown = AsyncMock()
    return executor


@pytest.fixture
async def webhook_handler(mock_settings, mock_executor):
    """Create a webhook handler with chat history enabled."""
    handler = WebhookHandler(
        settings=mock_settings,
        executor=mock_executor,
    )
    await handler.start()
    yield handler
    await handler.stop()


class TestWebhookChatHistoryIntegration:
    """Test that webhook handler logs conversations to chat history."""

    @pytest.mark.asyncio
    async def test_user_message_logged_to_history(
        self, webhook_handler, mock_settings, temp_second_brain
    ):
        """Test that incoming user messages are logged."""
        chat_id = 12345
        user_text = "Hello, Claude!"

        update = TelegramUpdate(
            update_id=1,
            message={
                "from": {"id": chat_id, "first_name": "Test User"},
                "chat": {"id": chat_id},
                "text": user_text,
            },
        )

        await webhook_handler.handle_update(update)

        # Check that history was saved
        today = datetime.now().strftime("%Y-%m-%d")
        history_file = mock_settings.chat_history_path / str(chat_id) / f"{today}.md"
        assert history_file.exists()

        content = history_file.read_text()
        assert "User" in content
        assert user_text in content

    @pytest.mark.asyncio
    async def test_assistant_response_logged_to_history(
        self, webhook_handler, mock_settings, mock_executor
    ):
        """Test that assistant responses are logged."""
        chat_id = 12345
        user_text = "What's the weather?"
        assistant_response = "I don't have real-time weather data."

        # Set up executor to return specific response
        mock_executor.execute.return_value = ExecutionResult(
            success=True,
            output=assistant_response,
        )

        update = TelegramUpdate(
            update_id=2,
            message={
                "from": {"id": chat_id, "first_name": "Test User"},
                "chat": {"id": chat_id},
                "text": user_text,
            },
        )

        await webhook_handler.handle_update(update)

        # Check that both user and assistant messages are logged
        today = datetime.now().strftime("%Y-%m-%d")
        history_file = mock_settings.chat_history_path / str(chat_id) / f"{today}.md"
        content = history_file.read_text()

        # User message
        assert user_text in content
        # Assistant response
        assert assistant_response in content

    @pytest.mark.asyncio
    async def test_conversation_thread_preserved(
        self, webhook_handler, mock_settings, mock_executor
    ):
        """Test that multi-turn conversations are preserved in order."""
        chat_id = 12345

        # Turn 1
        update1 = TelegramUpdate(
            update_id=1,
            message={
                "from": {"id": chat_id, "first_name": "Test User"},
                "chat": {"id": chat_id},
                "text": "First question",
            },
        )
        mock_executor.execute.return_value = ExecutionResult(success=True, output="First response")
        await webhook_handler.handle_update(update1)

        # Turn 2
        update2 = TelegramUpdate(
            update_id=2,
            message={
                "from": {"id": chat_id, "first_name": "Test User"},
                "chat": {"id": chat_id},
                "text": "Second question",
            },
        )
        mock_executor.execute.return_value = ExecutionResult(success=True, output="Second response")
        await webhook_handler.handle_update(update2)

        # Check history file
        today = datetime.now().strftime("%Y-%m-%d")
        history_file = mock_settings.chat_history_path / str(chat_id) / f"{today}.md"
        content = history_file.read_text()

        # All turns should be present
        assert "First question" in content
        assert "First response" in content
        assert "Second question" in content
        assert "Second response" in content

        # Order should be preserved (first before second)
        assert content.index("First question") < content.index("Second question")

    @pytest.mark.asyncio
    async def test_reset_command_logged(self, webhook_handler, mock_settings):
        """Test that /reset commands are logged to history."""
        chat_id = 12345

        update = TelegramUpdate(
            update_id=1,
            message={
                "from": {"id": chat_id, "first_name": "Test User"},
                "chat": {"id": chat_id},
                "text": "/reset",
            },
        )

        await webhook_handler.handle_update(update)

        # Check that the reset command was logged
        today = datetime.now().strftime("%Y-%m-%d")
        history_file = mock_settings.chat_history_path / str(chat_id) / f"{today}.md"
        content = history_file.read_text()

        assert "/reset" in content
        assert "System" in content  # Reset should be logged as system message

    @pytest.mark.asyncio
    async def test_error_responses_logged(self, webhook_handler, mock_settings, mock_executor):
        """Test that error responses are logged to history."""
        chat_id = 12345

        # Set up executor to return an error
        mock_executor.execute.return_value = ExecutionResult(
            success=False,
            output="",
            error="Something went wrong",
        )

        update = TelegramUpdate(
            update_id=1,
            message={
                "from": {"id": chat_id, "first_name": "Test User"},
                "chat": {"id": chat_id},
                "text": "This will error",
            },
        )

        await webhook_handler.handle_update(update)

        # Check that the error was logged
        today = datetime.now().strftime("%Y-%m-%d")
        history_file = mock_settings.chat_history_path / str(chat_id) / f"{today}.md"
        content = history_file.read_text()

        assert "This will error" in content
        # Error should be logged
        assert "error" in content.lower() or "Error" in content
