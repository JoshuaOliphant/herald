# ABOUTME: Configuration management for Herald using pydantic-settings
# ABOUTME: Loads settings from environment variables and .env files

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from herald.heartbeat.config import HeartbeatConfig


class Settings(BaseSettings):
    """Herald configuration settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Telegram settings
    telegram_bot_token: str
    allowed_telegram_user_ids: list[int] = []

    # Paths (override with SECOND_BRAIN_PATH env var)
    second_brain_path: Path = Path.home() / "second-brain"
    memory_path: Path | None = None  # Relative to second_brain_path if set
    heartbeat_file: Path | None = None  # Path to HEARTBEAT.md file

    # Claude model settings
    claude_model: str | None = None  # Override default model (e.g., "claude-opus-4-6")
    agent_teams: bool = False  # Enable experimental agent teams feature

    # Heartbeat settings
    heartbeat_enabled: bool = False
    heartbeat_every: str = "30m"
    heartbeat_prompt: str | None = None
    heartbeat_prompt_file: Path | None = None  # Load prompt from file (overrides heartbeat_prompt)
    heartbeat_target: str = "last"
    heartbeat_active_hours: str | None = None
    heartbeat_ack_max_chars: int = 300
    heartbeat_timezone: str = "UTC"
    heartbeat_model: str | None = None

    @property
    def herald_memory_path(self) -> Path:
        """Path to Herald's memory files."""
        if self.memory_path:
            return self.second_brain_path / self.memory_path
        return self.second_brain_path / "areas" / "herald"

    @property
    def chat_history_path(self) -> Path:
        """Path to chat history storage."""
        return self.second_brain_path / "areas" / "herald" / "chat-history"

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8080
    webhook_path: str = "/webhook"

    # Execution settings
    command_timeout: int = 300  # 5 minutes default
    max_response_length: int = 4096  # Telegram message limit

    @field_validator("allowed_telegram_user_ids", mode="before")
    @classmethod
    def parse_user_ids(cls, v: str | int | list[int]) -> list[int]:
        """Parse comma-separated user IDs from environment string."""
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(uid.strip()) for uid in v.split(",") if uid.strip()]
        return v

    @property
    def webhook_url(self) -> str:
        """Full webhook URL for Telegram registration."""
        # Override with your actual domain (e.g., Tailscale Funnel, ngrok, etc.)
        return f"https://localhost:{self.port}{self.webhook_path}"

    def validate_ready(self) -> list[str]:
        """Check if all required settings are configured. Returns list of errors."""
        errors = []

        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is required")

        if not self.allowed_telegram_user_ids:
            errors.append("ALLOWED_TELEGRAM_USER_IDS is required (comma-separated user IDs)")

        if not self.second_brain_path.exists():
            errors.append(f"SECOND_BRAIN_PATH does not exist: {self.second_brain_path}")

        return errors

    def get_heartbeat_config(self) -> HeartbeatConfig:
        """Build HeartbeatConfig from environment settings."""
        import logging
        logger = logging.getLogger(__name__)

        # Load prompt from file if specified, otherwise use inline prompt
        prompt = self.heartbeat_prompt
        if self.heartbeat_prompt_file:
            if self.heartbeat_prompt_file.exists():
                prompt = self.heartbeat_prompt_file.read_text().strip()
                logger.info(f"Loaded heartbeat prompt from {self.heartbeat_prompt_file} ({len(prompt)} chars)")
            else:
                logger.warning(f"Heartbeat prompt file not found: {self.heartbeat_prompt_file}")

        logger.info(f"Heartbeat target: {self.heartbeat_target}")

        return HeartbeatConfig(
            enabled=self.heartbeat_enabled,
            every=self.heartbeat_every,
            prompt=prompt,
            target=self.heartbeat_target,
            active_hours=self.heartbeat_active_hours,
            ack_max_chars=self.heartbeat_ack_max_chars,
            timezone=self.heartbeat_timezone,
            model=self.heartbeat_model,
        )

    @property
    def heartbeat_file_path(self) -> Path | None:
        """Get the HEARTBEAT.md file path."""
        if self.heartbeat_file:
            return self.heartbeat_file
        # Default to HEARTBEAT.md in second_brain_path
        default_path = self.second_brain_path / "HEARTBEAT.md"
        return default_path if default_path.exists() else None


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
