# ABOUTME: Unit tests for HeartbeatScheduler
# ABOUTME: Tests periodic execution, active hours checking, and lifecycle management

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from herald.heartbeat.config import HeartbeatConfig
from herald.heartbeat.executor import HeartbeatResult
from herald.heartbeat.scheduler import HeartbeatScheduler


class TestHeartbeatSchedulerInit:
    """Tests for HeartbeatScheduler initialization."""

    def test_init_with_config(self):
        """Test initialization with HeartbeatConfig."""
        config = HeartbeatConfig(enabled=True, every="1h")
        mock_executor = MagicMock()
        mock_delivery = AsyncMock()

        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
            on_alert=mock_delivery,
        )

        assert scheduler.config == config
        assert scheduler.executor == mock_executor
        assert scheduler.on_alert == mock_delivery
        assert scheduler._running is False
        assert scheduler._task is None

    def test_init_disabled(self):
        """Test initialization with disabled config."""
        config = HeartbeatConfig(enabled=False)
        mock_executor = MagicMock()

        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
        )

        assert scheduler.config.enabled is False


class TestHeartbeatSchedulerLifecycle:
    """Tests for scheduler start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        """Test that start creates an asyncio task."""
        config = HeartbeatConfig(enabled=True, every="1h")
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(
            return_value=HeartbeatResult(
                success=True,
                content="OK",
                should_deliver=False,
                is_ok=True,
            )
        )

        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
        )

        scheduler.start()

        assert scheduler._running is True
        assert scheduler._task is not None

        # Clean up
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_does_nothing_when_disabled(self):
        """Test that start does nothing when heartbeat is disabled."""
        config = HeartbeatConfig(enabled=False)
        mock_executor = MagicMock()

        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
        )

        scheduler.start()

        assert scheduler._running is False
        assert scheduler._task is None

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        """Test that stop cancels the running task."""
        config = HeartbeatConfig(enabled=True, every="1h")
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(
            return_value=HeartbeatResult(
                success=True,
                content="OK",
                should_deliver=False,
                is_ok=True,
            )
        )

        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
        )

        scheduler.start()
        await scheduler.stop()

        assert scheduler._running is False
        assert scheduler._task is None

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """Test that stop handles not-running state gracefully."""
        config = HeartbeatConfig(enabled=True)
        mock_executor = MagicMock()

        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
        )

        # Should not raise
        await scheduler.stop()
        assert scheduler._running is False


class TestHeartbeatSchedulerExecution:
    """Tests for heartbeat execution logic."""

    @pytest.mark.asyncio
    async def test_executes_immediately_on_start(self):
        """Test that heartbeat executes immediately when started."""
        config = HeartbeatConfig(enabled=True, every="1h")
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(
            return_value=HeartbeatResult(
                success=True,
                content="OK",
                should_deliver=False,
                is_ok=True,
            )
        )

        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
        )

        scheduler.start()
        # Give time for immediate execution
        await asyncio.sleep(0.1)
        await scheduler.stop()

        mock_executor.execute.assert_called()

    @pytest.mark.asyncio
    async def test_executes_without_chat_id(self):
        """Heartbeat should execute without passing chat_id (uses HEARTBEAT_CHAT_ID default)."""
        config = HeartbeatConfig(enabled=True, every="1h")
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(
            return_value=HeartbeatResult(
                success=True,
                content="OK",
                should_deliver=False,
                is_ok=True,
            )
        )

        scheduler = HeartbeatScheduler(config=config, executor=mock_executor)
        scheduler.start()
        await asyncio.sleep(0.1)
        await scheduler.stop()

        # Should call execute without chat_id keyword argument
        mock_executor.execute.assert_called()
        call_kwargs = mock_executor.execute.call_args[1]
        assert "chat_id" not in call_kwargs

    @pytest.mark.asyncio
    async def test_calls_on_alert_when_should_deliver(self):
        """Test that on_alert is called when response should be delivered."""
        config = HeartbeatConfig(enabled=True, every="1h")
        mock_executor = MagicMock()
        alert_result = HeartbeatResult(
            success=True,
            content="Alert: Something needs attention!",
            should_deliver=True,
            is_ok=False,
        )
        mock_executor.execute = AsyncMock(return_value=alert_result)

        on_alert = AsyncMock()
        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
            on_alert=on_alert,
        )

        scheduler.start()
        await asyncio.sleep(0.1)
        await scheduler.stop()

        on_alert.assert_called_once_with(alert_result)

    @pytest.mark.asyncio
    async def test_does_not_call_on_alert_when_suppressed(self):
        """Test that on_alert is NOT called when response is suppressed."""
        config = HeartbeatConfig(enabled=True, every="1h")
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(
            return_value=HeartbeatResult(
                success=True,
                content="OK",
                should_deliver=False,
                is_ok=True,
            )
        )

        on_alert = AsyncMock()
        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
            on_alert=on_alert,
        )

        scheduler.start()
        await asyncio.sleep(0.1)
        await scheduler.stop()

        on_alert.assert_not_called()


class TestHeartbeatSchedulerActiveHours:
    """Tests for active hours checking."""

    @pytest.mark.asyncio
    async def test_skips_execution_outside_active_hours(self):
        """Test that execution is skipped outside active hours."""
        config = HeartbeatConfig(enabled=True, every="1h", active_hours="09:00-17:00")
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock()

        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
        )

        # Mock is_within_active_hours to return False
        with patch("herald.heartbeat.scheduler.is_within_active_hours", return_value=False):
            scheduler.start()
            await asyncio.sleep(0.1)
            await scheduler.stop()

        mock_executor.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_within_active_hours(self):
        """Test that execution happens within active hours."""
        config = HeartbeatConfig(enabled=True, every="1h", active_hours="09:00-17:00")
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(
            return_value=HeartbeatResult(
                success=True,
                content="OK",
                should_deliver=False,
                is_ok=True,
            )
        )

        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
        )

        # Mock is_within_active_hours to return True
        with patch("herald.heartbeat.scheduler.is_within_active_hours", return_value=True):
            scheduler.start()
            await asyncio.sleep(0.1)
            await scheduler.stop()

        mock_executor.execute.assert_called()

    @pytest.mark.asyncio
    async def test_executes_when_no_active_hours_configured(self):
        """Test that execution happens when no active hours are configured."""
        config = HeartbeatConfig(enabled=True, every="1h", active_hours=None)
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(
            return_value=HeartbeatResult(
                success=True,
                content="OK",
                should_deliver=False,
                is_ok=True,
            )
        )

        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
        )

        scheduler.start()
        await asyncio.sleep(0.1)
        await scheduler.stop()

        mock_executor.execute.assert_called()


class TestHeartbeatSchedulerInterval:
    """Tests for interval timing."""

    @pytest.mark.asyncio
    async def test_uses_config_interval(self):
        """Test that scheduler uses the configured interval."""
        config = HeartbeatConfig(enabled=True, every="5s")
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(
            return_value=HeartbeatResult(
                success=True,
                content="OK",
                should_deliver=False,
                is_ok=True,
            )
        )

        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
        )

        assert scheduler.config.interval == timedelta(seconds=5)

    @pytest.mark.asyncio
    async def test_trigger_immediate_execution(self):
        """Test that trigger() causes immediate execution."""
        config = HeartbeatConfig(enabled=True, every="1h")
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(
            return_value=HeartbeatResult(
                success=True,
                content="Triggered!",
                should_deliver=True,
                is_ok=False,
            )
        )

        on_alert = AsyncMock()
        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
            on_alert=on_alert,
        )

        # Trigger without starting (manual execution)
        await scheduler.trigger()

        mock_executor.execute.assert_called_once()
        on_alert.assert_called_once()


class TestHeartbeatSchedulerErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_continues_after_execution_error(self):
        """Test that scheduler continues after an execution error."""
        # Use 0.1s = 100 milliseconds (ms not supported in parser)
        config = HeartbeatConfig(enabled=True, every="0.1s")
        mock_executor = MagicMock()

        # First call fails, second and third succeed
        mock_executor.execute = AsyncMock(
            side_effect=[
                HeartbeatResult(
                    success=False,
                    content="",
                    should_deliver=False,
                    is_ok=False,
                    error="Connection failed",
                ),
                HeartbeatResult(
                    success=True,
                    content="OK",
                    should_deliver=False,
                    is_ok=True,
                ),
                HeartbeatResult(
                    success=True,
                    content="OK",
                    should_deliver=False,
                    is_ok=True,
                ),
            ]
        )

        scheduler = HeartbeatScheduler(
            config=config,
            executor=mock_executor,
        )

        scheduler.start()
        # Wait for multiple intervals (0.1s each, need ~0.25s for at least 2 calls)
        await asyncio.sleep(0.35)
        await scheduler.stop()

        # Should have attempted multiple times
        assert mock_executor.execute.call_count >= 2
