from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "monitoramento-vencimentos"
    port: int = 10000
    log_level: str = "INFO"
    time_zone: str = "America/Fortaleza"
    database_url: str = "sqlite:///./monitoramento.db"
    manual_run_api_key: SecretStr = SecretStr("development-key")
    google_service_account_json: SecretStr | None = None
    google_service_account_json_base64: SecretStr | None = None
    mail_enabled: bool = False
    mail_host: str | None = None
    mail_port: int = 587
    mail_username: str | None = None
    mail_password: SecretStr | None = None
    mail_from: str | None = None
    mail_use_tls: bool = True
    mail_summary_to: str | None = None
    notify_employee: bool = False
    max_email_retries: int = 3
    google_api_max_retries: int = 3
    request_timeout_seconds: int = 30
    enable_docs: bool = False
    cors_allowed_origins: str = "http://localhost:5173,http://localhost:4173"

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        return value.replace("postgres://", "postgresql+psycopg://", 1).replace(
            "postgresql://", "postgresql+psycopg://", 1
        )

    @property
    def production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
