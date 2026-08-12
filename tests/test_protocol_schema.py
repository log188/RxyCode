"""Frozen JSON Schema for the protocol package."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from protocol.notifications import NOTIFICATION_MODELS
from protocol.notifications import TokenUsage
from protocol.requests import CLIENT_REQUEST_MODELS
from protocol.schema import export_schema
from protocol.server_requests import SERVER_REQUEST_MODELS

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "protocol" / "schema.json"

ALL_PROTOCOL_MODELS: tuple[type[BaseModel], ...] = (
    *CLIENT_REQUEST_MODELS,
    *NOTIFICATION_MODELS,
    *SERVER_REQUEST_MODELS,
)


def test_all_protocol_models_have_docstrings() -> None:
    missing = [
        model.__name__
        for model in ALL_PROTOCOL_MODELS
        if not (model.__doc__ or "").strip()
    ]
    assert not missing, f"protocol models missing docstrings: {', '.join(missing)}"


def test_protocol_module_doc_has_sse_inventory() -> None:
    text = (Path(__file__).resolve().parents[1] / "docs" / "modules" / "protocol.md").read_text(
        encoding="utf-8"
    )
    assert "SSE event inventory" in text
    assert "approval_request" in text
    assert "token" in text
    raw = (Path(__file__).resolve().parents[1] / "docs" / "modules" / "protocol.md").read_bytes()
    assert raw[:2] != b"\xff\xfe", "protocol.md must be UTF-8, not UTF-16"


def test_exported_schema_exposes_discriminated_unions() -> None:
    schema = export_schema()
    defs = schema["$defs"]
    assert "ClientRequest" in defs
    assert "ProtocolNotification" in defs
    assert len(defs["ClientRequest"]["oneOf"]) == len(CLIENT_REQUEST_MODELS)
    assert len(defs["ProtocolNotification"]["oneOf"]) == len(NOTIFICATION_MODELS)


def test_exported_schema_matches_committed_file() -> None:
    current = json.dumps(export_schema(), indent=2, ensure_ascii=False) + "\n"
    committed = SCHEMA_PATH.read_text(encoding="utf-8")
    assert current == committed, (
        "protocol/schema.json is out of date. "
        "Run: python -m protocol.schema > protocol/schema.json "
        "and commit the diff; bump PROTOCOL_VERSION if semantics changed."
    )


def test_schema_freeze_detects_field_changes() -> None:
    schema = export_schema()
    defs = schema["$defs"]["PromptRequest"]
    assert "timeout_seconds" in defs["properties"]
    defs["properties"]["timeout_seconds"]["description"] = "mutated"
    mutated = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    committed = SCHEMA_PATH.read_text(encoding="utf-8")
    assert mutated != committed


def test_token_usage_accepts_explicitly_unreported_metrics() -> None:
    usage = TokenUsage(
        session_id="session-1",
        input_tokens=None,
        output_tokens=None,
        cache_hit_tokens=None,
    )
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.cache_hit_tokens is None


def test_subagent_rpc_methods_are_part_of_the_main_protocol_schema() -> None:
    schema = export_schema()
    request_methods = {
        definition["properties"]["method"]["const"]
        for name, definition in schema["$defs"].items()
        if name.endswith("Request")
        and isinstance(definition, dict)
        and "method" in definition.get("properties", {})
        and "const" in definition["properties"]["method"]
    }
    assert {
        "subagents/capability",
        "subagents/list",
        "agent/invoke",
        "task/start",
        "child_sessions/list",
        "child_sessions/events",
        "child_sessions/cancel",
        "child_sessions/retry",
    } <= request_methods
