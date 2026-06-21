"""Bot configuration loaded from environment / .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass

# Try to auto-load a .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class BotConfig:
    telegram_token: str
    allowed_user_id: int
    ollama_base_url: str
    ollama_model: str
    workspace: str

    @classmethod
    def from_env(cls) -> "BotConfig":
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        user_id_raw = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "").strip()

        if not token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is not set.\n"
                "Please set it in your environment or .env file:\n"
                "  export TELEGRAM_BOT_TOKEN='your-bot-token-here'"
            )
        if not user_id_raw:
            raise ValueError(
                "TELEGRAM_ALLOWED_USER_ID is not set.\n"
                "Please set it in your environment or .env file:\n"
                "  export TELEGRAM_ALLOWED_USER_ID='your-telegram-user-id'"
            )

        try:
            user_id = int(user_id_raw)
        except ValueError as exc:
            raise ValueError(
                f"TELEGRAM_ALLOWED_USER_ID must be an integer, got: {user_id_raw}"
            ) from exc

        return cls(
            telegram_token=token,
            allowed_user_id=user_id,
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").strip(),
            ollama_model=os.environ.get("OLLAMA_MODEL", "gemma4:e2b").strip(),
            workspace=os.environ.get("SECONDBRAIN_WORKSPACE", ".").strip(),
        )
