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

    def _final_text(self, system: str, messages: list[Message]) -> str:
        service = "checkout-service"
        blob = (system + " " + json.dumps(messages, default=str)).lower()

        if "postmortem" in blob:
            return _POSTMORTEM_TEMPLATE.format(service=service)
        if "slack" in blob:
            return _SLACK_BRIEF_TEMPLATE.format(service=service)

        top_sha = "9f2c41ab7e03"
        runner_up = "4b8e19d3c5f7"

        analysis = {
            "root_cause": (
                f"Commit {top_sha} is the most likely cause: it deployed shortly before the "
                f"regression on {service} began, touches the failing code path, and carries "
                f"risky change markers that match the observed symptoms."
            ),
            "why_it_might_be_wrong": (
                "An upstream dependency degraded in the same window — if it was failing "
                "independently, the top-ranked commit is an aggravator rather than the root "
                "cause, and rolling back alone will not fully recover."
            ),
            "competing_candidates": [
                {
                    "commit": top_sha,
                    "reason": "Deployed closest to onset; touches the failing call path.",
                    "likelihood": "high",
                },
                {
                    "commit": runner_up,
                    "reason": "Same service and window, but the diff looks behavior-neutral.",
                    "likelihood": "low",
                },
            ],
            "confidence": 0.72,
            "severity": "critical",
            "user_impact": (
                f"~12% of {service} confirmations failing (~19 orders/min at current traffic); "
                "affected users see a payment error and may retry or abandon checkout."
            ),
            "recommended_runbook_steps": [
                "Roll back to the previous release (see deploy-rollback runbook).",
                "Disable the no-backoff retry wrapper before any forward fix.",
                "Verify error rate returns under 1% for 15 consecutive minutes.",
            ],
        }
        return json.dumps(analysis, indent=2)


_SLACK_BRIEF_TEMPLATE = """\
:rotating_light: *[CRITICAL] HighErrorRate — {service}*

*Status:* Investigating | *Started:* 14:02 UTC | *Owner:* payments on-call

*What we know:* Error rate on {service} is at 12.4% (threshold 2%), driven by payment \
authorization timeouts on POST /api/checkout/confirm.

*Likely cause (confidence 72%):* Commit `9f2c41ab7e03` (13:12 UTC) cut the payment gateway \
timeout to 2s below upstream p50 and added no-backoff retries — a retry storm is amplifying load.

*Impact:* ~19 failed orders/min. *Next step:* rolling back to previous release.
"""

_POSTMORTEM_TEMPLATE = """\
# Postmortem: HighErrorRate on {service}

## Summary
Between 13:35 and 14:47 UTC, {service} returned 5xx errors on up to 12.4% of checkout \
confirmations after a deploy tightened the payment gateway timeout below the upstream's \
actual latency and added retries without backoff.

## Timeline (UTC)
- 13:12 — Release 2026-07-07.2 deployed (commit 9f2c41ab7e03)
- 13:35 — Error rate begins climbing past 2%
- 14:02 — HighErrorRate alert fires; incident opened
- 14:31 — Rollback initiated
- 14:47 — Error rate back under 1%; incident resolved

## Root Cause
The 2s deadline sat below the gateway's ~2.1s p50, so most authorization calls timed out; \
3-attempt retries without backoff tripled request volume and triggered upstream throttling.

## Impact
~19 failed orders/min for 72 minutes; affected users saw payment errors at confirmation.

## Resolution
Rolled back to the prior release, restoring the 5s timeout and removing the retry wrapper.

## Action Items
1. Add a canary stage gating deploys on checkout error rate.
2. Require backoff + jitter on all retry wrappers (lint rule).
3. Alert when a client deadline is configured below upstream p95.

## Prevention
Timeout changes must reference measured upstream latency percentiles in the PR description.
"""
