# ABOUTME: Chat history persistence for Herald conversations
# ABOUTME: Saves timestamped conversation turns to markdown files organized by chat_id and date

from datetime import datetime
from pathlib import Path


class ChatHistoryManager:
    """Manages persistent storage of chat conversations as markdown files."""

    def __init__(self, base_path: Path):
        """
        Initialize the chat history manager.

        Args:
            base_path: Base directory for storing chat history (e.g., areas/herald/chat-history/)
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_message(
        self,
        chat_id: int,
        sender: str,
        message: str,
        timestamp: datetime | None = None,
    ) -> None:
        """
        Save a conversation message to the appropriate daily file.

        Args:
            chat_id: Telegram chat ID
            sender: Either "user" or "assistant"
            message: Message content
            timestamp: When the message was sent (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Create chat directory if it doesn't exist
        chat_dir = self.base_path / str(chat_id)
        chat_dir.mkdir(parents=True, exist_ok=True)

        # Daily file format: YYYY-MM-DD.md
        date_str = timestamp.strftime("%Y-%m-%d")
        daily_file = chat_dir / f"{date_str}.md"

        # Format the message entry
        time_str = timestamp.strftime("%H:%M:%S")
        sender_capitalized = sender.capitalize()
        entry = f"\n## {time_str} - {sender_capitalized}\n\n{message}\n"

        # Create or append to daily file
        if not daily_file.exists():
            # New file - add header
            header = f"# Chat History - {date_str}\n"
            daily_file.write_text(header + entry)
        else:
            # Append to existing file
            with daily_file.open("a") as f:
                f.write(entry)
