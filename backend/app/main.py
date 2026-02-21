from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import alerts
from app.config import get_settings
from app.db.session import engine
from app.models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # create_all keeps the demo self-bootstrapping; introduce Alembic only if
    # the schema starts churning after Phase 2
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)

app.include_router(alerts.router, prefix="/api/v1")


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
