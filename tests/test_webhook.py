# ABOUTME: Tests for Herald webhook handler
# ABOUTME: Validates user authorization, message routing, and /reset command

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from herald.config import Settings
from herald.executor import ClaudeExecutor, ExecutionResult
from herald.heartbeat.delivery import HeartbeatDelivery
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
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "What's on my todo list?",
            },
        )

        await handler.handle_update(update)

        # Should execute the prompt with chat_id (plus streaming callback)
        mock_executor.execute.assert_called_once()
        call_args = mock_executor.execute.call_args
        # Prompt is prefixed with current date/time in XML tag
        prompt = call_args.args[0]
        assert "<current-time>" in prompt
        assert "What's on my todo list?" in prompt
        assert call_args.args[1] == 12345
        assert "on_assistant_text" in call_args.kwargs
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
                "from": {"id": 12345, "username": "testuser"},
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
                "from": {"id": 12345, "username": "testuser"},
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

    async def test_handle_update_streams_intermediate_text(self, mock_settings, mock_executor):
        """Substantive intermediate text should be sent to Telegram as it arrives."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        # Make executor.execute call the on_assistant_text callback
        async def fake_execute(prompt, chat_id, on_assistant_text=None):
            if on_assistant_text:
                await on_assistant_text("Here are the detailed proposals " + "x" * 200)
            return ExecutionResult(success=True, output="Final summary")

        mock_executor.execute = AsyncMock(side_effect=fake_execute)

        update = TelegramUpdate(
            update_id=1,
            message={
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "Do the tasks",
            },
        )

        await handler.handle_update(update)

        # Should have sent the intermediate text to Telegram
        send_calls = handler._http_client.post.call_args_list
        message_calls = [c for c in send_calls if "sendMessage" in str(c)]
        assert any("proposals" in str(c) for c in message_calls)

    async def test_handle_update_skips_final_when_streamed(self, mock_settings, mock_executor):
        """When text was streamed via callback, should NOT re-send final output."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        async def fake_execute(prompt, chat_id, on_assistant_text=None):
            if on_assistant_text:
                await on_assistant_text("Detailed analysis " + "x" * 200)
            return ExecutionResult(success=True, output="Same content repeated")

        mock_executor.execute = AsyncMock(side_effect=fake_execute)

        update = TelegramUpdate(
            update_id=1,
            message={
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "Analyze",
            },
        )

        await handler.handle_update(update)

        # Filter for sendMessage calls only
        send_calls = handler._http_client.post.call_args_list
        message_calls = [c for c in send_calls if "sendMessage" in str(c)]

        # Should have the intermediate message but NOT "Same content repeated"
        assert any("analysis" in str(c).lower() for c in message_calls)
        assert not any("same content repeated" in str(c).lower() for c in message_calls)

    async def test_handle_update_sends_final_when_not_streamed(self, mock_settings, mock_executor):
        """When nothing was streamed, should send final output normally."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        # No callback invocation (simple/short response)
        async def fake_execute(prompt, chat_id, on_assistant_text=None):
            return ExecutionResult(success=True, output="Quick answer")

        mock_executor.execute = AsyncMock(side_effect=fake_execute)

        update = TelegramUpdate(
            update_id=2,
            message={
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "Quick question",
            },
        )

        await handler.handle_update(update)

        send_calls = handler._http_client.post.call_args_list
        message_calls = [c for c in send_calls if "sendMessage" in str(c)]
        assert any("quick answer" in str(c).lower() for c in message_calls)

    async def test_handle_update_logs_streamed_to_history(
        self, mock_settings, mock_executor,
    ):
        """Chat history should capture all streamed content, not just final output."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        chunk1 = "First proposal details " + "x" * 200
        chunk2 = "Second analysis results " + "y" * 200

        async def fake_execute(prompt, chat_id, on_assistant_text=None):
            if on_assistant_text:
                await on_assistant_text(chunk1)
                await on_assistant_text(chunk2)
            return ExecutionResult(success=True, output="Summary only")

        mock_executor.execute = AsyncMock(side_effect=fake_execute)

        # Mock chat history
        handler._chat_history = MagicMock()
        handler._chat_history.save_message = MagicMock()

        update = TelegramUpdate(
            update_id=3,
            message={
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "Review everything",
            },
        )

        await handler.handle_update(update)

        # Find the assistant save_message call
        assistant_calls = [
            c for c in handler._chat_history.save_message.call_args_list
            if c.kwargs.get("sender") == "assistant"
            or (c.args and len(c.args) > 1 and c.args[1] == "assistant")
        ]

        # Chat history should contain the streamed content, not just "Summary only"
        all_saved = str(assistant_calls)
        assert "First proposal details" in all_saved
        assert "Second analysis results" in all_saved

    async def test_deduplication_prevents_double_processing(self, mock_settings, mock_executor):
        """Same update ID should only be processed once."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        update = TelegramUpdate(
            update_id=1,
            message={
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "Hello",
            },
        )

        # Process same update twice
        await handler.handle_update(update)
        await handler.handle_update(update)

        # Should only execute once
        mock_executor.execute.assert_called_once()

    async def test_typing_indicator_sent_continuously(self, mock_settings, mock_executor):
        """Should send typing indicators repeatedly while executor runs."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler.TYPING_INTERVAL = 0.05  # Speed up for testing
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        # Make executor.execute take long enough for multiple typing indicators
        async def slow_execute(prompt, chat_id, on_assistant_text=None):
            await asyncio.sleep(0.2)  # Long enough for multiple 0.05s typing intervals
            return ExecutionResult(success=True, output="Done")

        mock_executor.execute = AsyncMock(side_effect=slow_execute)

        update = TelegramUpdate(
            update_id=10,
            message={
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "Do research",
            },
        )

        await handler.handle_update(update)

        # Count typing action calls (sendChatAction URL pattern)
        typing_calls = [
            c for c in handler._http_client.post.call_args_list
            if "sendChatAction" in str(c)
        ]
        # Should have sent multiple typing indicators (not just one)
        assert len(typing_calls) >= 2, (
            f"Expected multiple typing calls, got {len(typing_calls)}"
        )

    async def test_typing_indicator_stops_after_execution(self, mock_settings, mock_executor):
        """Typing loop should be cancelled after executor completes."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        async def fast_execute(prompt, chat_id, on_assistant_text=None):
            return ExecutionResult(success=True, output="Quick")

        mock_executor.execute = AsyncMock(side_effect=fast_execute)

        update = TelegramUpdate(
            update_id=11,
            message={
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "Quick question",
            },
        )

        await handler.handle_update(update)

        # Record typing calls at this point
        typing_before = len([
            c for c in handler._http_client.post.call_args_list
            if "sendChatAction" in str(c)
        ])

        # Wait a bit — no new typing calls should appear
        await asyncio.sleep(0.1)

        typing_after = len([
            c for c in handler._http_client.post.call_args_list
            if "sendChatAction" in str(c)
        ])

        # No new typing calls after execution completed
        assert typing_after == typing_before

    async def test_timeout_error_sent_to_user(self, mock_settings, mock_executor):
        """When executor returns timed_out failure, error message should be sent."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        mock_executor.execute = AsyncMock(
            return_value=ExecutionResult(
                success=False,
                output="",
                error="Timed out after 600s waiting for Claude to respond",
            )
        )

        update = TelegramUpdate(
            update_id=12,
            message={
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "Heavy research task",
            },
        )

        await handler.handle_update(update)

        # Should send the error message to the user
        send_calls = handler._http_client.post.call_args_list
        message_calls = [c for c in send_calls if "sendMessage" in str(c)]
        assert any("timed out" in str(c).lower() for c in message_calls)


@pytest.mark.asyncio
class TestHeartbeatContextInjection:
    """Tests for heartbeat context injection into user prompts."""

    async def test_heartbeat_context_injected_into_prompt(
        self, mock_settings, mock_executor,
    ):
        """When heartbeat content exists, prompt should include <recent-heartbeat> tag."""
        mock_send = AsyncMock()
        heartbeat_delivery = HeartbeatDelivery(send_message=mock_send)
        heartbeat_delivery._last_delivered_content = "You have 3 overdue tasks"

        handler = WebhookHandler(
            mock_settings, mock_executor, heartbeat_delivery=heartbeat_delivery,
        )
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        update = TelegramUpdate(
            update_id=100,
            message={
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "What tasks are overdue?",
            },
        )

        await handler.handle_update(update)

        prompt = mock_executor.execute.call_args.args[0]
        assert "<recent-heartbeat>" in prompt
        assert "You have 3 overdue tasks" in prompt
        assert "</recent-heartbeat>" in prompt

    async def test_heartbeat_context_consumed_after_use(
        self, mock_settings, mock_executor,
    ):
        """Second message should NOT include heartbeat context (consumed after first)."""
        mock_send = AsyncMock()
        heartbeat_delivery = HeartbeatDelivery(send_message=mock_send)
        heartbeat_delivery._last_delivered_content = "Alert: check logs"

        handler = WebhookHandler(
            mock_settings, mock_executor, heartbeat_delivery=heartbeat_delivery,
        )
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        # First message — should consume heartbeat context
        update1 = TelegramUpdate(
            update_id=101,
            message={
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "What happened?",
            },
        )
        await handler.handle_update(update1)

        # Second message — heartbeat context should be gone
        update2 = TelegramUpdate(
            update_id=102,
            message={
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "Tell me more",
            },
        )
        await handler.handle_update(update2)

        second_prompt = mock_executor.execute.call_args_list[1].args[0]
        assert "<recent-heartbeat>" not in second_prompt

    async def test_no_heartbeat_context_when_none_delivered(
        self, mock_settings, mock_executor,
    ):
        """Prompt should not include heartbeat tag when nothing was delivered."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        update = TelegramUpdate(
            update_id=103,
            message={
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "Hello",
            },
        )

        await handler.handle_update(update)

        prompt = mock_executor.execute.call_args.args[0]
        assert "<recent-heartbeat>" not in prompt

    async def test_current_time_uses_xml_tag(self, mock_settings, mock_executor):
        """Prompt should use <current-time> XML tag instead of bracket notation."""
        handler = WebhookHandler(mock_settings, mock_executor)
        handler._http_client = AsyncMock()
        handler._http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        update = TelegramUpdate(
            update_id=104,
            message={
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 12345},
                "text": "What time is it?",
            },
        )

        await handler.handle_update(update)

        prompt = mock_executor.execute.call_args.args[0]
        assert "<current-time>" in prompt
        assert "</current-time>" in prompt
        assert "[Current time:" not in prompt
