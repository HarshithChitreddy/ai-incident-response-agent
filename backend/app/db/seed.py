"""Seed the database with historical incidents from data/historical_incidents.csv.

Idempotent — skips if rows already exist. Run:

    python -m app.db.seed                          # local venv
    docker compose exec backend python -m app.db.seed
"""

import asyncio
import csv

from sqlalchemy import func, select

from app.config import get_settings
from app.db.session import async_session_factory, engine
from app.models import Base, HistoricalIncident


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    csv_path = get_settings().data_dir / "historical_incidents.csv"

    async with async_session_factory() as session:
        existing = await session.scalar(select(func.count()).select_from(HistoricalIncident))
        if existing:
            print(f"historical_incidents already has {existing} rows — skipping seed")
            return

        with csv_path.open(newline="") as f:
            rows = [
                HistoricalIncident(
                    service=r["service"],
                    alertname=r["alertname"],
                    severity=r["severity"],
                    error_rate_pct=float(r["error_rate_pct"]),
                    latency_p95_ms=float(r["latency_p95_ms"]),
                    request_rate_rps=float(r["request_rate_rps"]),
                    cpu_pct=float(r["cpu_pct"]),
                    memory_pct=float(r["memory_pct"]),
                    deploy_within_hour=r["deploy_within_hour"] == "1",
                    root_cause=r["root_cause"],
                    time_to_resolve_min=int(r["time_to_resolve_min"]),
                    summary=r["summary"],
                )
                for r in csv.DictReader(f)
            ]

        session.add_all(rows)
        await session.commit()
        print(f"Seeded {len(rows)} historical incidents from {csv_path}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
