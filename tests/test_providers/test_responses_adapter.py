"""DeepSeek/OpenAI Responses chunk normalization."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.providers.responses_adapter import responses_stream_as_chat_chunks


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
