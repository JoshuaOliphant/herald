# ABOUTME: Claude Code execution wrapper for Herald
# ABOUTME: Runs Claude Code CLI and parses streaming JSON output

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result from a Claude Code execution."""

    success: bool
    output: str
    error: str | None = None
    raw_events: list[dict] | None = None


class ClaudeExecutor:
    """Executes Claude Code CLI commands and parses output."""

    def __init__(
        self,
        claude_path: Path,
        working_dir: Path,
        timeout: int = 300,
    ):
        self.claude_path = claude_path
        self.working_dir = working_dir
        self.timeout = timeout

    async def execute(self, prompt: str) -> ExecutionResult:
        """
        Execute a prompt through Claude Code CLI.

        Uses --dangerously-skip-permissions for automation but relies on
        damage-control hooks for safety guardrails.

        Note: Uses create_subprocess_exec with args list (not shell) for safety.
        """
        cmd = [
            str(self.claude_path),
            "-p",
            prompt,
            "--dangerously-skip-permissions",
            "--output-format",
            "stream-json",
        ]

        logger.info(f"Executing Claude Code: {prompt[:100]}...")

        try:
            # Using create_subprocess_exec with explicit args list - safe from injection
            process = await asyncio.create_subprocess_exec(
                cmd[0],
                *cmd[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            if process.returncode != 0:
                logger.error(f"Claude Code failed with return code {process.returncode}")
                logger.error(f"stderr: {stderr_text}")
                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"Claude Code failed: {stderr_text or 'Unknown error'}",
                )

            # Parse the streaming JSON output
            return self._parse_output(stdout_text)

        except TimeoutError:
            logger.error(f"Claude Code timed out after {self.timeout}s")
            return ExecutionResult(
                success=False,
                output="",
                error=f"Timed out after {self.timeout} seconds",
            )
        except Exception as e:
            logger.exception("Unexpected error in Claude Code")
            return ExecutionResult(
                success=False,
                output="",
                error=f"Unexpected error: {e!s}",
            )

    def _parse_output(self, stdout: str) -> ExecutionResult:
        """Parse streaming JSON output from Claude Code."""
        events = []
        text_parts = []
        result_text = None

        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue

            try:
                event = json.loads(line)
                events.append(event)

                # Extract text from assistant messages
                if event.get("type") == "assistant":
                    message = event.get("message", {})
                    for content in message.get("content", []):
                        if content.get("type") == "text":
                            text_parts.append(content.get("text", ""))

                # Check for result event
                elif event.get("type") == "result":
                    result_text = event.get("result", "")

            except json.JSONDecodeError:
                # Non-JSON line, might be raw output
                logger.debug(f"Non-JSON line in output: {line[:100]}")
                continue

        # Prefer result text if available, otherwise combine text parts
        final_output = result_text if result_text is not None else "\n".join(text_parts)

        return ExecutionResult(
            success=True,
            output=final_output.strip(),
            raw_events=events,
        )


def create_executor(
    claude_path: Path | None,
    working_dir: Path,
    timeout: int = 300,
) -> ClaudeExecutor:
    """Factory function to create a ClaudeExecutor with validation."""
    if claude_path is None:
        raise ValueError("Claude Code path is required")

    if not claude_path.exists():
        raise ValueError(f"Claude Code not found at: {claude_path}")

    if not working_dir.exists():
        raise ValueError(f"Working directory does not exist: {working_dir}")

    return ClaudeExecutor(
        claude_path=claude_path,
        working_dir=working_dir,
        timeout=timeout,
    )
