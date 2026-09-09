import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.core.organizations as organizations_module
from app.db import Base
from app.dependencies import get_db
from app.main import create_app
from app.models.organization import Organization


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def default_org_id(test_engine) -> str:
    session_maker = async_sessionmaker(test_engine, expire_on_commit=False)
    org_id = str(uuid.uuid4())
    async with session_maker() as session:
        session.add(
            Organization(
                id=org_id,
                name="Test Org",
                slug="default",
                monthly_llm_budget_usd=20.00,
            )
        )
        await session.commit()
    # The org-id resolver caches in-process; each test gets a fresh in-memory
    # DB with a fresh org id, so the cache must be cleared between tests.
    organizations_module._default_org_id_cache = None
    return str(org_id)


@pytest_asyncio.fixture
async def db_session(test_engine, default_org_id):
    session_maker = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session, monkeypatch):
    # Router tests exercise the sync/async boundary (upload -> enqueue) but
    # not the worker pipeline itself -- that's covered by the full local
    # smoke test. Stub the enqueue call to a no-op recorder.
    monkeypatch.setattr("app.routers.datasets.profile_dataset.delay", lambda *a, **k: None)

    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
