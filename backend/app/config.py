from __future__ import annotations
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://passly:passly@db:5432/passly"

    # AI
    use_vertex_ai: bool = False
    gemini_api_key: str = ""
    gcp_project_id: str = ""
    gcp_region: str = "asia-northeast3"

    # Storage
    storage_type: str = "local"  # local | gcs
    upload_dir: str = "./uploads"
    gcs_bucket_name: str = ""

    # Security
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 24  # 24시간

    # App
    env: str = "development"
    log_level: str = "info"
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def async_database_url(self) -> str:
        return self.database_url.replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
