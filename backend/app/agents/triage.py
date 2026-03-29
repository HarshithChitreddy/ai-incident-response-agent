"""LangGraph triage workflow.

Two nodes in a ReAct loop — `agent` (LLM decides) and `tools` (we execute) —
with a conditional edge that exits when the model stops requesting tools or
the iteration budget runs out. Nodes close over a TriageContext instead of
stuffing live objects (db session, llm client) into graph state, which keeps
the state a plain serializable dict.

The LLM node talks to our LLMClient seam directly, not a LangChain chat model:
that's what makes MOCK_LLM work identically here.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.trace import AgentTracer, jsonable
from app.models import Incident
from app.services.llm import LLMClient
from app.tools.base import ToolContext
from app.tools.registry import anthropic_tool_defs, dispatch

MAX_ITERATIONS = 12


class TriageState(TypedDict):
    messages: list[dict[str, Any]]
    iterations: int
    done: bool
    final_text: str


@dataclass
class TriageContext:
    tool_ctx: ToolContext
    llm: LLMClient
    tracer: AgentTracer
