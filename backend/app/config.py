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

    # LLM (used from Phase 2 onward)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"
    # Safe-by-default: real API calls happen only with an explicit MOCK_LLM=false
    mock_llm: bool = True

    # Static sample data acting as the "external systems" (git host, log store, metrics store)
    data_dir: Path = _REPO_ROOT / "data"

    # RAG persistence (Phase 3)
    chroma_persist_dir: Path = _REPO_ROOT / "chroma_data"

    # Trained ML artifacts (Phase 4); env var MODEL_DIR
    model_dir: Path = _REPO_ROOT / "backend" / "app" / "ml" / "artifacts"

    # Slack-style notifications (Phase 5). Empty means "mock mode".
    slack_webhook_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
