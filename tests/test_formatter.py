# ABOUTME: Tests for Herald Telegram message formatting
# ABOUTME: Validates escaping, splitting, and error handling

from herald.formatter import (
    escape_markdown_v2,
    format_error,
    format_for_telegram,
)


class TestEscapeMarkdownV2:
    """Tests for Telegram MarkdownV2 escaping."""

    def test_escape_special_chars(self):
        """Special characters should be escaped."""
        text = "Hello_world*test[link](url)"
        result = escape_markdown_v2(text)
        assert r"\_" in result
        assert r"\*" in result
        assert r"\[" in result
        assert r"\]" in result
        assert r"\(" in result
        assert r"\)" in result

    def test_preserve_code_blocks(self):
        """Code blocks should not have their contents escaped."""
        text = "Normal_text `code_block` more_text"
        result = escape_markdown_v2(text)
        # Code block content should be preserved
        assert "`code_block`" in result
        # But surrounding text should be escaped
        assert r"Normal\_text" in result
        assert r"more\_text" in result

    def test_preserve_multiline_code_blocks(self):
        """Multi-line code blocks should be preserved."""
        text = "Text ```python\ndef foo_bar():\n    pass\n``` end"
        result = escape_markdown_v2(text)
        # Code block should be preserved
        assert "```python" in result
        assert "foo_bar" in result  # Not escaped
        assert "```" in result

    def test_plain_text(self):
        """Plain text without special chars should pass through."""
        text = "Hello world this is normal text"
        result = escape_markdown_v2(text)
        assert result == text


class TestFormatForTelegram:
    """Tests for full Telegram formatting."""

    def test_short_message(self):
        """Short messages should return single FormattedMessage."""
        messages = format_for_telegram("Hello world")
        assert len(messages) == 1
        assert messages[0].parse_mode == "MarkdownV2"

    def test_empty_message(self):
        """Empty messages should return 'No response'."""
        messages = format_for_telegram("")
        assert len(messages) == 1
        assert messages[0].text == "No response"
        assert messages[0].parse_mode is None

    def test_long_message_split(self):
        """Long messages should be split into multiple parts."""
        # Create a message longer than the limit
        long_text = "Word " * 1000  # ~5000 chars
        messages = format_for_telegram(long_text, max_length=500)
        assert len(messages) > 1
        # Each message should be under the limit
        for msg in messages:
            assert len(msg.text) <= 500

    def test_split_at_newlines(self):
        """Message splitting should prefer newline boundaries."""
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        messages = format_for_telegram(text, max_length=30)
        # Should split at paragraph boundaries
        assert len(messages) >= 2


class TestFormatError:
    """Tests for error message formatting."""

    def test_error_format(self):
        """Errors should be formatted with emoji prefix."""
        result = format_error("Something went wrong")
        assert "❌" in result.text
        assert "Something went wrong" in result.text
        assert result.parse_mode is None  # Plain text for errors
