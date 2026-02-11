# ABOUTME: HeartbeatDelivery handles sending heartbeat alerts to Telegram chats
# ABOUTME: Supports "last" active chat tracking, specific chat IDs, or "none" to disable

import logging
from collections.abc import Awaitable, Callable

from herald.formatter import format_for_telegram
from herald.heartbeat.executor import HeartbeatResult

logger = logging.getLogger(__name__)

# Type alias for the send_message callback (chat_id, text, parse_mode)
SendMessageCallback = Callable[[int, str, str | None], Awaitable[None]]


class HeartbeatDelivery:
    """
    Delivers heartbeat alerts to Telegram chats.

    Supports multiple target modes:
    - "last": Send to the most recently active chat
    - "none": Disable delivery entirely
    - "<chat_id>": Send to a specific chat ID (string or number)
    """

    def __init__(
        self,
        send_message: SendMessageCallback,
        target: str = "last",
    ):
        """
        Initialize the HeartbeatDelivery.

        Args:
            send_message: Async callback to send messages (chat_id, text)
            target: Delivery target - "last", "none", or specific chat ID
        """
        self.send_message = send_message
        self.target = target
        self._last_active_chat: int | None = None

    def record_activity(self, chat_id: int) -> None:
        """
        Record activity from a chat.

        Call this when a user interacts with the bot to track
        the "last" active chat for heartbeat delivery.

        Args:
            chat_id: The chat ID that had activity
        """
        self._last_active_chat = chat_id
        logger.debug(f"Recorded activity for chat {chat_id}")

    def get_target_chat(self) -> int | None:
        """
        Get the target chat ID based on configuration.

        Returns:
            The target chat ID, or None if no delivery should happen
        """
        if self.target == "none":
            return None

        if self.target == "last":
            return self._last_active_chat

        # Attempt to parse as a specific chat ID
        try:
            return int(self.target)
        except ValueError:
            logger.warning(f"Invalid target chat ID: {self.target}")
            return None

    async def deliver(self, result: HeartbeatResult) -> None:
        """
        Deliver a heartbeat alert to the configured target.

        This method matches the AlertCallback signature for use
        with HeartbeatScheduler.on_alert.

        Args:
            result: The HeartbeatResult to deliver
        """
        chat_id = self.get_target_chat()

        if chat_id is None:
            logger.debug("No target chat for heartbeat delivery")
            return

        # Format the message with a heartbeat indicator, converting markdown to HTML
        raw_message = f"💓 **Heartbeat Alert**\n\n{result.content}"
        formatted_messages = format_for_telegram(raw_message)

        try:
            for msg in formatted_messages:
                await self.send_message(chat_id, msg.text, msg.parse_mode)
            logger.info(f"Delivered heartbeat alert to chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to deliver heartbeat alert: {e}")
