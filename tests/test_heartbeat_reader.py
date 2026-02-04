# ABOUTME: Tests for HEARTBEAT.md file reader with empty-file skip logic
# ABOUTME: Validates reading, empty file detection, and header-only detection

from pathlib import Path
from textwrap import dedent

import pytest

from herald.heartbeat.reader import read_heartbeat_file


class TestReadHeartbeatFile:
    """Test HEARTBEAT.md reader with empty-file skip logic."""

    def test_reads_file_with_content(self, tmp_path: Path) -> None:
        """Test that it reads a file with meaningful content."""
        heartbeat_file = tmp_path / "HEARTBEAT.md"
        content = dedent(
            """
            # Heartbeat

            ## Tasks

            - Check inbox processing
            - Verify knowledge capture
            """
        ).strip()
        heartbeat_file.write_text(content)

        result = read_heartbeat_file(heartbeat_file)

        assert result == content

    def test_returns_none_for_nonexistent_file(self, tmp_path: Path) -> None:
        """Test that it returns None when file doesn't exist."""
        nonexistent = tmp_path / "HEARTBEAT.md"

        result = read_heartbeat_file(nonexistent)

        assert result is None

    def test_returns_none_for_empty_file(self, tmp_path: Path) -> None:
        """Test that it returns None for empty file."""
        heartbeat_file = tmp_path / "HEARTBEAT.md"
        heartbeat_file.write_text("")

        result = read_heartbeat_file(heartbeat_file)

        assert result is None

    def test_returns_none_for_whitespace_only_file(self, tmp_path: Path) -> None:
        """Test that it returns None for file with only whitespace."""
        heartbeat_file = tmp_path / "HEARTBEAT.md"
        heartbeat_file.write_text("   \n\n  \t  \n")

        result = read_heartbeat_file(heartbeat_file)

        assert result is None

    def test_returns_none_for_headers_only_file(self, tmp_path: Path) -> None:
        """Test that it returns None for file with only markdown headers."""
        heartbeat_file = tmp_path / "HEARTBEAT.md"
        content = dedent(
            """
            # Heartbeat

            ## Tasks

            ## Notes
            """
        ).strip()
        heartbeat_file.write_text(content)

        result = read_heartbeat_file(heartbeat_file)

        assert result is None

    def test_returns_content_with_headers_and_text(self, tmp_path: Path) -> None:
        """Test that it returns content when headers have actual content below them."""
        heartbeat_file = tmp_path / "HEARTBEAT.md"
        content = dedent(
            """
            # Heartbeat

            ## Tasks

            Some actual task content here.
            """
        ).strip()
        heartbeat_file.write_text(content)

        result = read_heartbeat_file(heartbeat_file)

        assert result == content

    def test_uses_default_path_when_none_provided(self, tmp_path: Path, monkeypatch) -> None:
        """Test that it uses default workspace path when no path provided."""
        # Change working directory to tmp_path for this test
        monkeypatch.chdir(tmp_path)

        heartbeat_file = tmp_path / "HEARTBEAT.md"
        content = "# Tasks\n\nCheck something"
        heartbeat_file.write_text(content)

        result = read_heartbeat_file()

        assert result == content

    def test_default_path_returns_none_when_not_found(self, tmp_path: Path, monkeypatch) -> None:
        """Test that default path returns None when file doesn't exist."""
        # Change to tmp_path where no HEARTBEAT.md exists
        monkeypatch.chdir(tmp_path)

        result = read_heartbeat_file()

        assert result is None

    def test_handles_complex_markdown_without_content(self, tmp_path: Path) -> None:
        """Test handling of complex markdown structure with no actual content."""
        heartbeat_file = tmp_path / "HEARTBEAT.md"
        content = dedent(
            """
            # Heartbeat

            ## Morning Check

            ### Subsection

            #### Deep nested header

            ## Evening Review
            """
        ).strip()
        heartbeat_file.write_text(content)

        result = read_heartbeat_file(heartbeat_file)

        assert result is None

    def test_detects_content_in_list_items(self, tmp_path: Path) -> None:
        """Test that list items count as content."""
        heartbeat_file = tmp_path / "HEARTBEAT.md"
        content = dedent(
            """
            # Heartbeat

            - A task item
            """
        ).strip()
        heartbeat_file.write_text(content)

        result = read_heartbeat_file(heartbeat_file)

        assert result == content

    def test_handles_mixed_empty_lines_and_headers(self, tmp_path: Path) -> None:
        """Test file with lots of empty lines and only headers."""
        heartbeat_file = tmp_path / "HEARTBEAT.md"
        content = dedent(
            """


            # Heartbeat



            ## Tasks



            ## Notes


            """
        ).strip()
        heartbeat_file.write_text(content)

        result = read_heartbeat_file(heartbeat_file)

        assert result is None
