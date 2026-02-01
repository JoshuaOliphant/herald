# ABOUTME: FastAPI webhook handler for Telegram updates
# ABOUTME: Receives messages, validates users, and routes to Claude Code

import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from .config import Settings
from .executor import ClaudeExecutor, create_executor
from .formatter import format_error, format_for_telegram

logger = logging.getLogger(__name__)


class TelegramUpdate(BaseModel):
    """Telegram webhook update payload."""

    update_id: int
    message: dict[str, Any] | None = None
    edited_message: dict[str, Any] | None = None


class WebhookHandler:
    """Handles incoming Telegram webhook updates."""

    def __init__(self, settings: Settings, executor: ClaudeExecutor):
        self.settings = settings
        self.executor = executor
        self._http_client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Initialize async resources."""
        self._http_client = httpx.AsyncClient(timeout=30.0)

    async def stop(self) -> None:
        """Clean up async resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            raise RuntimeError("WebhookHandler not started")
        return self._http_client

    async def handle_update(self, update: TelegramUpdate) -> None:
        """Process an incoming Telegram update."""
        # Get the message (could be new or edited)
        message = update.message or update.edited_message
        if not message:
            logger.debug(f"Update {update.update_id} has no message, ignoring")
            return

        # Extract sender info
        from_user = message.get("from", {})
        user_id = from_user.get("id")
        username = from_user.get("username", "unknown")
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")

        if not text:
            logger.debug(f"Message from {username} has no text, ignoring")
            return

        # Security: Check if user is allowed
        if not self._is_user_allowed(user_id):
            logger.warning(f"Unauthorized user {user_id} ({username}) attempted access")
            await self._send_message(
                chat_id,
                "⛔ Unauthorized. This bot is private.",
            )
            return

        logger.info(f"Processing message from {username} ({user_id}): {text[:50]}...")

        # Send typing indicator
        await self._send_chat_action(chat_id, "typing")

        # Execute through Claude Code
        result = await self.executor.execute(text)

        if result.success:
            # Format and send response
            messages = format_for_telegram(result.output)
            for msg in messages:
                await self._send_message(chat_id, msg.text, parse_mode=msg.parse_mode)
        else:
            # Send error message
            error_msg = format_error(result.error or "Unknown error")
            await self._send_message(chat_id, error_msg.text, parse_mode=error_msg.parse_mode)

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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal handler
        # Startup
        executor = create_executor(
            claude_path=settings.claude_code_path,
            working_dir=settings.second_brain_path,
            timeout=settings.command_timeout,
        )
        handler = WebhookHandler(settings, executor)
        await handler.start()
        logger.info("Herald started successfully")
        yield
        # Shutdown
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
            # Process in background to return quickly to Telegram
            await handler.handle_update(update)
            return {"ok": True}
        except Exception as e:
            logger.exception(f"Error processing webhook: {e}")
            # Return 200 anyway to prevent Telegram from retrying
            return {"ok": False, "error": str(e)}

    return app
