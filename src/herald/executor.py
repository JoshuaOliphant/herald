# ABOUTME: Claude Code execution wrapper for Herald using Agent SDK
# ABOUTME: Manages per-chat clients for conversation continuity with memory priming

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    Message,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
)

logger = logging.getLogger(__name__)

# After the last message, wait this long for more before considering done.
# Agent teams produce multiple ResultMessages with gaps between them.
MESSAGE_IDLE_TIMEOUT = 30.0

# Memory loading configuration
# Priority order: most actionable first
# Each tuple: (filename, budget_ratio)
MEMORY_FILES_PRIORITY = [
    ("pending.md", 0.3),  # 30% - actionable items
    ("learnings.md", 0.4),  # 40% - service knowledge
    ("observations.md", 0.3),  # 30% - preferences
]
MAX_MEMORY_CHARS = 10000


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
        memory_path: Path | None = None,
        model: str | None = None,
        agent_teams: bool = False,
    ):
        self.working_dir = working_dir
        self.memory_path = memory_path
        self.model = model
        self.agent_teams = agent_teams
        # Per-chat clients for conversation continuity
        self._clients: dict[int, ClaudeSDKClient] = {}

    def _smart_truncate(self, content: str, max_chars: int) -> str:
        """Truncate content while preserving line boundaries."""
        if len(content) <= max_chars:
            return content

        lines = content.split("\n")
        result: list[str] = []
        current_len = 0

        for line in lines:
            # Reserve space for the truncation indicator
            if current_len + len(line) + 1 > max_chars - 50:
                break
            result.append(line)
            current_len += len(line) + 1

        return "\n".join(result) + "\n\n[...content truncated...]"

    def _load_memory_context(self) -> str:
        """Load memory files with priority-based budget allocation."""
        if not self.memory_path or not self.memory_path.exists():
            return ""

        sections: list[str] = []
        for filename, budget_ratio in MEMORY_FILES_PRIORITY:
            filepath = self.memory_path / filename
            if not filepath.exists():
                continue

            content = filepath.read_text().strip()
            if not content:
                continue

            # Calculate budget for this file
            budget = int(MAX_MEMORY_CHARS * budget_ratio)

            # Smart truncation: preserve line boundaries
            if len(content) > budget:
                content = self._smart_truncate(content, budget)

            heading = filename.replace(".md", "").replace("-", " ").title()
            sections.append(f"## {heading}\n\n{content}")

        if not sections:
            return ""

        return "# Herald Memory\n\n" + "\n\n".join(sections)

    def _get_options(self) -> ClaudeAgentOptions:
        """Build options for Claude Agent SDK with memory context."""
        memory_context = self._load_memory_context()

        system_prompt: dict[str, Any]
        if memory_context:
            system_prompt = {
                "type": "preset",
                "preset": "claude_code",
                "append": memory_context,
            }
        else:
            system_prompt = {"type": "preset", "preset": "claude_code"}

        return ClaudeAgentOptions(
            cwd=self.working_dir,
            setting_sources=["user", "project"],  # Load CLAUDE.md
            permission_mode="bypassPermissions",
            max_turns=200,  # Allow long-running research and multi-step tasks
            system_prompt=system_prompt,
            model=self.model,
            env={"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}
            if self.agent_teams
            else None,
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

        Uses receive_messages() with idle timeout to support both regular
        queries and agent teams (which produce multiple ResultMessages
        across lead idle/wake cycles).
        """
        logger.info(
            "[chat %d] Executing: %s", chat_id, prompt[:100]
        )
        start_time = time.monotonic()

        try:
            client = await self._get_client(chat_id)
            await client.query(prompt)

            text_parts: list[str] = []
            last_result_text: str | None = None
            result_count = 0
            tool_count = 0
            message_count = 0

            msg_iter = client.receive_messages().__aiter__()
            while True:
                try:
                    message = await asyncio.wait_for(
                        _next_message(msg_iter),
                        timeout=MESSAGE_IDLE_TIMEOUT,
                    )
                except TimeoutError:
                    logger.debug(
                        "[chat %d] Stream idle for %ds, finishing",
                        chat_id, MESSAGE_IDLE_TIMEOUT,
                    )
                    break
                if message is None:
                    break

                message_count += 1

                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
                            logger.info(
                                "[chat %d] Assistant: %s",
                                chat_id, block.text[:200],
                            )
                        elif isinstance(block, ToolUseBlock):
                            tool_count += 1
                            logger.info(
                                "[chat %d] Tool #%d: %s",
                                chat_id, tool_count, block.name,
                            )
                elif isinstance(message, ResultMessage):
                    result_count += 1
                    cost = (
                        f"${message.total_cost_usd:.4f}"
                        if message.total_cost_usd is not None
                        else "n/a"
                    )
                    logger.info(
                        "[chat %d] Result #%d: %d turns, "
                        "cost=%s, %dms",
                        chat_id,
                        result_count,
                        message.num_turns,
                        cost,
                        message.duration_ms,
                    )
                    if message.result:
                        last_result_text = message.result
                elif isinstance(message, SystemMessage):
                    logger.debug(
                        "[chat %d] System: %s",
                        chat_id, message.subtype,
                    )

            elapsed = time.monotonic() - start_time
            # Prefer result text if available, otherwise combine text parts
            final_output = (
                last_result_text
                if last_result_text is not None
                else "\n".join(text_parts)
            )

            logger.info(
                "[chat %d] Complete: %d result(s), %d tool call(s), "
                "%d message(s), %.1fs",
                chat_id,
                result_count,
                tool_count,
                message_count,
                elapsed,
            )

            return ExecutionResult(
                success=True,
                output=final_output.strip(),
            )

        except Exception as e:
            elapsed = time.monotonic() - start_time
            logger.exception(
                "[chat %d] Error after %.1fs: %s",
                chat_id, elapsed, e,
            )
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


async def _next_message(msg_iter: AsyncIterator[Message]) -> Message | None:
    """Get next message from async iterator, returning None on exhaustion."""
    try:
        return await msg_iter.__anext__()
    except StopAsyncIteration:
        return None


def create_executor(
    working_dir: Path,
    memory_path: Path | None = None,
    model: str | None = None,
    agent_teams: bool = False,
) -> ClaudeExecutor:
    """Factory function to create a ClaudeExecutor with validation."""
    if not working_dir.exists():
        raise ValueError(f"Working directory does not exist: {working_dir}")

    return ClaudeExecutor(
        working_dir=working_dir,
        memory_path=memory_path,
        model=model,
        agent_teams=agent_teams,
    )
