from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
_BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_ROOT_ENV), str(_BACKEND_ENV), ".env"),
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Budgets (investigation hard stops)
    max_llm_rounds: int = Field(default=8, ge=0, le=20)
    max_tool_calls: int = Field(default=12, ge=0, le=30)
    max_wall_seconds: float = Field(default=120, gt=0, le=300)
    provider_timeout_seconds: float = Field(default=20, gt=0, le=60)
    max_output_tokens: int = Field(default=2048, ge=256, le=4096)
    database_path: str = "incident-zero.sqlite3"

    # Public demo protection
    allow_public_live: bool = False
    live_daily_cap: int = Field(default=5, ge=0, le=100)
    rate_limit_per_minute: int = Field(default=10, gt=0, le=100)
    demo_secret: str = ""

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
