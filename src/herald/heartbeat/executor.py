# ABOUTME: HeartbeatExecutor that runs periodic health check prompts through Claude
# ABOUTME: Builds prompts with HEARTBEAT.md content and classifies responses

import logging
from dataclasses import dataclass
from pathlib import Path

from herald.executor import ClaudeExecutor, ExecutionResult, create_executor
from herald.heartbeat.classifier import classify_heartbeat_response
from herald.heartbeat.config import HeartbeatConfig
from herald.heartbeat.reader import read_heartbeat_file

logger = logging.getLogger(__name__)

# Default prompt when no custom prompt is configured
DEFAULT_HEARTBEAT_PROMPT = """You are performing a periodic health check.
Review the current state and any items needing attention.

If everything is OK and no alerts are needed, start with HEARTBEAT_OK.

If there are issues requiring attention, describe them clearly."""


@dataclass
class HeartbeatResult:
    """
    Result from a heartbeat execution.

    Attributes:
        success: True if execution completed (even if response indicates issues)
        content: Response content (HEARTBEAT_OK stripped if present)
        should_deliver: True if response should be sent to user
        is_ok: True if response indicated HEARTBEAT_OK
        error: Error message if execution failed
    """

    success: bool
    content: str
    should_deliver: bool
    is_ok: bool
    error: str | None = None


class HeartbeatExecutor:
    """
    Executes heartbeat prompts through Claude and classifies responses.

    This executor:
    1. Builds a prompt from config and optional HEARTBEAT.md file
    2. Runs the prompt through ClaudeExecutor
    3. Classifies the response for HEARTBEAT_OK and suppression logic
    4. Returns a HeartbeatResult for the scheduler to act on
    """

    # Reserved chat ID for heartbeat conversations
    # Negative to avoid collision with Telegram chat IDs
    HEARTBEAT_CHAT_ID = -999999

    def __init__(
        self,
        config: HeartbeatConfig,
        working_dir: Path,
        heartbeat_file: Path | None = None,
        claude_executor: ClaudeExecutor | None = None,
        memory_path: Path | None = None,
    ):
        """
        Initialize the HeartbeatExecutor.

        Args:
            config: HeartbeatConfig with prompt and threshold settings
            working_dir: Working directory for Claude execution
            heartbeat_file: Optional path to HEARTBEAT.md checklist
            claude_executor: Optional pre-configured ClaudeExecutor
            memory_path: Optional memory path for the executor
        """
        self.config = config
        self.working_dir = working_dir
        self.heartbeat_file = heartbeat_file
        self._claude_executor = claude_executor
        self._memory_path = memory_path

    @property
    def claude_executor(self) -> ClaudeExecutor:
        """Lazily create ClaudeExecutor if not provided."""
        if self._claude_executor is None:
            self._claude_executor = create_executor(
                working_dir=self.working_dir,
                memory_path=self._memory_path,
            )
        return self._claude_executor

    def _build_prompt(self) -> str:
        """
        Build the heartbeat prompt.

        Combines:
        1. Custom prompt or default prompt
        2. HEARTBEAT.md content if available
        3. Instructions for HEARTBEAT_OK response format
        """
        parts: list[str] = []

        # Start with custom or default prompt
        if self.config.prompt:
            parts.append(self.config.prompt)
        else:
            parts.append(DEFAULT_HEARTBEAT_PROMPT)

        # Add HEARTBEAT.md content if available
        if self.heartbeat_file:
            heartbeat_content = read_heartbeat_file(self.heartbeat_file)
            if heartbeat_content:
                parts.append("\n## Heartbeat Checklist\n")
                parts.append(heartbeat_content)

        # Ensure HEARTBEAT_OK instructions are included
        prompt = "\n".join(parts)
        if "HEARTBEAT_OK" not in prompt:
            parts.append(
                "\n\nIf all checks pass, respond with HEARTBEAT_OK. "
                "Otherwise, describe any issues without the HEARTBEAT_OK marker."
            )
            prompt = "\n".join(parts)

        return prompt

    async def execute(self, chat_id: int | None = None) -> HeartbeatResult:
        """
        Execute a heartbeat check.

        Args:
            chat_id: Target chat ID for shared conversation. If None,
                     falls back to the reserved HEARTBEAT_CHAT_ID.

        Returns:
            HeartbeatResult with classification and delivery decision
        """
        target_chat_id = chat_id if chat_id is not None else self.HEARTBEAT_CHAT_ID
        prompt = self._build_prompt()
        logger.info(
            f"Executing heartbeat ({len(prompt)} chars, chat_id={target_chat_id})"
        )

        try:
            result: ExecutionResult = await self.claude_executor.execute(
                prompt=prompt,
                chat_id=target_chat_id,
            )

            if not result.success:
                return HeartbeatResult(
                    success=False,
                    content="",
                    should_deliver=False,
                    is_ok=False,
                    error=result.error,
                )

            # Classify the response
            classification = classify_heartbeat_response(
                response=result.output,
                ack_max_chars=self.config.ack_max_chars,
            )

            return HeartbeatResult(
                success=True,
                content=classification.content,
                should_deliver=classification.should_deliver,
                is_ok=classification.is_ok,
            )

        except Exception as e:
            logger.exception("Unexpected error during heartbeat execution")
            return HeartbeatResult(
                success=False,
                content="",
                should_deliver=False,
                is_ok=False,
                error=f"Unexpected error: {e!s}",
            )

    async def shutdown(self) -> None:
        """Shutdown the underlying ClaudeExecutor if created."""
        if self._claude_executor is not None:
            await self._claude_executor.shutdown()
