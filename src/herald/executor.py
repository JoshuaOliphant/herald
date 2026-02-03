# ABOUTME: Claude Code execution wrapper for Herald using Agent SDK
# ABOUTME: Manages per-chat clients for conversation continuity

import contextlib
import logging
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result from a Claude Code execution."""

    success: bool
    output: str
    error: str | None = None


class ClaudeExecutor:
    """Executes Claude Code queries using the Agent SDK with conversation continuity."""

    def __init__(
        self,
        working_dir: Path,
        timeout: int = 300,
    ):
        self.working_dir = working_dir
        self.timeout = timeout
        # Per-chat clients for conversation continuity
        self._clients: dict[int, ClaudeSDKClient] = {}

    def _get_options(self) -> ClaudeAgentOptions:
        """Build options for Claude Agent SDK."""
        return ClaudeAgentOptions(
            cwd=self.working_dir,
            setting_sources=["user", "project"],  # Load CLAUDE.md
            permission_mode="bypassPermissions",
            max_turns=50,
        )

    async def _get_client(self, chat_id: int) -> ClaudeSDKClient:
        """Get or create a client for a chat (conversation continuity)."""
        if chat_id not in self._clients:
            client = ClaudeSDKClient(options=self._get_options())
            await client.connect()
            self._clients[chat_id] = client
            logger.info(f"Created new SDK client for chat {chat_id}")
        return self._clients[chat_id]

    async def execute(self, prompt: str, chat_id: int) -> ExecutionResult:
        """
        Execute a prompt through Claude Agent SDK.

        Uses bypassPermissions for automation but relies on
        damage-control hooks for safety guardrails.
        """
        logger.info(f"Executing via SDK for chat {chat_id}: {prompt[:100]}...")

        try:
            client = await self._get_client(chat_id)
            await client.query(prompt)

            text_parts: list[str] = []
            result_text: str | None = None

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
                elif isinstance(message, ResultMessage) and message.result:
                    result_text = message.result

            # Prefer result text if available, otherwise combine text parts
            final_output = result_text if result_text is not None else "\n".join(text_parts)

            return ExecutionResult(
                success=True,
                output=final_output.strip(),
            )

        except TimeoutError:
            logger.error(f"Claude SDK timed out after {self.timeout}s")
            return ExecutionResult(
                success=False,
                output="",
                error=f"Timed out after {self.timeout} seconds",
            )
        except Exception as e:
            logger.exception("Unexpected error in Claude SDK execution")
            # On error, remove the client so next request creates fresh one
            if chat_id in self._clients:
                with contextlib.suppress(Exception):
                    await self._clients[chat_id].disconnect()
                del self._clients[chat_id]
            return ExecutionResult(
                success=False,
                output="",
                error=f"Unexpected error: {e!s}",
            )

    async def reset_chat(self, chat_id: int) -> None:
        """Reset conversation for a chat (fresh start)."""
        if chat_id in self._clients:
            logger.info(f"Resetting conversation for chat {chat_id}")
            try:
                await self._clients[chat_id].disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting client for chat {chat_id}: {e}")
            del self._clients[chat_id]

    async def shutdown(self) -> None:
        """Disconnect all clients on shutdown."""
        logger.info(f"Shutting down {len(self._clients)} SDK clients")
        for chat_id, client in list(self._clients.items()):
            try:
                await client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting client for chat {chat_id}: {e}")
        self._clients.clear()


def create_executor(
    working_dir: Path,
    timeout: int = 300,
) -> ClaudeExecutor:
    """Factory function to create a ClaudeExecutor with validation."""
    if not working_dir.exists():
        raise ValueError(f"Working directory does not exist: {working_dir}")

    return ClaudeExecutor(
        working_dir=working_dir,
        timeout=timeout,
    )
