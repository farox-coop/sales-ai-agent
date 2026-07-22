from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM via AI Gateway (endpoint OpenAI-compatible)
    llm_api_key: str  # gateway API key
    llm_base_url: str = "https://genway.farox.coop"  # Farox AI gateway
    llm_model: str = "claude-sonnet-4-20250514"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.7

    # Database
    sqlalchemy_async_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/lead_magnet"
    database_sync_url: str = "postgresql://postgres:postgres@postgres:5432/lead_magnet"

    # Chainlit
    chainlit_port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
