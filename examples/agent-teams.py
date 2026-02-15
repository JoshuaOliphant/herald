# ABOUTME: Example script demonstrating Agent Teams with the Claude Agent SDK
# ABOUTME: Shows how to use receive_messages() to handle multi-agent team responses

"""
Agent Teams Example
===================

This script demonstrates how Herald's agent teams feature works under the hood.
It connects to Claude Code via the Agent SDK, enables experimental agent teams,
and asks Claude to spawn a team of agents to review a knowledge base.

Usage:
    # Set SECOND_BRAIN_PATH to your knowledge base directory
    export SECOND_BRAIN_PATH=/path/to/your/second-brain
    uv run python examples/agent-teams.py

Requirements:
    - Claude Code installed and authenticated
    - claude-agent-sdk package (included in Herald's dependencies)
"""

import asyncio
import logging
import os
import sys

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

SECOND_BRAIN_PATH = os.environ.get(
    "SECOND_BRAIN_PATH", os.path.expanduser("~/second-brain")
)

PROMPT = """Create an agent team to review my active projects. Spawn three teammates:
- One to check projects/_active/ for stale projects (no recent commits in 7+ days)
- One to review inbox/ for unprocessed items
- One to check today's journal entry status

Have them each investigate and report findings. Keep it brief."""


async def main():
    options = ClaudeAgentOptions(
        cwd=SECOND_BRAIN_PATH,
        setting_sources=["user", "project"],
        permission_mode="bypassPermissions",
        model="claude-opus-4-6",
        max_turns=50,
        env={"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"},
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
        },
    )

    client = ClaudeSDKClient(options=options)
    await client.connect()

    logger.info("Connected to Claude Code, sending team prompt...")
    await client.query(PROMPT)

    text_parts: list[str] = []
    result_count = 0

    # Use receive_messages() instead of receive_response() to keep
    # listening after the lead's initial turn. The lead goes idle after
    # spawning teammates, then wakes up when they report back.
    async for message in client.receive_messages():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
                    print(f"[ASSISTANT] {block.text[:300]}")
        elif isinstance(message, SystemMessage):
            if message.subtype not in ("hook_started", "hook_response"):
                logger.info(f"[SYSTEM] subtype={message.subtype}")
        elif isinstance(message, ResultMessage):
            result_count += 1
            logger.info(
                f"[RESULT #{result_count}] turns={message.num_turns} "
                f"cost=${message.total_cost_usd:.4f} "
                f"duration={message.duration_ms}ms "
                f"result_preview="
                f"{message.result[:100] if message.result else 'None'}"
            )

    print("\n" + "=" * 60)
    print(f"DONE - {result_count} result messages received")
    print("=" * 60)
    print("\n".join(text_parts[-5:]) if text_parts else "(no text)")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
