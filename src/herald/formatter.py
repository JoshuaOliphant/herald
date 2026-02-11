# ABOUTME: Response formatting for Telegram messages using HTML parse mode
# ABOUTME: Converts markdown to Telegram-compatible HTML, handles splitting and length limits

from dataclasses import dataclass
from typing import Any

import mistune
from mistune.renderers.html import HTMLRenderer
from mistune.util import escape as escape_text

# Telegram message limit
MAX_MESSAGE_LENGTH = 4096


@dataclass
class FormattedMessage:
    """A formatted message ready for Telegram."""

    text: str
    parse_mode: str | None = "HTML"


class TelegramHTMLRenderer(HTMLRenderer):
    """Custom mistune renderer that outputs Telegram-compatible HTML.

    Telegram supports a limited subset of HTML tags:
    <b>, <i>, <u>, <s>, <code>, <pre>, <a>, <blockquote>, <tg-spoiler>
    """

    def __init__(self) -> None:
        super().__init__(escape=True)
        self._list_item_index = 0
        self._list_is_ordered = False

    # -- Inline elements --

    def emphasis(self, text: str) -> str:
        return "<i>" + text + "</i>"

    def strong(self, text: str) -> str:
        return "<b>" + text + "</b>"

    def codespan(self, text: str) -> str:
        return "<code>" + escape_text(text) + "</code>"

    def link(self, text: str, url: str, title: str | None = None) -> str:
        return '<a href="' + self.safe_url(url) + '">' + text + "</a>"

    def image(self, text: str, url: str, title: str | None = None) -> str:
        return '<a href="' + self.safe_url(url) + '">' + (text or "image") + "</a>"

    def linebreak(self) -> str:
        return "\n"

    def softbreak(self) -> str:
        return "\n"

    def inline_html(self, html: str) -> str:
        return escape_text(html)

    # -- Block elements --

    def paragraph(self, text: str) -> str:
        return text + "\n\n"

    def heading(self, text: str, level: int, **attrs: Any) -> str:
        return "<b>" + text.upper() + "</b>\n\n"

    def thematic_break(self) -> str:
        return "———\n\n"

    def block_code(self, code: str, info: str | None = None) -> str:
        html = "<pre>"
        if info is not None:
            info = info.strip()
        if info:
            lang = info.split(None, 1)[0]
            html += '<code class="language-' + lang + '">'
        else:
            html += "<code>"
        return html + escape_text(code) + "</code></pre>\n\n"

    def block_quote(self, text: str) -> str:
        return "<blockquote>" + text.strip() + "</blockquote>\n\n"

    def block_html(self, html: str) -> str:
        return escape_text(html.strip()) + "\n\n"

    def block_error(self, text: str) -> str:
        return text

    def blank_line(self) -> str:
        return ""

    def block_text(self, text: str) -> str:
        return text

    # -- Lists --
    # Telegram doesn't support <ul>/<ol> tags, so we render as plain text with bullets/numbers

    def list(self, text: str, ordered: bool, **attrs: Any) -> str:
        return text + "\n"

    def list_item(self, text: str) -> str:
        # list_item is called by HTMLRenderer.render_token which extracts
        # the children text. We prefix with bullet.
        # The ordered/unordered context is set by our custom list rendering.
        return "• " + text.strip() + "\n"


def _render_telegram_list(renderer: TelegramHTMLRenderer, token: dict, state: Any) -> str:
    """Custom list renderer that handles ordered/unordered lists with proper prefixes."""
    attrs = token["attrs"]
    ordered = attrs["ordered"]
    items = token["children"]
    result = []
    start = attrs.get("start", 1)

    for i, item in enumerate(items):
        # Render item children
        parts = []
        for child in item["children"]:
            if child["type"] == "blank_line":
                continue
            parts.append(renderer.render_token(child, state))
        text = "".join(parts).strip()

        prefix = f"{start + i}. " if ordered else "• "

        result.append(prefix + text + "\n")

    return "".join(result) + "\n"


def _render_telegram_table(renderer: TelegramHTMLRenderer, text: str) -> str:
    """Render tables as preformatted text."""
    return "<pre>" + text + "</pre>\n\n"


def _render_telegram_table_head(renderer: TelegramHTMLRenderer, text: str) -> str:
    return text


def _render_telegram_table_body(renderer: TelegramHTMLRenderer, text: str) -> str:
    return text


def _render_telegram_table_row(renderer: TelegramHTMLRenderer, text: str) -> str:
    return text.rstrip("\n") + "\n"


def _render_telegram_table_cell(
    renderer: TelegramHTMLRenderer, text: str, align: str | None = None, head: bool = False
) -> str:
    stripped = text.strip()
    if head:
        return stripped + " | "
    return stripped + " | "


def _render_telegram_strikethrough(renderer: TelegramHTMLRenderer, text: str) -> str:
    return "<s>" + text + "</s>"


def markdown_to_telegram_html(text: str) -> str:
    """Convert markdown to Telegram-compatible HTML."""
    renderer = TelegramHTMLRenderer()
    md = mistune.create_markdown(
        renderer=renderer,
        plugins=["strikethrough", "table"],
    )

    # Override the default list rendering to use our custom version
    # that properly handles ordered/unordered prefixes
    original_render_token = renderer.render_token

    def patched_render_token(token: dict, state: Any) -> str:
        if token["type"] == "list":
            return _render_telegram_list(renderer, token, state)
        return original_render_token(token, state)

    renderer.render_token = patched_render_token  # type: ignore[assignment]

    # Override table rendering to use <pre> format
    renderer.register("table", _render_telegram_table)
    renderer.register("table_head", _render_telegram_table_head)
    renderer.register("table_body", _render_telegram_table_body)
    renderer.register("table_row", _render_telegram_table_row)
    renderer.register("table_cell", _render_telegram_table_cell)

    # Override strikethrough to use <s> (Telegram) instead of <del> (default mistune)
    renderer.register("strikethrough", _render_telegram_strikethrough)

    return md(text).strip()


def format_for_telegram(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[FormattedMessage]:
    """
    Format text for Telegram, splitting if necessary.

    Returns a list of FormattedMessage objects ready to send.
    """
    if not text:
        return [FormattedMessage(text="No response", parse_mode=None)]

    try:
        converted = markdown_to_telegram_html(text)

        if len(converted) <= max_length:
            return [FormattedMessage(text=converted, parse_mode="HTML")]

        return _split_message(converted, max_length, parse_mode="HTML")

    except Exception:
        # Fall back to plain text if conversion fails
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
