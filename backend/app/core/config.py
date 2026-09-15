from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

# Walk up from app/core/ → app/ → backend/ → project root
# .env may live in backend/ or the project root — check both
_HERE = Path(__file__).resolve().parent          # app/core
_BACKEND = _HERE.parent.parent                   # backend/
_ROOT    = _BACKEND.parent                       # project root
_ENV_FILE = _BACKEND / ".env" if (_BACKEND / ".env").exists() else _ROOT / ".env"


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "emailagent"
    postgres_user: str = "postgres"
    postgres_password: str = "password"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5-coder:7b"
    embedding_model: str = "nomic-embed-text"

    # Embedding backend: "sentence_transformers" or "ollama"
    embedding_backend: str = "sentence_transformers"
    sentence_transformer_model: str = "all-MiniLM-L6-v2"
    embedding_dimensions: int = 384

    # Gmail OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/gmail/oauth/callback"
    fernet_secret_key: str = ""

    # App
    secret_key: str = "changeme"
    frontend_url: str = "http://localhost:5173"
    environment: str = "development"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = str(_ENV_FILE)
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
