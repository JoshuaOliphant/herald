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


class HeartbeatScheduler:
    """
    Schedules and manages periodic heartbeat execution.

    This scheduler:
    1. Runs on a configurable interval
    2. Respects active hours (skip execution outside window)
    3. Executes HeartbeatExecutor and processes results
    4. Calls on_alert callback when results should be delivered

    The heartbeat uses its own conversation via HEARTBEAT_CHAT_ID (executor default).
    """

    def __init__(
        self,
        config: HeartbeatConfig,
        executor: HeartbeatExecutor,
        on_alert: AlertCallback | None = None,
    ):
        """
        Initialize the HeartbeatScheduler.

        Args:
            config: HeartbeatConfig with interval and active hours settings
            executor: HeartbeatExecutor to run checks
            on_alert: Optional callback for deliverable results
        """
        self.config = config
        self.executor = executor
        self.on_alert = on_alert
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
        self._task.add_done_callback(self._on_task_done)
        logger.info(f"Heartbeat scheduler started with interval: {self.config.interval}")

    @staticmethod
    def _on_task_done(task: asyncio.Task[None]) -> None:
        """Log when the scheduler task finishes (expected or not)."""
        if task.cancelled():
            logger.info("Heartbeat scheduler task was cancelled")
        elif task.exception():
            logger.error(
                "Heartbeat scheduler task died with exception: %s",
                task.exception(),
            )
        else:
            logger.warning("Heartbeat scheduler task completed unexpectedly")

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
        Uses asyncio.create_task to ensure the sleep timer survives GC.
        """
        iteration = 0
        try:
            while self._running:
                iteration += 1
                logger.info("Heartbeat loop iteration %d starting", iteration)

                # Check active hours before execution
                if self._should_execute():
                    await self._execute_heartbeat()
                else:
                    logger.info("Heartbeat skipped: outside active hours")

                # Wait for next interval
                interval_secs = self.config.interval.total_seconds()
                logger.info(
                    "Heartbeat loop iteration %d sleeping for %.0fs",
                    iteration, interval_secs,
                )
                await asyncio.sleep(interval_secs)
                logger.info(
                    "Heartbeat loop iteration %d woke up after sleep",
                    iteration,
                )
        except asyncio.CancelledError:
            logger.info(
                "Heartbeat scheduler loop cancelled at iteration %d",
                iteration,
            )
            raise
        except Exception:
            logger.exception(
                "Heartbeat scheduler loop crashed at iteration %d",
                iteration,
            )
            raise

    def _should_execute(self) -> bool:
        """
        Check if heartbeat should execute based on active hours.

        Returns:
            True if within active hours or no restriction configured
        """
        if not self.config.active_hours:
            return True

        return is_within_active_hours(self.config.active_hours, tz=self.config.timezone)

    async def _execute_heartbeat(self) -> None:
        """
        Execute a single heartbeat and handle the result.

        Calls the executor without a chat_id so it defaults to HEARTBEAT_CHAT_ID,
        keeping heartbeat conversations isolated from user messages.
        """
        logger.debug("Executing heartbeat check")

        try:
            result = await self.executor.execute()

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
