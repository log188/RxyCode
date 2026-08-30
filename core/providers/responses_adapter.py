"""LangChain Responses public-chunk → RxyCode internal stream.

Stdlib-only. Stress harnesses can import this without loading AgentV2 or the
installed ``RxyCode.RxyCode1_1_0`` package.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator


def _text_from_part(part: object) -> str:
    if isinstance(part, str):
        return part
    if not isinstance(part, dict):
        return str(getattr(part, "text", "") or "")
    return str(part.get("text") or "")


def _reasoning_from_block(block: dict) -> str:
    """OpenAI uses ``summary[].text``; DeepSeek uses ``reasoning_text`` parts."""
    parts: list[str] = []
    for summary in block.get("summary") or []:
        text = _text_from_part(summary)
        if text:
            parts.append(text)
    content = block.get("content")
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                text = _text_from_part(part)
                if text:
                    parts.append(text)
                continue
            if str(part.get("type") or "") in {"reasoning_text", "text", "summary_text"}:
                text = _text_from_part(part)
                if text:
                    parts.append(text)
    elif isinstance(content, str) and content:
        parts.append(content)
    direct = block.get("text")
    if isinstance(direct, str) and direct and not parts:
        parts.append(direct)
    return "".join(parts)


def _maybe_native_reasoning_item(block: dict) -> dict[str, Any] | None:
    if str(block.get("type") or "") != "reasoning":
        return None
    item = {
        key: value
        for key, value in block.items()
        if value is not None and key in {
            "id",
            "type",
            "status",
            "content",
            "summary",
            "encrypted_content",
        }
    }
    return item or None


async def responses_stream_as_chat_chunks(stream) -> AsyncIterator[SimpleNamespace]:
    """Translate LangChain Responses chunks to the legacy raw-chat shape.

    Also accepts DeepSeek ``reasoning`` items whose content parts are
    ``reasoning_text`` rather than OpenAI ``summary`` blocks. Native reasoning
    items (id/content/summary) are attached on the chunk for later replay.
    """
    saw_legal_terminal = False
    saw_refusal = False
    async for item in stream:
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        refusal_parts: list[str] = []
        native_reasoning_items: list[dict[str, Any]] = []
        content = getattr(item, "content", "")
        if isinstance(content, str):
            if content:
                text_parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    if isinstance(block, str):
                        text_parts.append(block)
                    continue
                block_type = str(block.get("type") or "")
                if block_type in {"text", "output_text"}:
                    text_parts.append(str(block.get("text") or ""))
                elif block_type == "reasoning":
                    reasoning_parts.append(_reasoning_from_block(block))
                    native = _maybe_native_reasoning_item(block)
                    if native is not None:
                        native_reasoning_items.append(native)
                elif block_type == "reasoning_text":
                    reasoning_parts.append(_text_from_part(block))
                elif block_type == "refusal":
                    refusal = str(block.get("refusal") or "")
                    if refusal:
                        refusal_parts.append(refusal)
                        saw_refusal = True

        extra = getattr(item, "additional_kwargs", None) or {}
        if isinstance(extra, dict):
            extra_reason = extra.get("reasoning_content") or extra.get("reasoning")
            if isinstance(extra_reason, str) and extra_reason:
                reasoning_parts.append(extra_reason)

        tool_deltas = []
        for call in getattr(item, "tool_call_chunks", None) or []:
            if not isinstance(call, dict):
                continue
            tool_deltas.append(
                SimpleNamespace(
                    index=call.get("index", 0),
                    id=call.get("id"),
                    function=SimpleNamespace(
                        name=call.get("name"),
                        arguments=call.get("args") or "",
                    ),
                )
            )

        usage = None
        usage_metadata = getattr(item, "usage_metadata", None)
        if isinstance(usage_metadata, dict):
            input_details = usage_metadata.get("input_token_details") or {}
            output_details = usage_metadata.get("output_token_details") or {}
            cached_tokens = int(input_details.get("cache_read", 0) or 0)
            reasoning_tokens = int(output_details.get("reasoning", 0) or 0)
            usage = SimpleNamespace(
                prompt_tokens=int(usage_metadata.get("input_tokens", 0) or 0),
                completion_tokens=int(
                    usage_metadata.get("output_tokens", 0) or 0
                ),
                input_tokens_details=SimpleNamespace(
                    cached_tokens=cached_tokens
                ),
                prompt_tokens_details=SimpleNamespace(
                    cached_tokens=cached_tokens
                ),
                completion_tokens_details=SimpleNamespace(
                    reasoning_tokens=reasoning_tokens
                ),
                output_tokens_details=SimpleNamespace(
                    reasoning_tokens=reasoning_tokens
                ),
            )

        terminal = getattr(item, "chunk_position", None) == "last"
        finish_reason = None
        if terminal:
            metadata = getattr(item, "response_metadata", None)
            metadata = metadata if isinstance(metadata, dict) else {}
            status = str(metadata.get("status") or "").strip().casefold()
            if status == "completed":
                saw_legal_terminal = True
                finish_reason = (
                    "content_filter"
                    if saw_refusal
                    else ("tool_calls" if tool_deltas else "stop")
                )
            elif status == "incomplete":
                details = metadata.get("incomplete_details") or {}
                reason = (
                    str(details.get("reason") or "").strip().casefold()
                    if isinstance(details, dict)
                    else ""
                )
                if reason == "max_output_tokens":
                    saw_legal_terminal = True
                    finish_reason = "length"
                elif reason == "content_filter":
                    saw_legal_terminal = True
                    finish_reason = "content_filter"
                else:
                    raise RuntimeError(
                        "Responses stream ended with incomplete status but no "
                        "supported incomplete reason"
                    )
            elif status == "failed":
                raise RuntimeError("Responses stream ended with failed status")
            else:
                raise RuntimeError(
                    "Responses stream ended without a valid terminal response status"
                )
        delta = SimpleNamespace(
            content="".join(text_parts) + "".join(refusal_parts),
            reasoning_content="".join(reasoning_parts),
            tool_calls=tool_deltas,
        )
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=delta,
                    finish_reason=finish_reason,
                )
            ],
            usage=usage,
            _rxy_responses_terminal=terminal,
            _rxy_reasoning_items=native_reasoning_items,
        )
    if not saw_legal_terminal:
        raise RuntimeError(
            "Responses stream ended without a valid terminal response status"
        )
