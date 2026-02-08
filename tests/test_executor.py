# ABOUTME: Tests for Herald Claude Code executor using Agent SDK
# ABOUTME: Validates SDK client management and conversation continuity

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

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


def _make_result(text: str | None = None) -> MagicMock:
    """Create a mock ResultMessage with given result text."""
    msg = MagicMock(spec=ResultMessage)
    msg.result = text
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
