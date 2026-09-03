from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    GROQ_API_KEY: SecretStr
    # llama-3.3-70b-versatile was retired from Groq's catalog late Q3 2026;
    # gpt-oss-120b is the current in-tier replacement (131k ctx, comparable
    # capability). Override via env if a smaller/faster model works better
    # for your workload — e.g. openai/gpt-oss-20b for bulk classification.
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    ADZUNA_APP_ID: str = ""
    ADZUNA_APP_KEY: SecretStr = SecretStr("")
    ADZUNA_COUNTRY: str = "us"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
