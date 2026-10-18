import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class CodeGateSettings(BaseSettings):
    # Default to sqlite for local dev and testing
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///./codegate.db")
    
    # Static Analysis Settings
    STATIC_ANALYSIS_ENABLED: bool = True
    ANALYZER_TIMEOUT_SECONDS: int = 300
    RUFF_ENABLED: bool = True
    BANDIT_ENABLED: bool = True
    RADON_ENABLED: bool = True
    ALLOW_LOCAL_TEST_EXECUTOR: bool = False
    
    # Auth Settings
    GITHUB_OAUTH_CLIENT_ID: str | None = None
    GITHUB_OAUTH_CLIENT_SECRET: str | None = None
    GITHUB_OAUTH_CALLBACK_URL: str = "http://127.0.0.1:8000/api/v1/auth/github/callback"
    CODEGATE_SESSION_TTL_SECONDS: int = 604800  # 7 days
    CODEGATE_COOKIE_SECURE: bool = False
    
    # GitHub App Settings
    GITHUB_APP_ID: str | None = None
    GITHUB_APP_SLUG: str | None = None
    GITHUB_APP_PRIVATE_KEY_PATH: str | None = None
    GITHUB_WEBHOOK_SECRET: str | None = None
    GITHUB_APP_SETUP_URL: str = "http://127.0.0.1:8000/api/v1/integrations/github/setup"
    CODEGATE_FRONTEND_URL: str = "http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = CodeGateSettings()
