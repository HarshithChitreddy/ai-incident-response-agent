"""Tests for the LLM client seam and the deterministic mock.

`run_tool_loop` below is deliberately the same loop Phase 2's agent will run:
call the model, append the assistant turn verbatim, execute tool calls, feed
tool_result blocks back, repeat until stop_reason != tool_use.
"""

import json

import pytest

from app.config import Settings
from app.services.llm import (
    AnthropicLLMClient,
    LLMResponse,
    MockLLMClient,
    ToolCall,
    get_llm_client,
)

TOOLS = [
    {
        "name": "get_recent_commits",
        "description": "List recent commits for a service.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "hours": {"type": "integer"},
            },
            "required": ["service"],
        },
    },
    {
        "name": "search_logs",
        "description": "Search application logs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "query": {"type": "string"},
                "level": {"type": "string", "enum": ["ERROR", "WARNING", "INFO"]},
            },
            "required": ["service", "query", "level"],
        },
    },
    {
        "name": "query_metrics",
        "description": "Fetch metrics for a service.",
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string"}},
            "required": ["service"],
        },
    },
]


async def run_tool_loop(
    client, tools, user_message: str, system: str = "You are an incident triage agent."
) -> tuple[LLMResponse, list[ToolCall]]:
    messages = [{"role": "user", "content": user_message}]
    transcript: list[ToolCall] = []

    for _ in range(20):
        resp = await client.create_message(system=system, messages=messages, tools=tools)
        messages.append(resp.as_assistant_message())
        if resp.stop_reason != "tool_use":
            return resp, transcript
        results = []
        for call in resp.tool_calls:
            transcript.append(call)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": f"fake result for {call.name}",
                }
            )
        messages.append({"role": "user", "content": results})

    pytest.fail("tool loop did not terminate")


def test_factory_defaults_to_mock():
    client = get_llm_client(Settings(_env_file=None))
    assert isinstance(client, MockLLMClient)


def test_factory_returns_real_client_only_when_explicitly_disabled():
    client = get_llm_client(Settings(_env_file=None, mock_llm=False, anthropic_api_key="test-key"))
    assert isinstance(client, AnthropicLLMClient)
    assert client.model == "claude-opus-4-8"


async def test_mock_calls_each_tool_once_then_analyzes():
    resp, transcript = await run_tool_loop(
        MockLLMClient(), TOOLS, "Investigate HighErrorRate on checkout-service"
    )

    assert [c.name for c in transcript] == [t["name"] for t in TOOLS]
    assert resp.stop_reason == "end_turn"

    analysis = json.loads(resp.text)
    assert "root_cause" in analysis
    assert "why_it_might_be_wrong" in analysis
    assert 0 <= analysis["confidence"] <= 1
    assert len(analysis["competing_candidates"]) >= 2


async def test_mock_tool_inputs_satisfy_the_schema():
    client = MockLLMClient()
    resp = await client.create_message(
        system="triage",
        messages=[{"role": "user", "content": "Investigate orders-service pool exhaustion"}],
        tools=TOOLS,
    )

    assert resp.stop_reason == "tool_use"
    [call] = resp.tool_calls
    assert call.name == "get_recent_commits"
    assert call.input["service"] == "orders-service"  # context-aware, not hardcoded
    assert call.id.startswith("toolu_")

    # enum fields get a valid member
    resp2 = await client.create_message(
        system="triage",
        messages=[
            {"role": "user", "content": "Investigate orders-service"},
            resp.as_assistant_message(),
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": call.id, "content": "ok"}
                ],
            },
        ],
        tools=TOOLS,
    )
    [call2] = resp2.tool_calls
    assert call2.name == "search_logs"
    assert call2.input["level"] in ("ERROR", "WARNING", "INFO")
    assert set(call2.input) >= {"service", "query", "level"}
