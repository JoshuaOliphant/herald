# ABOUTME: Tests for Herald Claude Code executor using Agent SDK
# ABOUTME: Validates SDK client management and conversation continuity

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, TextBlock, ToolUseBlock

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


def _make_assistant(*texts: str) -> MagicMock:
    """Create a mock AssistantMessage with given text blocks."""
    blocks = []
    for text in texts:
        block = MagicMock(spec=TextBlock)
        block.text = text
        blocks.append(block)
    msg = MagicMock(spec=AssistantMessage)
    msg.content = blocks
    return msg


def _make_result(
    text: str | None = None,
    num_turns: int = 1,
    total_cost_usd: float = 0.01,
    duration_ms: int = 1000,
) -> MagicMock:
    """Create a mock ResultMessage with given result text and metadata."""
    msg = MagicMock(spec=ResultMessage)
    msg.result = text
    msg.num_turns = num_turns
    msg.total_cost_usd = total_cost_usd
    msg.duration_ms = duration_ms
    msg.duration_api_ms = duration_ms
    msg.is_error = False
    msg.session_id = "test"
    return msg


class TestClaudeExecutor:
    """Tests for ClaudeExecutor class with SDK mocking."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create an executor with a valid working directory."""
        return ClaudeExecutor(working_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_execute_creates_client_for_new_chat(self, executor):
        """Should create a new client for a chat that doesn't have one."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            async def mock_receive():
                yield _make_result("Test response")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

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

            async def mock_receive():
                yield _make_result("Response")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

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

            async def mock_receive():
                yield _make_result("Response")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            # Calls to different chats
            await executor.execute("Message 1", chat_id=11111)
            await executor.execute("Message 2", chat_id=22222)

            # Should create two separate clients
            assert mock_client_class.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_extracts_text_from_assistant_messages(self, executor):
        """Should extract text from AssistantMessage when no result."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            async def mock_receive():
                yield _make_assistant("Hello ")
                yield _make_assistant("world")
                yield _make_result(None)

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            result = await executor.execute("Hello", chat_id=12345)

            assert result.success is True
            assert "Hello" in result.output
            assert "world" in result.output

    @pytest.mark.asyncio
    async def test_execute_uses_last_result_from_multiple(self, executor):
        """Should use the last ResultMessage when multiple are received (agent teams)."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            async def mock_receive():
                yield _make_assistant("Creating team...")
                yield _make_result("Team spawned, waiting for reports")
                yield _make_assistant("Reports received, synthesizing...")
                yield _make_result("Final team summary with all findings")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            result = await executor.execute("Review projects", chat_id=12345)

            assert result.success is True
            assert result.output == "Final team summary with all findings"

    @pytest.mark.asyncio
    async def test_reset_chat_disconnects_client(self, executor):
        """Should disconnect and remove client when reset."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.disconnect = AsyncMock()
            mock_client.query = AsyncMock()

            async def mock_receive():
                yield _make_result("Response")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

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
    async def test_reset_client_disconnects_and_removes(self, executor):
        """_reset_client should disconnect and remove the client."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.disconnect = AsyncMock()
            mock_client.query = AsyncMock()

            async def mock_receive():
                yield _make_result("Response")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            await executor.execute("Hello", chat_id=500)
            assert 500 in executor._clients

            await executor._reset_client(500)
            assert 500 not in executor._clients
            mock_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_client_noop_for_unknown(self, executor):
        """_reset_client should do nothing for unknown chat_id."""
        await executor._reset_client(99999)  # Should not raise

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

            async def mock_receive():
                yield _make_result("Response")

            mock_client1.receive_messages = mock_receive
            mock_client2.receive_messages = mock_receive

            # Return different clients for different calls
            mock_client_class.side_effect = [mock_client1, mock_client2]

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

    def test_create_with_memory_path(self, tmp_path):
        """Should accept optional memory_path parameter."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        executor = create_executor(working_dir=tmp_path, memory_path=memory_dir)
        assert executor.memory_path == memory_dir


class TestMemoryLoading:
    """Tests for memory file loading and context building."""

    def test_load_memory_context_with_files(self, tmp_path):
        """Should load and format memory files."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "observations.md").write_text("La Boeuf prefers short responses")
        (memory_dir / "learnings.md").write_text("Keep it under 500 chars")

        executor = ClaudeExecutor(working_dir=tmp_path, memory_path=memory_dir)
        context = executor._load_memory_context()

        assert "# Herald Memory" in context
        assert "## Observations" in context
        assert "La Boeuf prefers short responses" in context
        assert "## Learnings" in context

    def test_load_memory_context_missing_dir(self, tmp_path):
        """Should return empty string if memory path doesn't exist."""
        executor = ClaudeExecutor(working_dir=tmp_path, memory_path=tmp_path / "nonexistent")
        assert executor._load_memory_context() == ""

    def test_load_memory_context_no_memory_path(self, tmp_path):
        """Should return empty string if no memory path configured."""
        executor = ClaudeExecutor(working_dir=tmp_path, memory_path=None)
        assert executor._load_memory_context() == ""

    def test_load_memory_respects_priority_order(self, tmp_path):
        """Should load pending before learnings before observations."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "pending.md").write_text("ACTION: Do this")
        (memory_dir / "learnings.md").write_text("LEARNING: Know this")
        (memory_dir / "observations.md").write_text("OBSERVATION: Notice this")

        executor = ClaudeExecutor(working_dir=tmp_path, memory_path=memory_dir)
        context = executor._load_memory_context()

        # Pending should appear before Learnings, which should appear before Observations
        pending_pos = context.find("ACTION: Do this")
        learnings_pos = context.find("LEARNING: Know this")
        observations_pos = context.find("OBSERVATION: Notice this")

        assert pending_pos < learnings_pos < observations_pos

    def test_smart_truncate_preserves_structure(self, tmp_path):
        """Should preserve line boundaries when truncating."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        # Create content that exceeds the 30% budget for observations (~3000 chars)
        content = "# Header\n\n" + "x" * 5000 + "\n\n# Another Header\n\n" + "y" * 5000
        (memory_dir / "observations.md").write_text(content)

        executor = ClaudeExecutor(working_dir=tmp_path, memory_path=memory_dir)
        context = executor._load_memory_context()

        # Should have truncation indicator
        assert "truncated" in context.lower()

    def test_load_memory_allocates_budget_per_file(self, tmp_path):
        """Each file should get its budget allocation."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        # Each file gets ~30-40% of 10K = 3-4K chars
        (memory_dir / "pending.md").write_text("p" * 5000)  # Exceeds 30% budget
        (memory_dir / "learnings.md").write_text("l" * 5000)  # Exceeds 40% budget
        (memory_dir / "observations.md").write_text("o" * 5000)  # Exceeds 30% budget

        executor = ClaudeExecutor(working_dir=tmp_path, memory_path=memory_dir)
        context = executor._load_memory_context()

        # Total should be under MAX_MEMORY_CHARS (10K) + overhead for headers
        assert len(context) <= 10500  # Allow some overhead for headers

    def test_load_memory_skips_empty_files(self, tmp_path):
        """Should skip files that are empty or whitespace only."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "pending.md").write_text("   \n\n  ")  # Whitespace only
        (memory_dir / "learnings.md").write_text("Actual content")

        executor = ClaudeExecutor(working_dir=tmp_path, memory_path=memory_dir)
        context = executor._load_memory_context()

        assert "## Pending" not in context
        assert "## Learnings" in context
        assert "Actual content" in context

    def test_load_memory_handles_missing_files_gracefully(self, tmp_path):
        """Should handle missing individual files gracefully."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        # Only create one file, others don't exist
        (memory_dir / "learnings.md").write_text("Some learnings")

        executor = ClaudeExecutor(working_dir=tmp_path, memory_path=memory_dir)
        context = executor._load_memory_context()

        assert "# Herald Memory" in context
        assert "## Learnings" in context
        assert "Some learnings" in context
        # Should not crash or include non-existent files
        assert "## Pending" not in context
        assert "## Observations" not in context


class TestSmartTruncate:
    """Tests for the _smart_truncate helper method."""

    def test_no_truncation_when_under_limit(self, tmp_path):
        """Should return content unchanged if under limit."""
        executor = ClaudeExecutor(working_dir=tmp_path, memory_path=None)
        content = "Short content"
        result = executor._smart_truncate(content, max_chars=1000)
        assert result == content

    def test_truncates_at_line_boundary(self, tmp_path):
        """Should truncate at line boundaries, not mid-line."""
        executor = ClaudeExecutor(working_dir=tmp_path, memory_path=None)
        content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
        result = executor._smart_truncate(content, max_chars=20)

        # Should not cut mid-line
        assert not result.endswith("Li")
        assert "truncated" in result.lower()

    def test_truncation_indicator_added(self, tmp_path):
        """Should add truncation indicator when content is cut."""
        executor = ClaudeExecutor(working_dir=tmp_path, memory_path=None)
        content = "x" * 1000
        result = executor._smart_truncate(content, max_chars=100)

        assert "[...content truncated...]" in result


class TestSystemPromptInjection:
    """Tests for memory injection into system prompt."""

    def test_get_options_without_memory(self, tmp_path):
        """Should return basic options when no memory configured."""
        executor = ClaudeExecutor(working_dir=tmp_path, memory_path=None)
        options = executor._get_options()

        # Should use preset without append
        assert options.system_prompt == {"type": "preset", "preset": "claude_code"}

    def test_get_options_with_memory(self, tmp_path):
        """Should append memory context to system prompt."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "observations.md").write_text("Test observation")

        executor = ClaudeExecutor(working_dir=tmp_path, memory_path=memory_dir)
        options = executor._get_options()

        # Should use preset with append
        assert options.system_prompt["type"] == "preset"
        assert options.system_prompt["preset"] == "claude_code"
        assert "# Herald Memory" in options.system_prompt["append"]
        assert "Test observation" in options.system_prompt["append"]


class TestModelAndAgentTeamsConfig:
    """Tests for model selection and agent teams configuration."""

    def test_get_options_with_model(self, tmp_path):
        """Should pass model to ClaudeAgentOptions when configured."""
        executor = ClaudeExecutor(
            working_dir=tmp_path, model="claude-opus-4-6"
        )
        options = executor._get_options()
        assert options.model == "claude-opus-4-6"

    def test_get_options_without_model(self, tmp_path):
        """Should default to None when no model configured."""
        executor = ClaudeExecutor(working_dir=tmp_path)
        options = executor._get_options()
        assert options.model is None

    def test_get_options_with_agent_teams(self, tmp_path):
        """Should set agent teams env var when enabled."""
        executor = ClaudeExecutor(
            working_dir=tmp_path, agent_teams=True
        )
        options = executor._get_options()
        assert options.env == {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}

    def test_get_options_without_agent_teams(self, tmp_path):
        """Should not set env when agent teams disabled."""
        executor = ClaudeExecutor(working_dir=tmp_path)
        options = executor._get_options()
        assert options.env is None

    def test_get_options_with_both(self, tmp_path):
        """Should set both model and agent teams together."""
        executor = ClaudeExecutor(
            working_dir=tmp_path,
            model="claude-opus-4-6",
            agent_teams=True,
        )
        options = executor._get_options()
        assert options.model == "claude-opus-4-6"
        assert options.env == {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}

    def test_create_executor_with_model_and_agent_teams(self, tmp_path):
        """Factory function should pass model and agent_teams through."""
        executor = create_executor(
            working_dir=tmp_path,
            model="claude-opus-4-6",
            agent_teams=True,
        )
        assert executor.model == "claude-opus-4-6"
        assert executor.agent_teams is True


class TestExecutionLogging:
    """Tests for executor logging during message consumption."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create an executor with a valid working directory."""
        return ClaudeExecutor(working_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_logs_assistant_text_preview(self, executor, caplog):
        """Should log a preview of assistant text messages."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            async def mock_receive():
                yield _make_assistant("Here is my detailed analysis of the project")
                yield _make_result("Done")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            with caplog.at_level(logging.INFO, logger="herald.executor"):
                await executor.execute("Analyze", chat_id=100)

            assert any("Here is my detailed analysis" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_tool_use(self, executor, caplog):
        """Should log tool invocations with tool name."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            # Create an assistant message with a tool use block
            tool_block = MagicMock(spec=ToolUseBlock)
            tool_block.id = "tool_123"
            tool_block.name = "Read"
            tool_block.input = {"file_path": "/tmp/test.py"}

            assistant_with_tool = MagicMock(spec=AssistantMessage)
            assistant_with_tool.content = [tool_block]

            async def mock_receive():
                yield assistant_with_tool
                yield _make_result("File contents here")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            with caplog.at_level(logging.INFO, logger="herald.executor"):
                await executor.execute("Read file", chat_id=100)

            assert any("Read" in r.message and "tool" in r.message.lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_result_with_metadata(self, executor, caplog):
        """Should log ResultMessage with cost and turn count."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            result_msg = MagicMock(spec=ResultMessage)
            result_msg.result = "Final answer"
            result_msg.num_turns = 5
            result_msg.total_cost_usd = 0.1234
            result_msg.duration_ms = 15000
            result_msg.duration_api_ms = 12000
            result_msg.is_error = False
            result_msg.session_id = "sess_1"

            async def mock_receive():
                yield result_msg

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            with caplog.at_level(logging.INFO, logger="herald.executor"):
                await executor.execute("Hello", chat_id=100)

            # Should log cost and turns
            assert any("$0.1234" in r.message for r in caplog.records)
            assert any("5 turn" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_completion_summary(self, executor, caplog):
        """Should log a summary when execution completes."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            async def mock_receive():
                yield _make_assistant("Thinking...")
                yield _make_assistant("Here you go")
                yield _make_result("Answer")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            with caplog.at_level(logging.INFO, logger="herald.executor"):
                await executor.execute("Question", chat_id=100)

            # Should have a completion summary with message count
            assert any("complete" in r.message.lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_multiple_results_for_agent_teams(self, executor, caplog):
        """Should log each ResultMessage separately in agent team scenarios."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            result1 = MagicMock(spec=ResultMessage)
            result1.result = "Team spawned"
            result1.num_turns = 3
            result1.total_cost_usd = 0.50
            result1.duration_ms = 20000
            result1.duration_api_ms = 18000
            result1.is_error = False
            result1.session_id = "s1"

            result2 = MagicMock(spec=ResultMessage)
            result2.result = "Final synthesis"
            result2.num_turns = 8
            result2.total_cost_usd = 0.95
            result2.duration_ms = 45000
            result2.duration_api_ms = 40000
            result2.is_error = False
            result2.session_id = "s1"

            async def mock_receive():
                yield _make_assistant("Creating team...")
                yield result1
                yield _make_assistant("Reports in...")
                yield result2

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            with caplog.at_level(logging.INFO, logger="herald.executor"):
                await executor.execute("Review", chat_id=100)

            # Should log both results with numbered labels
            result_logs = [
                r for r in caplog.records
                if "result" in r.message.lower() and "#" in r.message
            ]
            assert len(result_logs) >= 2

    @pytest.mark.asyncio
    async def test_logs_warning_on_timeout_with_no_results(
        self, executor, caplog,
    ):
        """Should log warning and return failure when stream times out before any ResultMessage."""
        with (
            patch("herald.executor.ClaudeSDKClient") as mock_client_class,
            patch("herald.executor.MESSAGE_IDLE_TIMEOUT", 0.01),
        ):
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.disconnect = AsyncMock()
            mock_client.query = AsyncMock()

            async def mock_receive():
                yield _make_assistant("Scanning files...")
                # Hang to trigger timeout — no ResultMessage
                await asyncio.sleep(10)

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            with caplog.at_level(logging.WARNING, logger="herald.executor"):
                result = await executor.execute("Do research", chat_id=100)

            assert any(
                "timed out" in r.message.lower()
                and r.levelno >= logging.WARNING
                for r in caplog.records
            )
            # Timeout with no results should be a failure
            assert result.success is False
            assert result.error is not None
            assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_timeout_with_no_result_resets_client(
        self, executor, caplog,
    ):
        """Should reset (disconnect + remove) client when timeout with no results."""
        with (
            patch("herald.executor.ClaudeSDKClient") as mock_client_class,
            patch("herald.executor.MESSAGE_IDLE_TIMEOUT", 0.01),
        ):
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.disconnect = AsyncMock()
            mock_client.query = AsyncMock()

            async def mock_receive():
                yield _make_assistant("Working...")
                await asyncio.sleep(10)

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            result = await executor.execute("Hang", chat_id=200)

            assert result.success is False
            # Client should be cleaned up (removed from _clients)
            assert 200 not in executor._clients
            mock_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_with_results_returns_success(
        self, executor, caplog,
    ):
        """Should return success when timeout occurs but results were received."""
        with (
            patch("herald.executor.ClaudeSDKClient") as mock_client_class,
            patch("herald.executor.MESSAGE_IDLE_TIMEOUT", 0.01),
            patch("herald.executor.POST_RESULT_IDLE_TIMEOUT", 0.01),
        ):
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            async def mock_receive():
                yield _make_assistant("Creating team...")
                yield _make_result("Team result with findings")
                # Hang after result — simulates agent team done but iterator not closed
                await asyncio.sleep(10)

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            result = await executor.execute("Review", chat_id=300)

            assert result.success is True
            assert result.output == "Team result with findings"
            assert result.error is None

    @pytest.mark.asyncio
    async def test_post_result_timeout_is_shorter(self, executor):
        """After receiving a ResultMessage, idle timeout should drop to POST_RESULT_IDLE_TIMEOUT."""
        with (
            patch("herald.executor.ClaudeSDKClient") as mock_client_class,
            patch("herald.executor.MESSAGE_IDLE_TIMEOUT", 100),
            patch("herald.executor.POST_RESULT_IDLE_TIMEOUT", 0.05),
        ):
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            async def mock_receive():
                yield _make_result("Quick answer")
                # Hang — should hit the short post-result timeout, not the 100s one
                await asyncio.sleep(10)

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            start = asyncio.get_event_loop().time()
            result = await executor.execute("Hello", chat_id=400)
            elapsed = asyncio.get_event_loop().time() - start

            assert result.success is True
            assert result.output == "Quick answer"
            # Should complete in well under 1s (post-result timeout is 0.05s),
            # not 100s (the main timeout)
            assert elapsed < 2.0

    @pytest.mark.asyncio
    async def test_logs_system_messages(self, executor, caplog):
        """Should log system messages at debug level."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            sys_msg = MagicMock(spec=SystemMessage)
            sys_msg.subtype = "init"
            sys_msg.data = {}

            async def mock_receive():
                yield sys_msg
                yield _make_result("Done")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            with caplog.at_level(logging.DEBUG, logger="herald.executor"):
                await executor.execute("Hello", chat_id=100)

            assert any("init" in r.message for r in caplog.records)


class TestConcurrencyLocking:
    """Tests for per-chat locking to prevent concurrent SDK client access.

    When multiple execute() calls target the same chat_id, they must be
    serialized to prevent racing on the shared receive_messages() stream.
    """

    @pytest.fixture
    def executor(self, tmp_path):
        """Create an executor with a valid working directory."""
        return ClaudeExecutor(working_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_concurrent_executes_are_serialized(self, executor):
        """Two concurrent execute() calls on the same chat should not overlap."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            # Track execution order to prove serialization
            execution_log: list[str] = []

            async def mock_receive_slow():
                execution_log.append("slow_start")
                yield _make_assistant("Working...")
                await asyncio.sleep(0.1)  # Simulate work
                yield _make_result("Slow result")
                execution_log.append("slow_end")

            async def mock_receive_fast():
                execution_log.append("fast_start")
                yield _make_result("Fast result")
                execution_log.append("fast_end")

            call_count = 0

            def receive_side_effect():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return mock_receive_slow()
                return mock_receive_fast()

            mock_client.receive_messages = receive_side_effect
            mock_client_class.return_value = mock_client

            # Launch two concurrent execute() calls on the same chat
            task1 = asyncio.create_task(
                executor.execute("First", chat_id=100)
            )
            task2 = asyncio.create_task(
                executor.execute("Second", chat_id=100)
            )

            result1, result2 = await asyncio.gather(task1, task2)

            # Both should succeed
            assert result1.success is True
            assert result2.success is True

            # Serialization: slow must fully complete before fast starts
            assert execution_log.index("slow_end") < execution_log.index("fast_start")

    @pytest.mark.asyncio
    async def test_different_chats_can_run_concurrently(self, executor):
        """Execute() calls on different chat_ids should NOT block each other."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            execution_log: list[str] = []

            async def mock_receive_chat1():
                execution_log.append("chat1_start")
                await asyncio.sleep(0.05)
                yield _make_result("Chat 1 done")
                execution_log.append("chat1_end")

            async def mock_receive_chat2():
                execution_log.append("chat2_start")
                yield _make_result("Chat 2 done")
                execution_log.append("chat2_end")

            call_count = 0

            def make_client(**kwargs):
                nonlocal call_count
                call_count += 1
                client = AsyncMock()
                client.connect = AsyncMock()
                client.query = AsyncMock()
                if call_count == 1:
                    client.receive_messages = mock_receive_chat1
                else:
                    client.receive_messages = mock_receive_chat2
                return client

            mock_client_class.side_effect = make_client

            # Launch concurrent calls on DIFFERENT chats
            task1 = asyncio.create_task(
                executor.execute("Msg 1", chat_id=111)
            )
            task2 = asyncio.create_task(
                executor.execute("Msg 2", chat_id=222)
            )

            await asyncio.gather(task1, task2)

            # Chat 2 (fast) should start before chat 1 (slow) ends
            assert execution_log.index("chat2_start") < execution_log.index("chat1_end")

    @pytest.mark.asyncio
    async def test_lock_released_after_error(self, executor):
        """Lock should be released even if execute() raises, allowing next call."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.disconnect = AsyncMock()
            # First query raises, second succeeds
            mock_client.query = AsyncMock(
                side_effect=[RuntimeError("Boom"), None]
            )

            async def mock_receive():
                yield _make_result("Recovery")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            # First call fails
            result1 = await executor.execute("Fail", chat_id=100)
            assert result1.success is False

            # Second call should work (lock was released)
            result2 = await executor.execute("Recover", chat_id=100)
            assert result2.success is True


class TestStreamingCallback:
    """Tests for on_assistant_text streaming callback during execution.

    Only substantive text (above MIN_STREAM_LENGTH) is forwarded via callback.
    Short status messages like "Let me check..." are filtered to avoid
    bombarding the user with noise.
    """

    @pytest.fixture
    def executor(self, tmp_path):
        """Create an executor with a valid working directory."""
        return ClaudeExecutor(working_dir=tmp_path)

    def _long_text(self, prefix: str) -> str:
        """Create text above MIN_STREAM_LENGTH threshold for testing."""
        # Pad to 250 chars to be safely above the 200-char threshold
        return prefix + " " + "x" * (250 - len(prefix) - 1)

    @pytest.mark.asyncio
    async def test_callback_called_for_substantive_text(self, executor):
        """Should invoke callback for AssistantMessages above length threshold."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            proposal_text = self._long_text("Here are my proposals")
            analysis_text = self._long_text("And the analysis")

            async def mock_receive():
                yield _make_assistant(proposal_text)
                yield _make_assistant(analysis_text)
                yield _make_result("Done")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            received: list[str] = []

            async def on_text(text: str) -> None:
                received.append(text)

            await executor.execute("Review", chat_id=100, on_assistant_text=on_text)

            assert received == [proposal_text, analysis_text]

    @pytest.mark.asyncio
    async def test_callback_filters_short_status_messages(self, executor):
        """Should NOT invoke callback for short status messages."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            long_text = self._long_text("Here's the detailed proposal")

            async def mock_receive():
                yield _make_assistant("Let me check the files...")
                yield _make_assistant("I'll read the README now")
                yield _make_assistant(long_text)
                yield _make_result("Done")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            received: list[str] = []

            async def on_text(text: str) -> None:
                received.append(text)

            await executor.execute("Review", chat_id=100, on_assistant_text=on_text)

            # Only the long substantive text should be streamed
            assert len(received) == 1
            assert received[0] == long_text

    @pytest.mark.asyncio
    async def test_callback_combines_multiple_text_blocks(self, executor):
        """Should combine multiple TextBlocks from one message and check total length."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            # Two blocks that are short individually but long combined
            block1 = MagicMock(spec=TextBlock)
            block1.text = "x" * 120
            block2 = MagicMock(spec=TextBlock)
            block2.text = "y" * 120
            msg = MagicMock(spec=AssistantMessage)
            msg.content = [block1, block2]

            async def mock_receive():
                yield msg
                yield _make_result("Done")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            received: list[str] = []

            async def on_text(text: str) -> None:
                received.append(text)

            await executor.execute("Hello", chat_id=100, on_assistant_text=on_text)

            # Combined length (240+) exceeds threshold, should be streamed
            assert len(received) == 1
            assert "x" * 120 in received[0]
            assert "y" * 120 in received[0]

    @pytest.mark.asyncio
    async def test_callback_skips_tool_only_messages(self, executor):
        """Should not invoke callback for AssistantMessages with only tool use."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            tool_block = MagicMock(spec=ToolUseBlock)
            tool_block.id = "t1"
            tool_block.name = "Read"
            tool_block.input = {}
            tool_msg = MagicMock(spec=AssistantMessage)
            tool_msg.content = [tool_block]

            async def mock_receive():
                yield tool_msg
                yield _make_result("File read")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            received: list[str] = []

            async def on_text(text: str) -> None:
                received.append(text)

            await executor.execute("Read file", chat_id=100, on_assistant_text=on_text)

            assert received == []

    @pytest.mark.asyncio
    async def test_execute_without_callback_still_works(self, executor):
        """Should work normally when no callback is provided (backward compat)."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            async def mock_receive():
                yield _make_assistant("Hello world")
                yield _make_result("Done")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            # No on_assistant_text param — should not raise
            result = await executor.execute("Hello", chat_id=100)

            assert result.success is True
            assert result.output == "Done"

    @pytest.mark.asyncio
    async def test_callback_called_between_multiple_results(self, executor):
        """Should stream substantive text from agent teams across result cycles."""
        with patch("herald.executor.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.query = AsyncMock()

            long_text = self._long_text("Reports received, here's the full analysis")

            async def mock_receive():
                yield _make_assistant("Spawning team...")  # Short, filtered
                yield _make_result("Team spawned")
                yield _make_assistant(long_text)  # Long, streamed
                yield _make_result("Final summary")

            mock_client.receive_messages = mock_receive
            mock_client_class.return_value = mock_client

            received: list[str] = []

            async def on_text(text: str) -> None:
                received.append(text)

            result = await executor.execute("Review", chat_id=100, on_assistant_text=on_text)

            # Only the long text should be streamed, not "Spawning team..."
            assert received == [long_text]
            assert result.output == "Final summary"
