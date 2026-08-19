from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Dependency used by routes that schedule background work — a background
    task outlives the request session, so it gets the factory instead. Tests
    override this to point background tasks at the test database."""
    return async_session_factory
