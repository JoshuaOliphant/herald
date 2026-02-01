# ABOUTME: Response formatting for Telegram messages
# ABOUTME: Handles message splitting, markdown conversion, and length limits

import re
from dataclasses import dataclass

# Telegram message limit
MAX_MESSAGE_LENGTH = 4096


@dataclass
class FormattedMessage:
    """A formatted message ready for Telegram."""

    text: str
    parse_mode: str | None = "MarkdownV2"


def escape_markdown_v2(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2.

    Characters that need escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    # Characters to escape (except inside code blocks)
    special_chars = r"_*[]()~`>#+-=|{}.!"

    # Don't escape inside code blocks - handle them separately
    parts = []
    last_end = 0

    # Find all code blocks (both inline and multi-line)
    code_pattern = re.compile(r"(```[\s\S]*?```|`[^`]+`)")

    for match in code_pattern.finditer(text):
        # Escape the text before this code block
        before = text[last_end : match.start()]
        escaped_before = "".join(f"\\{c}" if c in special_chars else c for c in before)
        parts.append(escaped_before)

        # Keep code block as-is (Telegram handles it)
        parts.append(match.group())
        last_end = match.end()

    # Escape remaining text after last code block
    remaining = text[last_end:]
    escaped_remaining = "".join(f"\\{c}" if c in special_chars else c for c in remaining)
    parts.append(escaped_remaining)

    return "".join(parts)


def format_for_telegram(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[FormattedMessage]:
    """
    Format text for Telegram, splitting if necessary.

    Returns a list of FormattedMessage objects ready to send.
    """
    if not text:
        return [FormattedMessage(text="No response", parse_mode=None)]

    # Try to use MarkdownV2 first
    try:
        escaped = escape_markdown_v2(text)

        # If it fits in one message, return it
        if len(escaped) <= max_length:
            return [FormattedMessage(text=escaped, parse_mode="MarkdownV2")]

        # Split into multiple messages
        return _split_message(escaped, max_length, parse_mode="MarkdownV2")

    except Exception:
        # Fall back to plain text if markdown escaping fails
        if len(text) <= max_length:
            return [FormattedMessage(text=text, parse_mode=None)]

        return _split_message(text, max_length, parse_mode=None)


def _split_message(
    text: str,
    max_length: int,
    parse_mode: str | None,
) -> list[FormattedMessage]:
    """Split a long message into multiple parts at natural boundaries."""
    messages = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            messages.append(FormattedMessage(text=remaining, parse_mode=parse_mode))
            break

        # Find a good split point
        split_point = _find_split_point(remaining, max_length)

        chunk = remaining[:split_point].rstrip()
        messages.append(FormattedMessage(text=chunk, parse_mode=parse_mode))
        remaining = remaining[split_point:].lstrip()

    return messages


def _find_split_point(text: str, max_length: int) -> int:
    """Find the best point to split text, preferring natural boundaries."""
    # Look for split points in order of preference
    split_chars = ["\n\n", "\n", ". ", ", ", " "]

    for char in split_chars:
        # Search backwards from max_length
        pos = text.rfind(char, 0, max_length)
        if pos > max_length // 2:  # Don't split too early
            return pos + len(char)

    # No good split point found, force split at max_length
    return max_length


def format_error(error: str) -> FormattedMessage:
    """Format an error message for Telegram."""
    # Use plain text for errors to avoid escaping issues
    return FormattedMessage(
        text=f"❌ Error: {error}",
        parse_mode=None,
    )


def format_thinking() -> FormattedMessage:
    """Format a 'thinking' indicator message."""
    return FormattedMessage(
        text="🤔 Thinking...",
        parse_mode=None,
    )
