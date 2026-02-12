# ABOUTME: Unit tests for heartbeat alert delivery to Telegram
# ABOUTME: Tests target resolution ("last", specific chat, "none") and message sending

from unittest.mock import AsyncMock

import pytest

from herald.heartbeat.delivery import HeartbeatDelivery
from herald.heartbeat.executor import HeartbeatResult


class TestHeartbeatDeliveryInit:
    """Tests for HeartbeatDelivery initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default target."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send)

        assert delivery.send_message == mock_send
        assert delivery.target == "last"
        assert delivery._last_active_chat is None

    def test_init_with_specific_target(self):
        """Test initialization with specific chat ID target."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="12345")

        assert delivery.target == "12345"

    def test_init_with_none_target(self):
        """Test initialization with 'none' target."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="none")

        assert delivery.target == "none"


class TestHeartbeatDeliveryLastActiveTracking:
    """Tests for last active chat tracking."""

    def test_record_activity_stores_chat_id(self):
        """Test that record_activity stores the last active chat ID."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send)

        delivery.record_activity(12345)
        assert delivery._last_active_chat == 12345

    def test_record_activity_updates_chat_id(self):
        """Test that record_activity updates to the most recent chat."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send)

        delivery.record_activity(12345)
        delivery.record_activity(67890)
        assert delivery._last_active_chat == 67890

    def test_get_target_chat_returns_last_active(self):
        """Test that get_target_chat returns last active for 'last' target."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="last")

        delivery.record_activity(12345)
        assert delivery.get_target_chat() == 12345

    def test_get_target_chat_returns_none_when_no_activity(self):
        """Test that get_target_chat returns None when no activity recorded."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="last")

        assert delivery.get_target_chat() is None


class TestHeartbeatDeliveryTargetResolution:
    """Tests for target resolution logic."""

    def test_get_target_chat_returns_specific_id(self):
        """Test that specific chat ID target returns that ID."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="12345")

        # Even if we record activity, should return specific target
        delivery.record_activity(67890)
        assert delivery.get_target_chat() == 12345

    def test_get_target_chat_returns_none_for_none_target(self):
        """Test that 'none' target always returns None."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="none")

        delivery.record_activity(12345)
        assert delivery.get_target_chat() is None

    def test_get_target_chat_parses_negative_chat_id(self):
        """Test that negative chat IDs (groups) are supported."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="-100123456789")

        assert delivery.get_target_chat() == -100123456789


class TestHeartbeatDeliveryDeliver:
    """Tests for the deliver method."""

    @pytest.mark.asyncio
    async def test_deliver_sends_message_to_target(self):
        """Test that deliver sends formatted message to target chat."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="12345")

        result = HeartbeatResult(
            success=True,
            content="Alert: Something needs attention!",
            should_deliver=True,
            is_ok=False,
        )

        await delivery.deliver(result)

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[0][0] == 12345  # chat_id
        assert "Something needs attention!" in call_args[0][1]  # text
        assert call_args[0][2] == "HTML"  # parse_mode

    @pytest.mark.asyncio
    async def test_deliver_skips_when_target_is_none(self):
        """Test that deliver does nothing when target is 'none'."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="none")

        result = HeartbeatResult(
            success=True,
            content="Alert!",
            should_deliver=True,
            is_ok=False,
        )

        await delivery.deliver(result)

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_deliver_skips_when_no_last_active(self):
        """Test that deliver does nothing when 'last' has no activity."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="last")

        result = HeartbeatResult(
            success=True,
            content="Alert!",
            should_deliver=True,
            is_ok=False,
        )

        await delivery.deliver(result)

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_deliver_to_last_active_chat(self):
        """Test that deliver sends to last active chat when target is 'last'."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="last")

        delivery.record_activity(12345)

        result = HeartbeatResult(
            success=True,
            content="Alert: Check the logs!",
            should_deliver=True,
            is_ok=False,
        )

        await delivery.deliver(result)

        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == 12345

    @pytest.mark.asyncio
    async def test_deliver_includes_heartbeat_emoji(self):
        """Test that delivered messages include heartbeat emoji prefix."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="12345")

        result = HeartbeatResult(
            success=True,
            content="System check required",
            should_deliver=True,
            is_ok=False,
        )

        await delivery.deliver(result)

        message = mock_send.call_args[0][1]
        assert "💓" in message

    @pytest.mark.asyncio
    async def test_deliver_formats_as_html(self):
        """Test that delivered messages use HTML parse_mode."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="12345")

        result = HeartbeatResult(
            success=True,
            content="**Bold alert** with `code`",
            should_deliver=True,
            is_ok=False,
        )

        await delivery.deliver(result)

        message = mock_send.call_args[0][1]
        parse_mode = mock_send.call_args[0][2]
        assert "<b>" in message  # Bold converted to HTML
        assert "<code>" in message  # Code converted to HTML
        assert parse_mode == "HTML"

    @pytest.mark.asyncio
    async def test_deliver_handles_send_error_gracefully(self):
        """Test that delivery errors are handled gracefully."""
        mock_send = AsyncMock(side_effect=Exception("Network error"))
        delivery = HeartbeatDelivery(send_message=mock_send, target="12345")

        result = HeartbeatResult(
            success=True,
            content="Alert!",
            should_deliver=True,
            is_ok=False,
        )

        # Should not raise
        await delivery.deliver(result)


class TestHeartbeatDeliveryLastContent:
    """Tests for last delivered content storage and consumption."""

    @pytest.mark.asyncio
    async def test_last_delivered_content_stored(self):
        """After deliver(), _last_delivered_content should hold the result content."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="12345")

        result = HeartbeatResult(
            success=True,
            content="Alert: Something needs attention!",
            should_deliver=True,
            is_ok=False,
        )

        await delivery.deliver(result)

        assert delivery._last_delivered_content == "Alert: Something needs attention!"

    def test_consume_last_content_returns_and_clears(self):
        """consume_last_content() should return content once, then None."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send)
        delivery._last_delivered_content = "Some heartbeat content"

        first = delivery.consume_last_content()
        second = delivery.consume_last_content()

        assert first == "Some heartbeat content"
        assert second is None

    def test_consume_last_content_none_when_no_delivery(self):
        """consume_last_content() should return None if nothing was delivered."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send)

        assert delivery.consume_last_content() is None


class TestHeartbeatDeliveryAsCallback:
    """Tests for using delivery as scheduler callback."""

    @pytest.mark.asyncio
    async def test_can_be_used_as_on_alert_callback(self):
        """Test that deliver method matches scheduler's on_alert signature."""
        mock_send = AsyncMock()
        delivery = HeartbeatDelivery(send_message=mock_send, target="12345")

        result = HeartbeatResult(
            success=True,
            content="Alert!",
            should_deliver=True,
            is_ok=False,
        )

        # deliver method should be callable with just the result
        await delivery.deliver(result)

        mock_send.assert_called_once()
