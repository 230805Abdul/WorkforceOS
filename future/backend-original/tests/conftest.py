import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User, UserRole

test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=None)
TestSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    # slowapi's in-memory storage is process-wide, so without this, login/register
    # calls accumulate across tests and later tests get spuriously 429'd.
    from app.services.rate_limit import limiter

    limiter.reset()
    yield


@pytest_asyncio.fixture(autouse=True)
async def reset_redis_pool():
    # app.services.cache keeps one module-level connection pool for the life of
    # the process. pytest-asyncio gives each test its own event loop, so a pool
    # opened in test N's loop is dead by test N+1 ("Event loop is closed").
    # Production doesn't hit this — the app has exactly one event loop for its
    # whole lifetime — but tests need the pool rebuilt fresh each time.
    import app.services.cache as cache_module

    cache_module._redis_pool = None
    yield
    if cache_module._redis_pool is not None:
        await cache_module._redis_pool.aclose()
        cache_module._redis_pool = None


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def seed_user() -> dict:
    """Creates one user of each role directly in the DB and returns their plaintext creds."""
    async with TestSessionLocal() as session:
        users = {}
        for role, email in [
            (UserRole.ADMIN, "admin@test.com"),
            (UserRole.RECRUITER, "recruiter@test.com"),
            (UserRole.CANDIDATE, "candidate@test.com"),
        ]:
            user = User(email=email, hashed_password=hash_password("Password123!"), full_name=role.value, role=role)
            session.add(user)
            users[role.value] = {"email": email, "password": "Password123!"}
        await session.commit()
        return users
