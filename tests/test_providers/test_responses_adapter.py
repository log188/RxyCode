"""DeepSeek/OpenAI Responses chunk normalization."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from core.providers.responses_adapter import (
    accumulate_reasoning_items,
    assistant_content_for_responses_replay,
    build_responses_replay_input,
    responses_stream_as_chat_chunks,
)


@pytest.mark.asyncio
async def test_adapter_reads_deepseek_reasoning_text_parts():
    async def source():
        yield SimpleNamespace(
            content=[
                {
                    "id": "rs_1",
                    "type": "reasoning",
                    "status": "completed",
                    "content": [
                        {"type": "reasoning_text", "text": "first thought"}
                    ],
                },
                {"type": "output_text", "text": "answer"},
            ],
            tool_call_chunks=[],
            usage_metadata=None,
            chunk_position=None,
        )
        yield SimpleNamespace(
            content=[],
            tool_call_chunks=[],
            usage_metadata=None,
            chunk_position="last",
            response_metadata={"status": "completed"},
        )

    chunks = [chunk async for chunk in responses_stream_as_chat_chunks(source())]
    assert chunks[0].choices[0].delta.reasoning_content == "first thought"
    assert chunks[0].choices[0].delta.content == "answer"
    assert chunks[0]._rxy_reasoning_items[0]["id"] == "rs_1"
    assert chunks[0]._rxy_reasoning_items[0]["type"] == "reasoning"


@pytest.mark.asyncio
async def test_adapter_still_reads_openai_reasoning_summary():
    async def source():
        yield SimpleNamespace(
            content=[
                {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "brief"}],
                }
            ],
            tool_call_chunks=[],
            usage_metadata=None,
            chunk_position=None,
        )
        yield SimpleNamespace(
            content=[],
            tool_call_chunks=[],
            usage_metadata=None,
            chunk_position="last",
            response_metadata={"status": "completed"},
        )

    chunks = [chunk async for chunk in responses_stream_as_chat_chunks(source())]
    assert chunks[0].choices[0].delta.reasoning_content == "brief"


def test_responses_replay_input_is_reasoning_then_function_call_then_output():
    items = []
    accumulate_reasoning_items(
        items,
        [
            {
                "id": "rs_1",
                "type": "reasoning",
                "content": [{"type": "reasoning_text", "text": "plan"}],
            }
        ],
    )
    content = assistant_content_for_responses_replay(items, "")
    messages = [
        HumanMessage(content="weather?"),
        AIMessage(
            content=content,
            tool_calls=[
                {
                    "name": "get_weather",
                    "args": {"city": "Hangzhou"},
                    "id": "call_1",
                    "type": "tool_call",
                }
            ],
            additional_kwargs={"responses_reasoning_items": items},
        ),
        ToolMessage(content="24C", tool_call_id="call_1"),
    ]
    wire = build_responses_replay_input(messages)
    assert [item["type"] for item in wire] == [
        "message",
        "reasoning",
        "function_call",
        "function_call_output",
    ]
    assert wire[1]["id"] == "rs_1"
    assert wire[2]["call_id"] == "call_1"
    assert wire[3]["output"] == "24C"


def test_langchain_responses_input_replays_reasoning_items_before_tools():
    from langchain_openai.chat_models.base import _construct_responses_api_input

    reasoning = {
        "id": "rs_1",
        "type": "reasoning",
        "content": [{"type": "reasoning_text", "text": "plan"}],
    }
    messages = [
        HumanMessage(content="weather?"),
        AIMessage(
            content=assistant_content_for_responses_replay([reasoning], ""),
            tool_calls=[
                {
                    "name": "get_weather",
                    "args": {"city": "Hangzhou"},
                    "id": "call_1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content="24C", tool_call_id="call_1"),
    ]
    wire = _construct_responses_api_input(messages)
    assert [item.get("type") for item in wire] == [
        "message",
        "reasoning",
        "function_call",
        "function_call_output",
    ]
