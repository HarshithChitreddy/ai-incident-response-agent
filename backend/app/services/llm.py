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


class LLMClient(Protocol):
    async def create_message(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16000,
    ) -> LLMResponse: ...


# --------------------------------------------------------------------------- #
# Mock implementation
# --------------------------------------------------------------------------- #


class MockLLMClient:
    def __init__(self, model: str = "mock-claude") -> None:
        self.model = model
        self._counter = 0

    async def create_message(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16000,
    ) -> LLMResponse:
        tools = tools or []
        called = self._called_tool_names(messages)
        next_tool = next((t for t in tools if t["name"] not in called), None)

        if next_tool is not None:
            self._counter += 1
            block = {
                "type": "tool_use",
                "id": f"toolu_mock_{self._counter:04d}",
                "name": next_tool["name"],
                "input": self._fake_input(next_tool.get("input_schema", {}), messages),
            }
            return LLMResponse(
                content=[block],
                stop_reason="tool_use",
                model=self.model,
                usage={"input_tokens": 1200, "output_tokens": 60},
            )

        return LLMResponse(
            content=[{"type": "text", "text": self._final_text(system, messages)}],
            stop_reason="end_turn",
            model=self.model,
            usage={"input_tokens": 4800, "output_tokens": 420},
        )

    @staticmethod
    def _called_tool_names(messages: list[Message]) -> set[str]:
        called: set[str] = set()
        for msg in messages:
            content = msg.get("content")
            if msg.get("role") == "assistant" and isinstance(content, list):
                called.update(
                    b["name"] for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
                )
        return called

    def _fake_input(self, schema: dict[str, Any], messages: list[Message]) -> dict[str, Any]:
        props: dict[str, Any] = schema.get("properties", {})
        required = set(schema.get("required", list(props)))
        out: dict[str, Any] = {}
        for name, spec in props.items():
            if name in required:
                out[name] = self._fake_value(name, spec, messages)
        return out

    def _fake_value(self, name: str, spec: dict[str, Any], messages: list[Message]) -> Any:
        if "enum" in spec:
            return spec["enum"][0]
        match spec.get("type"):
            case "string":
                return f"mock-{name}"
            case "integer":
                return 5
            case "number":
                return 1.0
            case "boolean":
                return True
            case "array":
                return []
            case _:
                return {}
