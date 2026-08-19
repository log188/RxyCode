"""JSON-RPC 2.0 envelopes for F16. Reuses appserver.jsonrpc.parse_line."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from RxyCode.RxyCode1_1_0.appserver.jsonrpc import parse_line
from RxyCode.RxyCode1_1_0.protocol.agents import (
    BridgeAbort,
    BridgePlan,
    BridgeProgress,
    BridgeResult,
    BridgeToolCall,
    TaskDelegate,
)

BRIDGE_MODELS: dict[str, type[BaseModel]] = {
    "task_delegate": TaskDelegate,
    "progress": BridgeProgress,
    "tool_call": BridgeToolCall,
    "plan": BridgePlan,
    "result": BridgeResult,
    "abort": BridgeAbort,
}

SUMMARY_CHAR_CAP = 8000  # ~2k tokens


def encode(model: BaseModel, *, rpc_id: int | None = None) -> dict[str, Any]:
    payload = model.model_dump()
    method = payload.pop("method")
    envelope: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": payload}
    if rpc_id is not None:
        envelope["id"] = rpc_id
    return envelope


def decode_line(line: str) -> BaseModel | None:
    raw = parse_line(line)
    if raw is None:
        return None
    method = raw.get("method")
    model_cls = BRIDGE_MODELS.get(str(method or ""))
    if model_cls is None:
        raise ValueError(f"unknown bridge method {method!r}")
    params = raw.get("params") or {}
    try:
        return model_cls.model_validate(params)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


def truncate_summary(text: str) -> str:
    if len(text) <= SUMMARY_CHAR_CAP:
        return text
    return text[: SUMMARY_CHAR_CAP] + "\n…[truncated; see artifact]"
