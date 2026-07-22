from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    llm_api_key: str
    llm_base_url: str = "https://api.anthropic.com/v1"
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
