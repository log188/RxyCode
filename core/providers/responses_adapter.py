"""LangChain Responses public-chunk → RxyCode internal stream.

Stdlib-only. Stress harnesses can import this without loading AgentV2 or the
installed ``RxyCode.RxyCode1_1_0`` package.
"""

from __future__ import annotations

import json
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


def accumulate_reasoning_items(
    store: list[dict[str, Any]], incoming: list[object]
) -> None:
    """Merge streamed reasoning items by id (or append a tail without id)."""
    for raw in incoming:
        if not isinstance(raw, dict) or str(raw.get("type") or "") != "reasoning":
            continue
        item = dict(raw)
        item_id = item.get("id")
        if item_id:
            for existing in store:
                if existing.get("id") == item_id:
                    extra = _reasoning_from_block(item)
                    if extra:
                        existing.setdefault("content", [])
                        if not isinstance(existing["content"], list):
                            existing["content"] = []
                        existing["content"].append(
                            {"type": "reasoning_text", "text": extra}
                        )
                    if item.get("encrypted_content"):
                        existing["encrypted_content"] = item["encrypted_content"]
                    break
            else:
                store.append(item)
            continue
        if store and store[-1].get("id") is None:
            extra = _reasoning_from_block(item)
            if extra:
                store[-1].setdefault("content", [])
                if not isinstance(store[-1]["content"], list):
                    store[-1]["content"] = []
                store[-1]["content"].append({"type": "reasoning_text", "text": extra})
        else:
            store.append(item)


def assistant_content_for_responses_replay(
    reasoning_items: list[dict[str, Any]],
    text: str,
) -> list[dict[str, Any]]:
    """Content list LangChain will serialize as reasoning items then text."""
    blocks = [dict(item) for item in reasoning_items if isinstance(item, dict)]
    if text:
        blocks.append({"type": "output_text", "text": text, "annotations": []})
    return blocks


def _tool_call_as_function_call(tool_call: object) -> dict[str, Any] | None:
    if isinstance(tool_call, dict):
        name = str(tool_call.get("name") or "")
        call_id = str(tool_call.get("id") or "")
        args = tool_call.get("args", tool_call.get("arguments", {}))
    else:
        name = str(getattr(tool_call, "name", "") or "")
        call_id = str(getattr(tool_call, "id", "") or "")
        args = getattr(tool_call, "args", {})
    if not name or not call_id:
        return None
    if isinstance(args, str):
        arguments = args
    else:
        arguments = json.dumps(args or {}, ensure_ascii=False)
    return {
        "type": "function_call",
        "name": name,
        "arguments": arguments,
        "call_id": call_id,
    }


def build_responses_replay_input(messages) -> list[dict[str, Any]]:
    """Rebuild DeepSeek/OpenAI Responses input: reasoning → function_call → output."""
    items: list[dict[str, Any]] = []
    for message in messages:
        role = getattr(message, "type", None)
        ak = getattr(message, "additional_kwargs", None) or {}
        content = getattr(message, "content", "")
        if role in {"system", "human"}:
            text = content if isinstance(content, str) else str(content or "")
            items.append(
                {
                    "type": "message",
                    "role": "system" if role == "system" else "user",
                    "content": text,
                }
            )
            continue
        if role == "ai":
            stored = ak.get("responses_reasoning_items")
            emitted_reasoning = False
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_type = str(block.get("type") or "")
                    if block_type == "reasoning":
                        items.append(dict(block))
                        emitted_reasoning = True
                    elif block_type in {"text", "output_text"} and block.get("text"):
                        items.append(
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": str(block.get("text") or ""),
                                    }
                                ],
                            }
                        )
            if not emitted_reasoning and isinstance(stored, list):
                for block in stored:
                    if isinstance(block, dict) and block.get("type") == "reasoning":
                        items.append(dict(block))
            elif (
                not emitted_reasoning
                and isinstance(ak.get("reasoning_content"), str)
                and ak["reasoning_content"]
            ):
                items.append(
                    {
                        "type": "reasoning",
                        "content": [
                            {
                                "type": "reasoning_text",
                                "text": ak["reasoning_content"],
                            }
                        ],
                    }
                )
            for tool_call in getattr(message, "tool_calls", None) or []:
                function_call = _tool_call_as_function_call(tool_call)
                if function_call is not None:
                    items.append(function_call)
            continue
        if role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": str(getattr(message, "tool_call_id", "") or ""),
                    "output": str(content or ""),
                }
            )
    return items


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
