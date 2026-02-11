# ABOUTME: Tests for Herald Telegram message formatting
# ABOUTME: Validates markdown-to-HTML conversion, message splitting, and error handling

from herald.formatter import (
    format_error,
    format_for_telegram,
    markdown_to_telegram_html,
)


class TestMarkdownToTelegramHTML:
    """Tests for markdown-to-Telegram-HTML conversion."""

    def test_bold_conversion(self):
        """**bold** should become <b>bold</b>."""
        result = markdown_to_telegram_html("**bold**")
        assert "<b>bold</b>" in result

    def test_italic_conversion(self):
        """*italic* should become <i>italic</i>."""
        result = markdown_to_telegram_html("*italic*")
        assert "<i>italic</i>" in result

    def test_code_inline(self):
        """`code` should become <code>code</code>."""
        result = markdown_to_telegram_html("`code`")
        assert "<code>code</code>" in result

    def test_code_block(self):
        """Fenced code blocks should become <pre><code>...</code></pre>."""
        text = "```\ndef foo():\n    pass\n```"
        result = markdown_to_telegram_html(text)
        assert "<pre>" in result
        assert "<code>" in result
        assert "def foo():" in result

    def test_code_block_with_language(self):
        """Fenced code blocks with language should preserve language class."""
        text = "```python\nprint('hello')\n```"
        result = markdown_to_telegram_html(text)
        assert 'class="language-python"' in result
        assert "print('hello')" in result

    def test_link_conversion(self):
        """[text](url) should become <a href="url">text</a>."""
        result = markdown_to_telegram_html("[click here](https://example.com)")
        assert '<a href="https://example.com">click here</a>' in result

    def test_heading_conversion(self):
        """# Heading should become bold text."""
        result = markdown_to_telegram_html("# My Heading")
        assert "<b>" in result
        assert "MY HEADING" in result

    def test_heading_level_2(self):
        """## Heading should also become bold text."""
        result = markdown_to_telegram_html("## Subheading")
        assert "<b>" in result
        assert "SUBHEADING" in result

    def test_unordered_list_conversion(self):
        """Bullet lists should use bullet character."""
        text = "- First item\n- Second item\n- Third item"
        result = markdown_to_telegram_html(text)
        assert "• First item" in result
        assert "• Second item" in result
        assert "• Third item" in result

    def test_ordered_list_conversion(self):
        """Numbered lists should preserve numbering."""
        text = "1. First\n2. Second\n3. Third"
        result = markdown_to_telegram_html(text)
        assert "1. First" in result
        assert "2. Second" in result
        assert "3. Third" in result

    def test_blockquote(self):
        """> text should become <blockquote>text</blockquote>."""
        result = markdown_to_telegram_html("> This is a quote")
        assert "<blockquote>" in result
        assert "This is a quote" in result
        assert "</blockquote>" in result

    def test_strikethrough(self):
        """~~text~~ should become <s>text</s>."""
        result = markdown_to_telegram_html("~~deleted~~")
        assert "<s>deleted</s>" in result

    def test_html_escaping(self):
        """HTML special chars in text content should be escaped."""
        result = markdown_to_telegram_html("Use <script> & 'quotes' > \"stuff\"")
        assert "&lt;script&gt;" in result
        assert "&amp;" in result

    def test_mixed_formatting(self):
        """Nested formatting should work."""
        result = markdown_to_telegram_html("This is **bold and *italic* text**")
        assert "<b>" in result
        assert "<i>" in result

    def test_table_as_preformatted(self):
        """Tables should render as preformatted text."""
        text = "| Name | Age |\n|------|-----|\n| Alice | 30 |\n| Bob | 25 |"
        result = markdown_to_telegram_html(text)
        assert "<pre>" in result
        assert "Name" in result
        assert "Alice" in result

    def test_plain_text_passthrough(self):
        """Plain text without markdown should pass through without tags."""
        result = markdown_to_telegram_html("Just plain text here")
        assert "Just plain text here" in result
        # Should not contain formatting tags
        assert "<b>" not in result
        assert "<i>" not in result
        assert "<code>" not in result

    def test_thematic_break(self):
        """--- should become em dashes."""
        result = markdown_to_telegram_html("Above\n\n---\n\nBelow")
        assert "———" in result

    def test_image_as_link(self):
        """Images should render as links."""
        result = markdown_to_telegram_html("![alt text](https://example.com/img.png)")
        assert '<a href="https://example.com/img.png">' in result
        assert "alt text" in result

    def test_paragraph_separation(self):
        """Paragraphs should be separated by double newlines."""
        result = markdown_to_telegram_html("First paragraph.\n\nSecond paragraph.")
        assert "First paragraph." in result
        assert "Second paragraph." in result
        # Paragraphs should be separated
        assert "\n\n" in result


class TestFormatForTelegram:
    """Tests for full Telegram formatting."""

    def test_short_message(self):
        """Short messages should return single FormattedMessage with HTML parse_mode."""
        messages = format_for_telegram("Hello world")
        assert len(messages) == 1
        assert messages[0].parse_mode == "HTML"

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

    def test_split_preserves_html_parse_mode(self):
        """Split messages should retain HTML parse_mode."""
        long_text = "Word " * 1000
        messages = format_for_telegram(long_text, max_length=500)
        for msg in messages:
            assert msg.parse_mode == "HTML"

    def test_markdown_converted_to_html(self):
        """Markdown in input should be converted to HTML."""
        messages = format_for_telegram("**bold text**")
        assert len(messages) == 1
        assert "<b>bold text</b>" in messages[0].text
        assert messages[0].parse_mode == "HTML"


class TestFormatError:
    """Tests for error message formatting."""

    def test_error_format(self):
        """Errors should be formatted with emoji prefix."""
        result = format_error("Something went wrong")
        assert "❌" in result.text
        assert "Something went wrong" in result.text
        assert result.parse_mode is None  # Plain text for errors
