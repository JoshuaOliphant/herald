# ABOUTME: HeartbeatScheduler for periodic health check execution using asyncio
# ABOUTME: Manages lifecycle (start/stop), active hours, and alert delivery

import asyncio
import logging
from collections.abc import Awaitable, Callable

from herald.heartbeat.active_hours import is_within_active_hours
from herald.heartbeat.config import HeartbeatConfig
from herald.heartbeat.executor import HeartbeatExecutor, HeartbeatResult

logger = logging.getLogger(__name__)

# Type alias for alert callback
AlertCallback = Callable[[HeartbeatResult], Awaitable[None]]

# Type alias for target chat resolver
GetTargetChat = Callable[[], int | None]


class HeartbeatScheduler:
    """
    Schedules and manages periodic heartbeat execution.

    This scheduler:
    1. Runs on a configurable interval
    2. Respects active hours (skip execution outside window)
    3. Resolves target chat for shared conversation context
    4. Executes HeartbeatExecutor and processes results
    5. Calls on_alert callback when results should be delivered
    """

    def __init__(
        self,
        config: HeartbeatConfig,
        executor: HeartbeatExecutor,
        on_alert: AlertCallback | None = None,
        get_target_chat: GetTargetChat | None = None,
    ):
        """
        Initialize the HeartbeatScheduler.

        Args:
            config: HeartbeatConfig with interval and active hours settings
            executor: HeartbeatExecutor to run checks
            on_alert: Optional callback for deliverable results
            get_target_chat: Optional callback to resolve which chat to
                execute in. Returns chat_id or None (skip heartbeat).
        """
        self.config = config
        self.executor = executor
        self.on_alert = on_alert
        self.get_target_chat = get_target_chat
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """
        Start the heartbeat scheduler.

        Creates an asyncio task that runs the periodic execution loop.
        Does nothing if heartbeat is disabled.
        """
        if not self.config.enabled:
            logger.info("Heartbeat is disabled, not starting scheduler")
            return

        if self._running:
            logger.warning("Heartbeat scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Heartbeat scheduler started with interval: {self.config.interval}")

    async def stop(self) -> None:
        """
        Stop the heartbeat scheduler.

        Cancels the running task and waits for cleanup.
        """
        if not self._running:
            return

        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Heartbeat scheduler stopped")

    async def trigger(self) -> None:
        """
        Trigger an immediate heartbeat execution.

        Useful for manual checks or testing.
        """
        await self._execute_heartbeat()

    async def _run_loop(self) -> None:
        """
        Main execution loop that runs periodically.

        Executes immediately on start, then waits for the configured interval.
        """
        try:
            while self._running:
                # Check active hours before execution
                if self._should_execute():
                    await self._execute_heartbeat()

                # Wait for next interval
                await asyncio.sleep(self.config.interval.total_seconds())
        except asyncio.CancelledError:
            logger.debug("Heartbeat scheduler loop cancelled")
            raise

    def _should_execute(self) -> bool:
        """
        Check if heartbeat should execute based on active hours.

        Returns:
            True if within active hours or no restriction configured
        """
        if not self.config.active_hours:
            return True

        return is_within_active_hours(self.config.active_hours)

    async def _execute_heartbeat(self) -> None:
        """
        Execute a single heartbeat and handle the result.

        Resolves the target chat from get_target_chat callback. If no
        active chat is available, the heartbeat is skipped.
        """
        # Resolve target chat for shared conversation
        chat_id: int | None = None
        if self.get_target_chat:
            chat_id = self.get_target_chat()
            if chat_id is None:
                logger.info("Heartbeat skipped: no active chat available")
                return

        logger.debug(f"Executing heartbeat check (chat_id={chat_id})")

        try:
            result = await self.executor.execute(chat_id=chat_id)

            if not result.success:
                logger.error(f"Heartbeat execution failed: {result.error}")
                return

            if result.should_deliver and self.on_alert:
                logger.info("Heartbeat alert triggered, delivering...")
                await self.on_alert(result)
            elif result.is_ok:
                logger.info(f"Heartbeat OK (suppressed, {len(result.content)} chars)")
            else:
                logger.info(f"Heartbeat complete (is_ok={result.is_ok}, should_deliver={result.should_deliver})")

        except Exception as e:
            logger.exception(f"Unexpected error in heartbeat execution: {e}")
