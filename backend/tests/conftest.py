"""Test harness: in-memory SQLite via aiosqlite, swapped in through FastAPI's
dependency overrides. Both request sessions (get_db) and background-task
sessions (get_session_factory) point at the test database, so webhook-triggered
agent runs execute end-to-end in tests. MOCK_LLM is forced on before the app
imports so no test can ever hit the real API."""

import os
import tempfile
import threading

os.environ["MOCK_LLM"] = "true"
# empty MODEL_DIR: tool tests exercise the deterministic heuristic fallback even
# if a real model has been trained into backend/app/ml/artifacts on this machine
os.environ["MODEL_DIR"] = tempfile.mkdtemp(prefix="ira-test-no-models-")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db.session import get_db, get_session_factory
from app.main import app
from app.models import Base

get_settings.cache_clear()

# ---------------------------------------------------------------------------
# Shared runbook vector index: built lazily (first test that actually touches
# retrieval pays the embedding-model load), at most once per session, in a tmp
# dir so tests never write to the repo's chroma_data/.
# ---------------------------------------------------------------------------

_index_cache: dict = {}
_index_lock = threading.Lock()


def _get_or_build_index(persist_dir):
    from app.rag.store import RunbookIndex

    with _index_lock:
        if "index" not in _index_cache:
            index = RunbookIndex(
                persist_dir=persist_dir,
                runbooks_dir=get_settings().data_dir / "runbooks",
            )
            index.ensure_indexed()
            _index_cache["index"] = index
        return _index_cache["index"]


@pytest.fixture(scope="session")
def _chroma_tmp(tmp_path_factory):
    return tmp_path_factory.mktemp("chroma-test")


@pytest.fixture(scope="session")
def runbook_index(_chroma_tmp):
    return _get_or_build_index(_chroma_tmp)


@pytest.fixture(autouse=True)
def _route_runbook_index(monkeypatch, _chroma_tmp):
    """Point the process-wide index accessor at the test index (lazily)."""
    monkeypatch.setattr(
        "app.rag.store.get_runbook_index", lambda: _get_or_build_index(_chroma_tmp)
    )


@pytest.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def client(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
