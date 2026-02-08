# ABOUTME: FastAPI webhook handler for Telegram updates with heartbeat
# ABOUTME: Receives messages, validates users, routes to Claude Code

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from .chat_history import ChatHistoryManager
from .config import Settings
from .executor import ClaudeExecutor, create_executor
from .formatter import format_error, format_for_telegram
from .heartbeat import HeartbeatDelivery, HeartbeatExecutor, HeartbeatScheduler

logger = logging.getLogger(__name__)


class TelegramUpdate(BaseModel):
    """Telegram webhook update payload."""

    update_id: int
    message: dict[str, Any] | None = None
    edited_message: dict[str, Any] | None = None


class WebhookHandler:
    """Handles incoming Telegram webhook updates."""

    def __init__(
        self,
        settings: Settings,
        executor: ClaudeExecutor,
        on_activity: Callable[[int], None] | None = None,
        chat_history: ChatHistoryManager | None = None,
    ):
        self.settings = settings
        self.executor = executor
        self._http_client: httpx.AsyncClient | None = None
        self._on_activity = on_activity
        # Track processed update IDs to prevent duplicate processing from Telegram retries
        self._processed_updates: OrderedDict[int, bool] = OrderedDict()
        self._max_tracked_updates = 1000  # Limit memory usage
        # Chat history manager (optional)
        self._chat_history = chat_history or ChatHistoryManager(
            base_path=settings.chat_history_path
        )

    async def start(self) -> None:
        """Initialize async resources."""
        self._http_client = httpx.AsyncClient(timeout=30.0)

    async def stop(self) -> None:
        """Clean up async resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        # Shutdown executor (disconnects all SDK clients)
        await self.executor.shutdown()

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            raise RuntimeError("WebhookHandler not started")
        return self._http_client

    def _mark_processed(self, update_id: int) -> bool:
        """Mark an update as processed. Returns False if already processed."""
        if update_id in self._processed_updates:
            return False
        self._processed_updates[update_id] = True
        # Trim old entries to limit memory usage
        while len(self._processed_updates) > self._max_tracked_updates:
            self._processed_updates.popitem(last=False)
        return True

    async def handle_update(self, update: TelegramUpdate) -> None:
        """Process an incoming Telegram update."""
        # Deduplicate - Telegram retries if we don't respond quickly
        if not self._mark_processed(update.update_id):
            logger.debug(f"Update {update.update_id} already processed, skipping")
            return

        # Get the message (could be new or edited)
        message = update.message or update.edited_message
        if not message:
            logger.debug(f"Update {update.update_id} has no message, ignoring")
            return

        # Extract sender info
        from_user = message.get("from", {})
        user_id = from_user.get("id")
        display_name = from_user.get("first_name") or from_user.get("username") or "unknown"
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")

        if not text:
            logger.debug(f"Message from {display_name} has no text, ignoring")
            return

        # Security: Check if user is allowed
        if not self._is_user_allowed(user_id):
            logger.warning(f"Unauthorized user {user_id} ({display_name}) attempted access")
            await self._send_message(
                chat_id,
                "⛔ Unauthorized. This bot is private.",
            )
            return

        # Handle /reset command - clears conversation history
        if text.strip().lower() == "/reset":
            logger.info(f"Reset command from {display_name} ({user_id}) for chat {chat_id}")
            # Log reset command to history
            self._chat_history.save_message(
                chat_id=chat_id,
                sender="system",
                message="/reset - Conversation reset requested",
                timestamp=datetime.now(),
            )
            await self.executor.reset_chat(chat_id)
            await self._send_message(chat_id, "🔄 Conversation reset. Starting fresh!")
            return

        logger.info(f"Processing message from {display_name} ({user_id}): {text[:50]}...")

        # Track activity for heartbeat delivery targeting
        if self._on_activity and chat_id:
            self._on_activity(chat_id)

        # Log user message to chat history
        timestamp = datetime.now()
        self._chat_history.save_message(
            chat_id=chat_id,
            sender="user",
            message=text,
            timestamp=timestamp,
        )

        # Send typing indicator
        await self._send_chat_action(chat_id, "typing")

        # Execute through Claude Code (with chat_id for conversation continuity)
        result = await self.executor.execute(text, chat_id)

        if result.success:
            # Format and send response
            messages = format_for_telegram(result.output)
            for msg in messages:
                await self._send_message(chat_id, msg.text, parse_mode=msg.parse_mode)

            # Log assistant response to chat history
            self._chat_history.save_message(
                chat_id=chat_id,
                sender="assistant",
                message=result.output,
                timestamp=datetime.now(),
            )
        else:
            # Send error message
            error_msg = format_error(result.error or "Unknown error")
            await self._send_message(chat_id, error_msg.text, parse_mode=error_msg.parse_mode)

            # Log error to chat history
            self._chat_history.save_message(
                chat_id=chat_id,
                sender="assistant",
                message=f"[Error] {result.error or 'Unknown error'}",
                timestamp=datetime.now(),
            )

    def _is_user_allowed(self, user_id: int | None) -> bool:
        """Check if a user is in the allowed list."""
        if user_id is None:
            return False
        if not self.settings.allowed_telegram_user_ids:
            # If no whitelist configured, deny all (fail secure)
            return False
        return user_id in self.settings.allowed_telegram_user_ids

    async def _send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
    ) -> None:
        """Send a message via Telegram Bot API."""
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            response = await self.http_client.post(url, json=payload)
            if response.status_code != 200:
                logger.error(f"Failed to send message: {response.text}")
                # If MarkdownV2 failed, retry without parse_mode
                if parse_mode and "can't parse" in response.text.lower():
                    logger.info("Retrying without parse_mode")
                    await self._send_message(chat_id, text, parse_mode=None)
        except Exception as e:
            logger.exception(f"Error sending message: {e}")

    async def _send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        """Send a chat action (typing indicator) via Telegram Bot API."""
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendChatAction"
        payload = {
            "chat_id": chat_id,
            "action": action,
        }

        try:
            await self.http_client.post(url, json=payload)
        except Exception as e:
            logger.debug(f"Failed to send chat action: {e}")


def create_app(settings: Settings) -> FastAPI:
    """Create and configure the FastAPI application."""
    handler: WebhookHandler | None = None
    heartbeat_scheduler: HeartbeatScheduler | None = None
    heartbeat_executor: HeartbeatExecutor | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal handler, heartbeat_scheduler, heartbeat_executor
        # Startup
        executor = create_executor(
            working_dir=settings.second_brain_path,
            memory_path=settings.herald_memory_path,
        )

        # Set up heartbeat components
        heartbeat_config = settings.get_heartbeat_config()
        heartbeat_delivery: HeartbeatDelivery | None = None

        if heartbeat_config.enabled:
            # Create a wrapper for send_message that matches the callback signature
            async def send_message_wrapper(chat_id: int, text: str) -> None:
                if handler:
                    await handler._send_message(chat_id, text)

            heartbeat_delivery = HeartbeatDelivery(
                send_message=send_message_wrapper,
                target=heartbeat_config.target,
            )

            # Share the same executor so heartbeat joins the regular conversation
            heartbeat_executor = HeartbeatExecutor(
                config=heartbeat_config,
                working_dir=settings.second_brain_path,
                heartbeat_file=settings.heartbeat_file_path,
                claude_executor=executor,
            )

            heartbeat_scheduler = HeartbeatScheduler(
                config=heartbeat_config,
                executor=heartbeat_executor,
                on_alert=heartbeat_delivery.deliver,
                get_target_chat=heartbeat_delivery.get_target_chat,
            )

        # Create webhook handler with activity tracking
        handler = WebhookHandler(
            settings,
            executor,
            on_activity=heartbeat_delivery.record_activity if heartbeat_delivery else None,
        )
        await handler.start()

        # Start heartbeat scheduler after handler is ready
        if heartbeat_scheduler:
            heartbeat_scheduler.start()
            logger.info(f"Heartbeat scheduler started (interval: {heartbeat_config.interval})")

        logger.info("Herald started successfully")
        yield
        # Shutdown
        if heartbeat_scheduler:
            await heartbeat_scheduler.stop()
            logger.info("Heartbeat scheduler stopped")
        if heartbeat_executor:
            await heartbeat_executor.shutdown()
        if handler:
            await handler.stop()
        logger.info("Herald stopped")

    app = FastAPI(
        title="Herald",
        description="Telegram Gateway to Claude Code",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "herald"}

    @app.post(settings.webhook_path)
    async def webhook(request: Request):
        """Handle incoming Telegram webhook updates."""
        if handler is None:
            raise HTTPException(status_code=503, detail="Service not ready")

        try:
            data = await request.json()
            update = TelegramUpdate(**data)
            # Process in background - return immediately to prevent Telegram retries
            asyncio.create_task(handler.handle_update(update))
            return {"ok": True}
        except Exception as e:
            logger.exception(f"Error processing webhook: {e}")
            # Return 200 anyway to prevent Telegram from retrying
            return {"ok": False, "error": str(e)}

    return app
