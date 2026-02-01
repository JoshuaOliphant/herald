# ABOUTME: Herald entry point - starts the FastAPI server
# ABOUTME: Validates configuration and runs uvicorn

import logging
import sys

import uvicorn

from .config import get_settings
from .webhook import create_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for Herald."""
    logger.info("Starting Herald - Telegram Gateway to Claude Code")

    # Load and validate settings
    try:
        settings = get_settings()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        sys.exit(1)

    # Check for configuration errors
    errors = settings.validate_ready()
    if errors:
        logger.error("Configuration errors:")
        for error in errors:
            logger.error(f"  - {error}")
        sys.exit(1)

    logger.info(f"Second brain path: {settings.second_brain_path}")
    logger.info(f"Claude Code path: {settings.claude_code_path}")
    logger.info(f"Allowed users: {settings.allowed_telegram_user_ids}")
    logger.info(f"Webhook path: {settings.webhook_path}")

    # Create and run the app
    app = create_app(settings)

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
