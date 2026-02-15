# ABOUTME: Claude Code execution wrapper for Herald using Agent SDK
# ABOUTME: Manages per-chat clients for conversation continuity with memory priming

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
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

# Safety-net timeout for detecting hangs. The primary completion signal is the
# iterator's natural StopAsyncIteration (SDK sends {"type": "end"}).
# This only fires when the subprocess stops producing messages entirely —
# e.g., stuck tool calls, network issues, or API-side hangs.
MESSAGE_IDLE_TIMEOUT = 1800.0

# After receiving a ResultMessage, use this shorter timeout for subsequent
# messages. Once we have results, any follow-up (e.g., agent team handoffs)
# should arrive quickly. This prevents holding the per-chat lock for the
# full MESSAGE_IDLE_TIMEOUT after work is already complete.
POST_RESULT_IDLE_TIMEOUT = 30.0

# Only stream AssistantMessage text to the callback when it exceeds this length.
# Filters out short status messages ("Let me check...") while forwarding
# substantive content (proposals, tables, analysis).
MIN_STREAM_LENGTH = 200

# Memory loading configuration.
#
# Herald primes each Claude Code session with context from memory files stored
# in the herald_memory_path directory. Files are loaded in priority order (most
# actionable first) and each receives a percentage of the MAX_MEMORY_CHARS
# budget. This keeps the system prompt compact while giving the agent relevant
# context about pending work, learned patterns, and user preferences.
#
# Format: list of (filename, budget_ratio) tuples. Ratios should sum to 1.0.
# Users can customize content by editing the files directly; the filenames and
# budget ratios are intentionally not env-configurable to avoid the complexity
# of parsing structured tuples from environment variables.
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
        # Per-chat locks to serialize execute() calls and prevent racing
        # on the shared receive_messages() stream
        self._locks: dict[int, asyncio.Lock] = {}

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

    def _get_lock(self, chat_id: int) -> asyncio.Lock:
        """Get or create a lock for a chat to serialize execute() calls."""
        if chat_id not in self._locks:
            self._locks[chat_id] = asyncio.Lock()
        return self._locks[chat_id]

    async def _reset_client(self, chat_id: int) -> None:
        """Disconnect and remove the SDK client for a chat."""
        if chat_id not in self._clients:
            return
        with contextlib.suppress(Exception):
            await self._clients[chat_id].disconnect()
        del self._clients[chat_id]

    async def execute(
        self,
        prompt: str,
        chat_id: int,
        on_assistant_text: Callable[[str], Awaitable[None]] | None = None,
    ) -> ExecutionResult:
        """
        Execute a prompt through Claude Agent SDK.

        Uses receive_messages() with idle timeout to support both regular
        queries and agent teams (which produce multiple ResultMessages
        across lead idle/wake cycles).

        If on_assistant_text is provided, substantive AssistantMessage text
        (above MIN_STREAM_LENGTH) is forwarded via the callback as it arrives.

        Acquires a per-chat lock to prevent concurrent execute() calls from
        racing on the shared SDK client's receive_messages() stream.
        """
        lock = self._get_lock(chat_id)
        async with lock:
            return await self._execute_locked(
                prompt, chat_id, on_assistant_text
            )

    async def _execute_locked(
        self,
        prompt: str,
        chat_id: int,
        on_assistant_text: Callable[[str], Awaitable[None]] | None = None,
    ) -> ExecutionResult:
        """Execute a prompt while holding the per-chat lock."""
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
            timed_out = False

            msg_iter = client.receive_messages().__aiter__()
            while True:
                # Once we have results, use a shorter timeout — any follow-up
                # messages (agent team handoffs) should arrive quickly.
                timeout = (
                    POST_RESULT_IDLE_TIMEOUT
                    if result_count > 0
                    else MESSAGE_IDLE_TIMEOUT
                )
                try:
                    message = await asyncio.wait_for(
                        _next_message(msg_iter),
                        timeout=timeout,
                    )
                except TimeoutError:
                    timed_out = True
                    break
                if message is None:
                    break

                if isinstance(message, AssistantMessage):
                    msg_text_parts: list[str] = []
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
                            msg_text_parts.append(block.text)
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

                    # Stream substantive text to callback
                    if on_assistant_text and msg_text_parts:
                        combined = "\n".join(msg_text_parts)
                        if len(combined) >= MIN_STREAM_LENGTH:
                            await on_assistant_text(combined)
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

            if timed_out and result_count == 0:
                # Genuine hang — no ResultMessage means Claude never finished.
                # Reset the client since the subprocess is in an unknown state.
                logger.warning(
                    "[chat %d] Timed out after %.1fs with no "
                    "ResultMessage (%d tool calls). Resetting client.",
                    chat_id, elapsed, tool_count,
                )
                await self._reset_client(chat_id)
                return ExecutionResult(
                    success=False,
                    output="",
                    error=(
                        f"Timed out after {elapsed:.0f}s waiting for "
                        f"Claude to respond ({tool_count} tool calls "
                        f"in progress)"
                    ),
                )

            if timed_out:
                logger.info(
                    "[chat %d] Timed out after %.1fs but had %d "
                    "result(s), treating as complete.",
                    chat_id, elapsed, result_count,
                )

            # Prefer result text if available, otherwise combine text parts
            final_output = (
                last_result_text
                if last_result_text is not None
                else "\n".join(text_parts)
            )

            logger.info(
                "[chat %d] Complete: %d result(s), %d tool call(s), "
                "%.1fs",
                chat_id,
                result_count,
                tool_count,
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
            await self._reset_client(chat_id)
            return ExecutionResult(
                success=False,
                output="",
                error=f"Unexpected error: {e!s}",
            )

    async def reset_chat(self, chat_id: int) -> None:
        """Reset conversation for a chat (fresh start)."""
        if chat_id in self._clients:
            logger.info(f"Resetting conversation for chat {chat_id}")
        await self._reset_client(chat_id)

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
