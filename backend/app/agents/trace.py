import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun, TraceStep


def jsonable(obj: Any) -> Any:
    """Force anything into JSON-serializable form for trace storage."""
    return json.loads(json.dumps(obj, default=str))


class AgentTracer:
    """Persists each agent step as it happens (committed per step, so a crashed
    run still leaves its partial trace behind for debugging)."""

    def __init__(self, db: AsyncSession, run: AgentRun) -> None:
        self._db = db
        self._run = run
        self._seq = 0

    async def record(
        self,
        step_type: str,
        name: str,
        step_input: Any,
        step_output: Any,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        self._seq += 1
        self._db.add(
            TraceStep(
                run_id=self._run.id,
                seq=self._seq,
                step_type=step_type,
                name=name,
                input=jsonable(step_input) if isinstance(step_input, dict) else {"value": jsonable(step_input)},
                output=jsonable(step_output) if isinstance(step_output, dict) else {"value": jsonable(step_output)},
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
        )
        await self._db.commit()
