import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun, TraceStep


def jsonable(obj: Any) -> Any:
    """Force anything into JSON-serializable form for trace storage."""
    return json.loads(json.dumps(obj, default=str))
