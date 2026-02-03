# ABOUTME: Tests for Herald Claude Code executor using Agent SDK
# ABOUTME: Validates SDK client management and conversation continuity

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from herald.executor import ClaudeExecutor, ExecutionResult, create_executor


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_successful_result(self):
        """Successful result should have success=True and output."""
        result = ExecutionResult(success=True, output="Hello world")
        assert result.success is True
        assert result.output == "Hello world"
        assert result.error is None

    def test_failed_result(self):
        """Failed result should have success=False and error."""
        result = ExecutionResult(success=False, output="", error="Something broke")
        assert result.success is False
        assert result.output == ""
        assert result.error == "Something broke"


class TestClaudeExecutor:
    """Tests for ClaudeExecutor class with SDK mocking."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create an executor with a valid working directory."""
        return ClaudeExecutor(working_dir=tmp_path)

    @pytest.fixture
    def mock_text_block(self):
        """Create a mock TextBlock."""
        block = MagicMock()
        block.text = "Hello from Claude"
        return block

    @pytest.fixture
    def mock_assistant_message(self, mock_text_block):
        """Create a mock AssistantMessage."""
        msg = MagicMock()
        msg.content = [mock_text_block]
        return msg

    @pytest.fixture
    def mock_result_message(self):
        """Create a mock ResultMessage."""
        msg = MagicMock()
        msg.result = "Final answer"
        return msg

    @pytest.mark.asyncio
    async def test_execute_creates_client_for_new_chat(self, executor):
        """Should create a new client for a chat that doesn't have one."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            # Setup mock client
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            # Mock receive_response to return a result message
            mock_result = MagicMock()
            mock_result.result = "Test response"

            async def mock_receive():
                yield mock_result

            mock_client.receive_response = mock_receive
            mock_client_class.return_value = mock_client

            # Patch isinstance checks
            with patch("herald.executor.ResultMessage", type(mock_result)):
                result = await executor.execute("Hello", chat_id=12345)

            assert result.success is True
            assert result.output == "Test response"
            mock_client.connect.assert_called_once()
            mock_client.query.assert_called_once_with("Hello")

    @pytest.mark.asyncio
    async def test_execute_reuses_client_for_same_chat(self, executor):
        """Should reuse existing client for the same chat (conversation continuity)."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            mock_result = MagicMock()
            mock_result.result = "Response"

            async def mock_receive():
                yield mock_result

            mock_client.receive_response = mock_receive
            mock_client_class.return_value = mock_client

            with patch("herald.executor.ResultMessage", type(mock_result)):
                # First call
                await executor.execute("First message", chat_id=12345)
                # Second call to same chat
                await executor.execute("Second message", chat_id=12345)

            # Client should only be created once
            assert mock_client_class.call_count == 1
            mock_client.connect.assert_called_once()
            # But query should be called twice
            assert mock_client.query.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_creates_separate_clients_per_chat(self, executor):
        """Should create separate clients for different chats."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            mock_result = MagicMock()
            mock_result.result = "Response"

            async def mock_receive():
                yield mock_result

            mock_client.receive_response = mock_receive
            mock_client_class.return_value = mock_client

            with patch("herald.executor.ResultMessage", type(mock_result)):
                # Calls to different chats
                await executor.execute("Message 1", chat_id=11111)
                await executor.execute("Message 2", chat_id=22222)

            # Should create two separate clients
            assert mock_client_class.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_extracts_text_from_assistant_messages(self, executor):
        """Should extract text from AssistantMessage when no result."""
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            # Create real SDK message types for proper isinstance checks
            mock_text_block = MagicMock(spec=TextBlock)
            mock_text_block.text = "Hello "

            mock_text_block2 = MagicMock(spec=TextBlock)
            mock_text_block2.text = "world"

            mock_assistant = MagicMock(spec=AssistantMessage)
            mock_assistant.content = [mock_text_block]

            mock_assistant2 = MagicMock(spec=AssistantMessage)
            mock_assistant2.content = [mock_text_block2]

            mock_result = MagicMock(spec=ResultMessage)
            mock_result.result = None  # No result text

            async def mock_receive():
                yield mock_assistant
                yield mock_assistant2
                yield mock_result

            mock_client.receive_response = mock_receive
            mock_client_class.return_value = mock_client

            result = await executor.execute("Hello", chat_id=12345)

            assert result.success is True
            assert "Hello" in result.output
            assert "world" in result.output

    @pytest.mark.asyncio
    async def test_reset_chat_disconnects_client(self, executor):
        """Should disconnect and remove client when reset."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.disconnect = AsyncMock()
            mock_client.query = AsyncMock()

            mock_result = MagicMock()
            mock_result.result = "Response"

            async def mock_receive():
                yield mock_result

            mock_client.receive_response = mock_receive
            mock_client_class.return_value = mock_client

            with patch("herald.executor.ResultMessage", type(mock_result)):
                # Create a client
                await executor.execute("Hello", chat_id=12345)
                assert 12345 in executor._clients

                # Reset the chat
                await executor.reset_chat(12345)

            mock_client.disconnect.assert_called_once()
            assert 12345 not in executor._clients

    @pytest.mark.asyncio
    async def test_reset_chat_noop_for_unknown_chat(self, executor):
        """Should do nothing when resetting unknown chat."""
        # Should not raise
        await executor.reset_chat(99999)
        assert 99999 not in executor._clients

    @pytest.mark.asyncio
    async def test_shutdown_disconnects_all_clients(self, executor):
        """Should disconnect all clients on shutdown."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client1 = AsyncMock()
            mock_client1.connect = AsyncMock()
            mock_client1.disconnect = AsyncMock()
            mock_client1.query = AsyncMock()

            mock_client2 = AsyncMock()
            mock_client2.connect = AsyncMock()
            mock_client2.disconnect = AsyncMock()
            mock_client2.query = AsyncMock()

            mock_result = MagicMock()
            mock_result.result = "Response"

            async def mock_receive():
                yield mock_result

            mock_client1.receive_response = mock_receive
            mock_client2.receive_response = mock_receive

            # Return different clients for different calls
            mock_client_class.side_effect = [mock_client1, mock_client2]

            with patch("herald.executor.ResultMessage", type(mock_result)):
                await executor.execute("Hello", chat_id=11111)
                await executor.execute("Hello", chat_id=22222)

                # Shutdown
                await executor.shutdown()

            mock_client1.disconnect.assert_called_once()
            mock_client2.disconnect.assert_called_once()
            assert len(executor._clients) == 0

    @pytest.mark.asyncio
    async def test_execute_handles_error_gracefully(self, executor):
        """Should return error result when SDK throws."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.disconnect = AsyncMock()
            mock_client.query = AsyncMock(side_effect=RuntimeError("SDK error"))
            mock_client_class.return_value = mock_client

            result = await executor.execute("Hello", chat_id=12345)

            assert result.success is False
            assert "SDK error" in result.error
            # Client should be removed after error
            assert 12345 not in executor._clients


class TestCreateExecutor:
    """Tests for create_executor factory function."""

    def test_create_with_valid_path(self, tmp_path):
        """Should create executor with valid working directory."""
        executor = create_executor(working_dir=tmp_path)
        assert executor.working_dir == tmp_path

    def test_create_with_missing_workdir(self, tmp_path):
        """Should raise ValueError when working_dir doesn't exist."""
        with pytest.raises(ValueError, match="Working directory does not exist"):
            create_executor(working_dir=tmp_path / "nonexistent")

    def test_create_with_custom_timeout(self, tmp_path):
        """Should accept custom timeout."""
        executor = create_executor(working_dir=tmp_path, timeout=600)
        assert executor.timeout == 600
