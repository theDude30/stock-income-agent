from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    postgres_user: str = Field(...)
    postgres_password: str = Field(...)
    postgres_db: str = Field(...)
    postgres_host: str = Field(...)
    postgres_port: int = Field(...)

    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    anthropic_api_key: str = Field(default="")
    llm_model: str = Field(default="claude-sonnet-4-6")

    # Annualized 1-month Treasury yield (%) used as the performance baseline
    # (design 5b §2: config constant; optionally ^IRX-refreshed later).
    treasury_1m_yield_pct: float = Field(default=4.2)

    notifications_enabled: bool = Field(default=False)
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from: str = Field(default="")
    notify_email_to: str = Field(default="")

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.notify_email_to)


def get_settings() -> Settings:
    return Settings()
