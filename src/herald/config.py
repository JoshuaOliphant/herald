# ABOUTME: Configuration management for Herald using pydantic-settings
# ABOUTME: Loads settings from environment variables and .env files

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Paths
    second_brain_path: Path = (
        Path.home() / "Library/CloudStorage/Dropbox/python_workspace/second_brain"
    )
    memory_path: Path | None = None  # Relative to second_brain_path if set

    @property
    def herald_memory_path(self) -> Path:
        """Path to Herald's memory files."""
        if self.memory_path:
            return self.second_brain_path / self.memory_path
        return self.second_brain_path / "areas" / "herald"

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
        # This will be set externally based on Tailscale Funnel URL
        return f"https://your-mac.ts.net{self.webhook_path}"

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


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
