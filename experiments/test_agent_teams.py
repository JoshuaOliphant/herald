# ABOUTME: Experiment to test if Agent Teams work headlessly via the SDK
# ABOUTME: Enables CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS and asks for a team review

import asyncio
import logging
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

SECOND_BRAIN_PATH = "/Users/joshuaoliphant/Library/CloudStorage/Dropbox/python_workspace/second_brain"

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
                f"result_preview={message.result[:100] if message.result else 'None'}"
            )

    print("\n" + "=" * 60)
    print(f"DONE - {result_count} result messages received")
    print("=" * 60)
    print("\n".join(text_parts[-5:]) if text_parts else "(no text)")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
