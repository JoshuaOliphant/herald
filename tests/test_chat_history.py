"""Tests for chat history persistence."""

import shutil
from datetime import datetime

import pytest

from herald.chat_history import ChatHistoryManager


@pytest.fixture
def temp_history_dir(tmp_path):
    """Create a temporary directory for chat history."""
    history_dir = tmp_path / "chat-history"
    history_dir.mkdir()
    yield history_dir
    # Cleanup
    if history_dir.exists():
        shutil.rmtree(history_dir)


@pytest.fixture
def chat_history(temp_history_dir):
    """Create a ChatHistoryManager instance."""
    return ChatHistoryManager(base_path=temp_history_dir)


class TestChatHistoryManager:
    """Tests for ChatHistoryManager class."""

    def test_save_user_message(self, chat_history, temp_history_dir):
        """Test saving a user message to chat history."""
        chat_id = 12345
        message = "Hello, Claude!"
        timestamp = datetime(2026, 2, 4, 10, 30, 0)

        chat_history.save_message(
            chat_id=chat_id,
            sender="user",
            message=message,
            timestamp=timestamp,
        )

        # Check that chat directory was created
        chat_dir = temp_history_dir / str(chat_id)
        assert chat_dir.exists()
        assert chat_dir.is_dir()

        # Check that a file was created (daily file)
        daily_file = chat_dir / "2026-02-04.md"
        assert daily_file.exists()

        # Check content format
        content = daily_file.read_text()
        assert "## 10:30:00 - User" in content
        assert "Hello, Claude!" in content

    def test_save_assistant_message(self, chat_history, temp_history_dir):
        """Test saving an assistant response to chat history."""
        chat_id = 12345
        message = "Hello! How can I help you today?"
        timestamp = datetime(2026, 2, 4, 10, 31, 0)

        chat_history.save_message(
            chat_id=chat_id,
            sender="assistant",
            message=message,
            timestamp=timestamp,
        )

        daily_file = temp_history_dir / str(chat_id) / "2026-02-04.md"
        content = daily_file.read_text()
        assert "## 10:31:00 - Assistant" in content
        assert "Hello! How can I help you today?" in content

    def test_multiple_messages_same_day(self, chat_history, temp_history_dir):
        """Test that multiple messages on the same day append to the same file."""
        chat_id = 12345
        timestamp1 = datetime(2026, 2, 4, 10, 30, 0)
        timestamp2 = datetime(2026, 2, 4, 11, 45, 0)

        chat_history.save_message(
            chat_id=chat_id,
            sender="user",
            message="First message",
            timestamp=timestamp1,
        )

        chat_history.save_message(
            chat_id=chat_id,
            sender="assistant",
            message="Second message",
            timestamp=timestamp2,
        )

        daily_file = temp_history_dir / str(chat_id) / "2026-02-04.md"
        content = daily_file.read_text()

        # Both messages should be in the same file
        assert content.count("##") == 2
        assert "First message" in content
        assert "Second message" in content

    def test_different_days_create_different_files(self, chat_history, temp_history_dir):
        """Test that messages on different days create separate files."""
        chat_id = 12345
        timestamp1 = datetime(2026, 2, 4, 23, 59, 0)
        timestamp2 = datetime(2026, 2, 5, 0, 1, 0)

        chat_history.save_message(
            chat_id=chat_id,
            sender="user",
            message="Late night message",
            timestamp=timestamp1,
        )

        chat_history.save_message(
            chat_id=chat_id,
            sender="user",
            message="Early morning message",
            timestamp=timestamp2,
        )

        file1 = temp_history_dir / str(chat_id) / "2026-02-04.md"
        file2 = temp_history_dir / str(chat_id) / "2026-02-05.md"

        assert file1.exists()
        assert file2.exists()
        assert "Late night message" in file1.read_text()
        assert "Early morning message" in file2.read_text()

    def test_different_chats_separate_directories(self, chat_history, temp_history_dir):
        """Test that different chat_ids create separate directories."""
        chat_id1 = 12345
        chat_id2 = 67890
        timestamp = datetime(2026, 2, 4, 10, 30, 0)

        chat_history.save_message(
            chat_id=chat_id1,
            sender="user",
            message="Message for chat 1",
            timestamp=timestamp,
        )

        chat_history.save_message(
            chat_id=chat_id2,
            sender="user",
            message="Message for chat 2",
            timestamp=timestamp,
        )

        chat_dir1 = temp_history_dir / str(chat_id1)
        chat_dir2 = temp_history_dir / str(chat_id2)

        assert chat_dir1.exists()
        assert chat_dir2.exists()
        assert (chat_dir1 / "2026-02-04.md").read_text().count("Message for chat 1") == 1
        assert (chat_dir2 / "2026-02-04.md").read_text().count("Message for chat 2") == 1

    def test_default_timestamp_uses_now(self, chat_history, temp_history_dir):
        """Test that if no timestamp is provided, current time is used."""
        chat_id = 12345

        # Save without explicit timestamp
        chat_history.save_message(
            chat_id=chat_id,
            sender="user",
            message="Message with auto timestamp",
        )

        # Should create file with today's date
        today = datetime.now().strftime("%Y-%m-%d")
        daily_file = temp_history_dir / str(chat_id) / f"{today}.md"
        assert daily_file.exists()

    def test_markdown_escaping_in_messages(self, chat_history, temp_history_dir):
        """Test that messages with markdown syntax are preserved correctly."""
        chat_id = 12345
        # Message with markdown characters that should be preserved
        message = "Check this **bold** and `code` and # heading"
        timestamp = datetime(2026, 2, 4, 10, 30, 0)

        chat_history.save_message(
            chat_id=chat_id,
            sender="user",
            message=message,
            timestamp=timestamp,
        )

        daily_file = temp_history_dir / str(chat_id) / "2026-02-04.md"
        content = daily_file.read_text()
        # Message content should be preserved as-is
        assert message in content

    def test_file_has_daily_header(self, chat_history, temp_history_dir):
        """Test that daily files have a proper header."""
        chat_id = 12345
        timestamp = datetime(2026, 2, 4, 10, 30, 0)

        chat_history.save_message(
            chat_id=chat_id,
            sender="user",
            message="First message of the day",
            timestamp=timestamp,
        )

        daily_file = temp_history_dir / str(chat_id) / "2026-02-04.md"
        content = daily_file.read_text()

        # Should have a header with the date
        assert "# Chat History - 2026-02-04" in content
