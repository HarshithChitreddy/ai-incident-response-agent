from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All runtime configuration. Values come from the environment (or .env);
    defaults are tuned for local development against docker-compose."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Incident Response Agent"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://incident:incident@localhost:5432/incident_response"


@lru_cache
def get_settings() -> Settings:
    return Settings()
