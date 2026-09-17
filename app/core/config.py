from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Distributed Document Search Service"
    database_url: str = "postgresql+asyncpg://search:search@localhost:5432/document_search"
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_per_minute: int = 100
    cache_ttl_seconds: int = 45
    index_stream: str = "index.document"
    index_group: str = "indexers"
    index_consumer: str = "worker-1"
    tenant_header: str = "X-Tenant-ID"


@lru_cache
def get_settings() -> Settings:
    return Settings()
