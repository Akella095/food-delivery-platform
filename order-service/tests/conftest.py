import asyncio
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.database as database_module
from app import models  # noqa: F401  ensures models are registered on Base.metadata
from app.config import settings
from app.database import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def make_token(user_id: str, role: str) -> str:
    return jwt.encode({"sub": user_id, "role": role}, settings.secret_key, algorithm=settings.algorithm)


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_engine, monkeypatch):
    session_maker = async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)
    database_module.AsyncSessionLocal = session_maker

    monkeypatch.setattr("app.routers.restaurants.cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.restaurants.cache_set", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.restaurants.cache_delete", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.orders.publish_event", AsyncMock())

    from app.database import get_db
    from app.main import app

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
