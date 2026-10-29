from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM via AI Gateway (endpoint OpenAI-compatible)
    llm_api_key: str  # gateway API key
    llm_base_url: str = "https://your-llm-gateway.example.com"  # LLM AI gateway
    llm_model: str = "claude-sonnet-4-20250514"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.7

    # Database
    sqlalchemy_async_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/lead_magnet"
    database_sync_url: str = "postgresql+psycopg2://postgres:postgres@postgres:5432/lead_magnet"

    # Chainlit
    chainlit_port: int = 8000

    # Modo mantenimiento: si está activo, el chat rechaza toda interacción.
    maintenance_mode: bool = False
    maintenance_message: str = (
        "El servicio está en mantenimiento. "
        "Volvé a intentar en unos minutos, gracias."
    )

    @field_validator("database_sync_url")
    @classmethod
    def _force_psycopg2_driver(cls, v: str) -> str:
        # SQLAlchemy 2.1 usa psycopg v3 para "postgresql://", pero el proyecto
        # instala psycopg2-binary. Forzamos el driver explícito.
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg2://", 1)
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
