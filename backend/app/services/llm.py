"""LLM client seam: one interface, two implementations.

- AnthropicLLMClient: real calls to the Claude Messages API.
- MockLLMClient: deterministic, token-free stand-in (MOCK_LLM=true, the default).

Both return `LLMResponse` carrying raw wire-format content blocks. The agent loop
appends `response.as_assistant_message()` verbatim, which keeps thinking blocks
intact for replay on the real API and makes the mock indistinguishable in shape.

The mock drives a realistic triage loop: given tools, it calls each one exactly
once (in the order provided) with schema-valid fake inputs, then emits a final
analysis. Prompts mentioning "postmortem" or "slack" get matching canned text,
so every Phase 2 node has a plausible output to parse.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import Settings, get_settings

# Anthropic Messages API wire format: {"role": ..., "content": str | [blocks]}
Message = dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMResponse:
    content: list[dict[str, Any]]
    stop_reason: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(
            b.get("text", "") for b in self.content if b.get("type") == "text"
        ).strip()

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [
            ToolCall(id=b["id"], name=b["name"], input=b.get("input", {}))
            for b in self.content
            if b.get("type") == "tool_use"
        ]

    def as_assistant_message(self) -> Message:
        return {"role": "assistant", "content": self.content}
