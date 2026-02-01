# ABOUTME: Tests for Herald Claude Code executor
# ABOUTME: Validates command execution and output parsing

import json
from pathlib import Path

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
    """Tests for ClaudeExecutor class."""

    def test_parse_output_with_result(self):
        """Should extract text from result event."""
        executor = ClaudeExecutor(
            claude_path=Path("/fake/claude"),
            working_dir=Path("/tmp"),
        )

        stdout = json.dumps({"type": "result", "result": "Final answer"})
        result = executor._parse_output(stdout)

        assert result.success is True
        assert result.output == "Final answer"

    def test_parse_output_with_assistant_messages(self):
        """Should extract text from assistant message events."""
        executor = ClaudeExecutor(
            claude_path=Path("/fake/claude"),
            working_dir=Path("/tmp"),
        )

        events = [
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello "}]}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "world"}]}},
        ]
        stdout = "\n".join(json.dumps(e) for e in events)
        result = executor._parse_output(stdout)

        assert result.success is True
        assert "Hello" in result.output
        assert "world" in result.output

    def test_parse_output_prefers_result(self):
        """Result event should take precedence over assistant messages."""
        executor = ClaudeExecutor(
            claude_path=Path("/fake/claude"),
            working_dir=Path("/tmp"),
        )

        events = [
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Thinking..."}]},
            },
            {"type": "result", "result": "Final answer"},
        ]
        stdout = "\n".join(json.dumps(e) for e in events)
        result = executor._parse_output(stdout)

        assert result.output == "Final answer"

    def test_parse_output_handles_non_json(self):
        """Should gracefully handle non-JSON lines."""
        executor = ClaudeExecutor(
            claude_path=Path("/fake/claude"),
            working_dir=Path("/tmp"),
        )

        stdout = "Some random text\n" + json.dumps({"type": "result", "result": "Answer"})
        result = executor._parse_output(stdout)

        assert result.success is True
        assert result.output == "Answer"


class TestCreateExecutor:
    """Tests for create_executor factory function."""

    def test_create_with_valid_paths(self, tmp_path):
        """Should create executor with valid paths."""
        fake_claude = tmp_path / "claude"
        fake_claude.touch()

        executor = create_executor(
            claude_path=fake_claude,
            working_dir=tmp_path,
        )

        assert executor.claude_path == fake_claude
        assert executor.working_dir == tmp_path

    def test_create_with_none_path(self, tmp_path):
        """Should raise ValueError when claude_path is None."""
        with pytest.raises(ValueError, match="Claude Code path is required"):
            create_executor(claude_path=None, working_dir=tmp_path)

    def test_create_with_missing_claude(self, tmp_path):
        """Should raise ValueError when claude_path doesn't exist."""
        with pytest.raises(ValueError, match="Claude Code not found"):
            create_executor(
                claude_path=tmp_path / "nonexistent",
                working_dir=tmp_path,
            )

    def test_create_with_missing_workdir(self, tmp_path):
        """Should raise ValueError when working_dir doesn't exist."""
        fake_claude = tmp_path / "claude"
        fake_claude.touch()

        with pytest.raises(ValueError, match="Working directory does not exist"):
            create_executor(
                claude_path=fake_claude,
                working_dir=tmp_path / "nonexistent",
            )
