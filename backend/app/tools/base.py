from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings

if TYPE_CHECKING:
    from app.rag.store import RunbookIndex


@dataclass
class ToolContext:
    """Everything a tool may need at execution time. Tools stay plain async
    functions of (ctx, **model_supplied_args) so they're trivially unit-testable.

    `runbook_index` is injectable for tests; when None, tools use the shared
    process-wide index from app.rag.store."""

    db: AsyncSession
    settings: Settings
    runbook_index: RunbookIndex | None = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]

    def to_anthropic(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
