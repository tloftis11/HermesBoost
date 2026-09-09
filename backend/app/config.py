from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase / Postgres
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""
    DATABASE_URL: str = "sqlite+aiosqlite:///./_dev.db"

    # Redis / Celery
    UPSTASH_REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_TASK_ALWAYS_EAGER: bool = False

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    DEFAULT_LLM_MODEL: str = "claude-opus-5"

    # Behavior toggles
    STORAGE_BACKEND: str = "local"  # supabase | local
    LLM_PROVIDER_MODE: str = "fake"  # live | fake
    AUTH_MODE: str = "dev"  # supabase | dev

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # Local storage (only used when STORAGE_BACKEND == "local")
    LOCAL_STORAGE_DIR: str = "./_dev_storage"

    # AutoML
    FLAML_TIME_BUDGET_SECONDS: int = 60


settings = Settings()
