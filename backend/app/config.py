from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
_BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_ROOT_ENV), str(_BACKEND_ENV), ".env"),
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Budgets (investigation hard stops)
    max_llm_rounds: int = 12
    max_tool_calls: int = 20
    max_wall_seconds: float = 120.0

    # Public demo protection
    allow_public_live: bool = False
    live_daily_cap: int = 5
    rate_limit_per_minute: int = 10
    demo_secret: str = ""

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
