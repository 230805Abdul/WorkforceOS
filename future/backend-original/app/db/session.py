from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

_engine_kwargs: dict = {"pool_pre_ping": True, "echo": not settings.is_production}
if settings.DATABASE_URL.startswith("postgresql"):
    # Pool sizing only applies to real connection-pooled backends (Postgres via
    # asyncpg). SQLite (used in the test suite) uses NullPool and rejects these.
    _engine_kwargs.update(pool_size=10, max_overflow=20)

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
