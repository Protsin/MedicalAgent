"""Runtime configuration loaded from environment variables."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

DEFAULT_DB_NAME = "clinic_agent.db"


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    database_path: Path = Path(DEFAULT_DB_NAME)
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    request_timeout: float = 30.0
    max_message_chars: int = 4000

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        source = env if env is not None else os.environ.copy()
        raw_port = source.get("PORT", "8000")
        try:
            port = int(raw_port)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError as exc:
            raise ValueError("PORT must be an integer between 1 and 65535") from exc

        return cls(
            host=source.get("HOST", "127.0.0.1"),
            port=port,
            database_path=Path(source.get("CLINIC_AGENT_DB", DEFAULT_DB_NAME)),
            api_key=source.get("OPENAI_API_KEY", ""),
            base_url=source.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            model=source.get("CLINIC_AGENT_MODEL", "gpt-4o-mini"),
            request_timeout=float(source.get("CLINIC_AGENT_TIMEOUT", "30")),
            max_message_chars=int(source.get("CLINIC_AGENT_MAX_MESSAGE_CHARS", "4000")),
        )

    @property
    def llm_enabled(self) -> bool:
        return bool(self.api_key and self.model and self.base_url)
