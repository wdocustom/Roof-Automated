"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration. All values read from environment / .env file."""

    # -- App --
    environment: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000"]

    # -- Database --
    database_url: str = "postgresql+asyncpg://roof_user:password@localhost:5432/roof_automated"
    database_sync_url: str = "postgresql://roof_user:password@localhost:5432/roof_automated"

    # -- Neon Auth --
    neon_auth_url: str = ""
    neon_auth_jwks_url: str = ""

    # -- Temporal --
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "roof-automated"
    temporal_task_queue: str = "roof-main"
    temporal_api_key: str | None = None
    temporal_tls_cert_path: str | None = None
    temporal_tls_key_path: str | None = None

    # -- Twilio --
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_messaging_service_sid: str = ""
    twilio_webhook_secret: str = ""

    # -- Stripe --
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # -- LLM --
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "roof-automated"

    # -- Gemma 4 / Self-hosted LLM --
    ollama_base_url: str = ""  # e.g. http://gpu-server:11434
    google_ai_studio_api_key: str = ""  # For Gemma 4 via Google AI Studio

    # -- Frontend --
    frontend_url: str = "https://roof-automated.vercel.app"

    # -- AWS S3 --
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_s3_bucket: str = "roof-automated-media"
    aws_region: str = "us-east-1"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}


settings = Settings()
