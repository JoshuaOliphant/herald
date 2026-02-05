# ABOUTME: Unit tests for HeartbeatExecutor
# ABOUTME: Tests prompt building, HEARTBEAT.md inclusion, and response handling

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from herald.executor import ExecutionResult
from herald.heartbeat.config import HeartbeatConfig
from herald.heartbeat.executor import HeartbeatExecutor, HeartbeatResult


class TestHeartbeatResult:
    """Tests for the HeartbeatResult dataclass."""

    def test_heartbeat_result_success(self):
        """Test HeartbeatResult with successful execution."""
        result = HeartbeatResult(
            success=True,
            content="All systems operational",
            should_deliver=True,
            is_ok=False,
            error=None,
        )
        assert result.success is True
        assert result.content == "All systems operational"
        assert result.should_deliver is True
        assert result.is_ok is False
        assert result.error is None

    def test_heartbeat_result_ok_suppressed(self):
        """Test HeartbeatResult with OK response suppressed."""
        result = HeartbeatResult(
            success=True,
            content="OK",
            should_deliver=False,
            is_ok=True,
            error=None,
        )
        assert result.success is True
        assert result.should_deliver is False
        assert result.is_ok is True

    def test_heartbeat_result_error(self):
        """Test HeartbeatResult with error."""
        result = HeartbeatResult(
            success=False,
            content="",
            should_deliver=False,
            is_ok=False,
            error="Connection failed",
        )
        assert result.success is False
        assert result.error == "Connection failed"


class TestHeartbeatExecutorInit:
    """Tests for HeartbeatExecutor initialization."""

    def test_init_with_minimal_config(self, tmp_path):
        """Test initialization with minimal configuration."""
        config = HeartbeatConfig()
        executor = HeartbeatExecutor(
            config=config,
            working_dir=tmp_path,
        )
        assert executor.config == config
        assert executor.working_dir == tmp_path
        assert executor.heartbeat_file is None

    def test_init_with_heartbeat_file(self, tmp_path):
        """Test initialization with HEARTBEAT.md file path."""
        config = HeartbeatConfig()
        heartbeat_file = tmp_path / "HEARTBEAT.md"
        executor = HeartbeatExecutor(
            config=config,
            working_dir=tmp_path,
            heartbeat_file=heartbeat_file,
        )
        assert executor.heartbeat_file == heartbeat_file


class TestHeartbeatExecutorPromptBuilding:
    """Tests for heartbeat prompt building."""

    def test_build_prompt_default(self, tmp_path):
        """Test building prompt with default configuration."""
        config = HeartbeatConfig()
        executor = HeartbeatExecutor(config=config, working_dir=tmp_path)
        prompt = executor._build_prompt()

        # Default prompt should include instructions for monitoring
        assert "heartbeat" in prompt.lower() or "status" in prompt.lower()
        assert "HEARTBEAT_OK" in prompt

    def test_build_prompt_custom(self, tmp_path):
        """Test building prompt with custom prompt text."""
        custom_prompt = "Check the database and report issues"
        config = HeartbeatConfig(prompt=custom_prompt)
        executor = HeartbeatExecutor(config=config, working_dir=tmp_path)
        prompt = executor._build_prompt()

        assert custom_prompt in prompt
        assert "HEARTBEAT_OK" in prompt

    def test_build_prompt_includes_heartbeat_file(self, tmp_path):
        """Test that HEARTBEAT.md content is included in prompt."""
        heartbeat_content = """## Checklist
- [ ] Check API health
- [ ] Verify database connections"""

        heartbeat_file = tmp_path / "HEARTBEAT.md"
        heartbeat_file.write_text(heartbeat_content)

        config = HeartbeatConfig()
        executor = HeartbeatExecutor(
            config=config,
            working_dir=tmp_path,
            heartbeat_file=heartbeat_file,
        )
        prompt = executor._build_prompt()

        assert "Check API health" in prompt
        assert "Verify database connections" in prompt

    def test_build_prompt_missing_heartbeat_file(self, tmp_path):
        """Test prompt building when HEARTBEAT.md doesn't exist."""
        heartbeat_file = tmp_path / "HEARTBEAT.md"  # Doesn't exist

        config = HeartbeatConfig()
        executor = HeartbeatExecutor(
            config=config,
            working_dir=tmp_path,
            heartbeat_file=heartbeat_file,
        )
        prompt = executor._build_prompt()

        # Should still work without the file
        assert "HEARTBEAT_OK" in prompt


class TestHeartbeatExecutorExecution:
    """Tests for heartbeat execution."""

    @pytest.fixture
    def mock_claude_executor(self):
        """Create a mock ClaudeExecutor."""
        mock = MagicMock()
        mock.execute = AsyncMock()
        return mock

    @pytest.mark.asyncio
    async def test_execute_successful_ok_response(self, tmp_path, mock_claude_executor):
        """Test execution with HEARTBEAT_OK response."""
        mock_claude_executor.execute.return_value = ExecutionResult(
            success=True,
            output="HEARTBEAT_OK All systems operational",
        )

        config = HeartbeatConfig(ack_max_chars=300)
        executor = HeartbeatExecutor(
            config=config,
            working_dir=tmp_path,
            claude_executor=mock_claude_executor,
        )

        result = await executor.execute()

        assert result.success is True
        assert result.is_ok is True
        assert result.content == "All systems operational"
        # Short OK response should be suppressed
        assert result.should_deliver is False

    @pytest.mark.asyncio
    async def test_execute_alert_response(self, tmp_path, mock_claude_executor):
        """Test execution with non-OK alert response."""
        mock_claude_executor.execute.return_value = ExecutionResult(
            success=True,
            output="Alert: Database connection pool exhausted! Immediate action required.",
        )

        config = HeartbeatConfig()
        executor = HeartbeatExecutor(
            config=config,
            working_dir=tmp_path,
            claude_executor=mock_claude_executor,
        )

        result = await executor.execute()

        assert result.success is True
        assert result.is_ok is False
        assert "Database connection pool" in result.content
        assert result.should_deliver is True

    @pytest.mark.asyncio
    async def test_execute_long_ok_response_delivered(self, tmp_path, mock_claude_executor):
        """Test that long OK responses are delivered."""
        long_content = "HEARTBEAT_OK " + "A" * 400
        mock_claude_executor.execute.return_value = ExecutionResult(
            success=True,
            output=long_content,
        )

        config = HeartbeatConfig(ack_max_chars=300)
        executor = HeartbeatExecutor(
            config=config,
            working_dir=tmp_path,
            claude_executor=mock_claude_executor,
        )

        result = await executor.execute()

        assert result.success is True
        assert result.is_ok is True
        assert result.should_deliver is True  # Long content delivered

    @pytest.mark.asyncio
    async def test_execute_custom_ack_threshold(self, tmp_path, mock_claude_executor):
        """Test execution with custom ack_max_chars threshold."""
        mock_claude_executor.execute.return_value = ExecutionResult(
            success=True,
            output="HEARTBEAT_OK Short",
        )

        # With threshold of 10, "Short" (5 chars) should be suppressed
        config = HeartbeatConfig(ack_max_chars=10)
        executor = HeartbeatExecutor(
            config=config,
            working_dir=tmp_path,
            claude_executor=mock_claude_executor,
        )

        result = await executor.execute()
        assert result.should_deliver is False

        # With threshold of 3, "Short" should be delivered
        config2 = HeartbeatConfig(ack_max_chars=3)
        executor2 = HeartbeatExecutor(
            config=config2,
            working_dir=tmp_path,
            claude_executor=mock_claude_executor,
        )

        result2 = await executor2.execute()
        assert result2.should_deliver is True

    @pytest.mark.asyncio
    async def test_execute_error(self, tmp_path, mock_claude_executor):
        """Test execution with Claude executor error."""
        mock_claude_executor.execute.return_value = ExecutionResult(
            success=False,
            output="",
            error="Connection timeout",
        )

        config = HeartbeatConfig()
        executor = HeartbeatExecutor(
            config=config,
            working_dir=tmp_path,
            claude_executor=mock_claude_executor,
        )

        result = await executor.execute()

        assert result.success is False
        assert result.error == "Connection timeout"
        assert result.should_deliver is False

    @pytest.mark.asyncio
    async def test_execute_uses_heartbeat_chat_id(self, tmp_path, mock_claude_executor):
        """Test that heartbeat uses a reserved chat ID."""
        mock_claude_executor.execute.return_value = ExecutionResult(
            success=True,
            output="HEARTBEAT_OK",
        )

        config = HeartbeatConfig()
        executor = HeartbeatExecutor(
            config=config,
            working_dir=tmp_path,
            claude_executor=mock_claude_executor,
        )

        await executor.execute()

        # Verify execute was called with the heartbeat chat ID
        mock_claude_executor.execute.assert_called_once()
        call_args = mock_claude_executor.execute.call_args
        assert call_args[1]["chat_id"] == HeartbeatExecutor.HEARTBEAT_CHAT_ID


class TestHeartbeatExecutorCreateExecutor:
    """Tests for lazy executor creation."""

    def test_creates_executor_lazily(self, tmp_path):
        """Test that ClaudeExecutor is created lazily if not provided."""
        config = HeartbeatConfig()
        executor = HeartbeatExecutor(
            config=config,
            working_dir=tmp_path,
        )

        # Initially no executor
        assert executor._claude_executor is None

        # Property should trigger creation
        with patch("herald.heartbeat.executor.create_executor") as mock_create:
            mock_create.return_value = MagicMock()
            _ = executor.claude_executor
            mock_create.assert_called_once()
