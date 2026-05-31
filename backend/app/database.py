from collections.abc import AsyncGenerator

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Settings(BaseSettings):
    database_url: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

# asyncpg driver requires postgresql+asyncpg:// scheme
_async_url = settings.database_url.replace(
    "postgresql://", "postgresql+asyncpg://", 1
)

engine = create_async_engine(_async_url, echo=False, pool_pre_ping=True)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
