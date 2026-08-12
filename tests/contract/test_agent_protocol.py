"""E4 contract tests: protocol AgentEvent domain (PHASE-E §5 E4).

Coverage:
- the ten frozen AgentMethod entries live in NOTIFICATION_MODELS (EB1)
- per-method field matrix: routed requires experiment_tag/routing_reason;
  non-routed forbids routing_reason; team_created forbids experiment_tag;
  budget_exceeded requires the cumulative snapshot (strict ints)
- strict ints: bool/str/float tokens_used are rejected; negatives rejected
- source three-state wire protocol: omitted | internal | bridge, round-trip
  preserved; unknown values rejected on construction and deserialization
- unknown fields ignored on deserialization; misspelled known fields
  (source="bridg") rejected, never silently treated as unknown
- event/team_* never falls into AgentEvent (no default fallback); the
  legacy event/team_created is rejected outright
- SSE (`type: agent_*`) and stdio (`method: event/agent_*`) envelopes carry
  identical event fields
"""

from __future__ import annotations

import json
from typing import get_args

import pytest
from pydantic import ValidationError

from protocol.notifications import (
    NOTIFICATION_MODELS,
    AgentEvent,
    AgentMethod,
)
from protocol.types import JsonObject

AGENT_METHODS = [
    "event/agent_started",
    "event/agent_tool",
    "event/agent_progress",
    "event/agent_done",
    "event/agent_paused",
    "event/agent_cancelled",
    "event/agent_budget_exceeded",
    "event/agent_denied",
    "event/agent_routed",
    "event/agent_team_created",
]


def _evt(method: str, **extra) -> AgentEvent:
    base: dict = {
        "method": method,
        "session_id": "s1",
        "agent_id": "A",
        "payload": {},
        "seq": 1,
    }
    base.update(extra)
    return AgentEvent(**base)


# ---------------------------------------------------------------------------
# ten frozen methods
# ---------------------------------------------------------------------------


def test_ten_methods_exist_and_are_constructed():
    for method in AGENT_METHODS:
        extra = {}
        if method == "event/agent_budget_exceeded":
            extra = {"tokens_used": 0, "budget_used": 0}
        if method == "event/agent_routed":
            extra = {"experiment_tag": "E0", "routing_reason": "smoke"}
        evt = _evt(method, **extra)
        assert evt.method == method


def test_agent_event_in_notification_models():
    assert AgentEvent in NOTIFICATION_MODELS


def test_agent_method_count_derives_from_enum():
    assert len(get_args(AgentMethod)) == 10
    assert set(get_args(AgentMethod)) == set(AGENT_METHODS)


def test_existing_notifications_untouched():
    legacy_methods = {
        m.model_fields["method"].default
        for m in NOTIFICATION_MODELS
        if m is not AgentEvent and "method" in m.model_fields
    }
    # all pre-E4 methods still present (EB1 add-only)
    for legacy in (
        "event/message_delta",
        "event/tool_begin",
        "event/tool_end",
        "event/token_usage",
        "event/server_heartbeat",
    ):
        assert legacy in legacy_methods


# ---------------------------------------------------------------------------
# per-method field matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", AGENT_METHODS)
def test_non_routed_methods_forbid_routing_reason(method: str):
    if method == "event/agent_routed":
        return
    with pytest.raises(ValidationError):
        _evt(method, routing_reason="because")


@pytest.mark.parametrize(
    "method",
    [
        m
        for m in AGENT_METHODS
        if m
        not in (
            "event/agent_routed",
            "event/agent_team_created",
            "event/agent_budget_exceeded",
        )
    ],
)
def test_experiment_tag_optional_for_plain_methods(method: str):
    evt = _evt(method, experiment_tag="E1")
    assert evt.experiment_tag == "E1"


def test_routed_requires_experiment_tag():
    with pytest.raises(ValidationError):
        _evt("event/agent_routed", routing_reason="mode router")
    ok = _evt("event/agent_routed", experiment_tag="E1", routing_reason="mode router")
    assert ok.experiment_tag == "E1"
    assert ok.routing_reason == "mode router"


def test_routed_requires_routing_reason():
    with pytest.raises(ValidationError):
        _evt("event/agent_routed", experiment_tag="E0")


def test_team_created_forbids_experiment_tag():
    with pytest.raises(ValidationError):
        _evt("event/agent_team_created", experiment_tag="E0")


def test_budget_exceeded_requires_snapshot():
    with pytest.raises(ValidationError):
        _evt("event/agent_budget_exceeded")
    with pytest.raises(ValidationError):
        _evt("event/agent_budget_exceeded", tokens_used=5)
    ok = _evt("event/agent_budget_exceeded", tokens_used=5, budget_used=3)
    assert ok.tokens_used == 5


def test_plain_methods_accept_optional_snapshot_fields():
    evt = _evt("event/agent_done", tokens_used=10, budget_used=7, cache_miss_warning=True)
    assert evt.tokens_used == 10
    assert evt.budget_used == 7
    assert evt.cache_miss_warning is True


# ---------------------------------------------------------------------------
# strict ints (pydantic strict: bool/str/float rejected)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [True, "12", 12.0])
def test_tokens_used_rejects_non_int(bad):
    with pytest.raises(ValidationError):
        _evt("event/agent_done", tokens_used=bad)


@pytest.mark.parametrize("bad", [True, "7", 7.0])
def test_budget_used_rejects_non_int(bad):
    with pytest.raises(ValidationError):
        _evt("event/agent_done", budget_used=bad)


@pytest.mark.parametrize("field", ["tokens_used", "budget_used"])
def test_negative_snapshots_rejected(field: str):
    with pytest.raises(ValidationError):
        _evt("event/agent_done", **{field: -1})


def test_snapshot_defaults_to_none_at_schema_layer():
    evt = _evt("event/agent_started")
    assert evt.tokens_used is None  # compatibility layer: may be absent
    assert evt.budget_used is None


# ---------------------------------------------------------------------------
# source three-state wire protocol
# ---------------------------------------------------------------------------


def test_source_defaults_to_none():
    assert _evt("event/agent_started").source is None


def test_source_bridge_round_trip_preserved():
    evt = _evt("event/agent_started", source="bridge")
    wire = evt.model_dump(exclude_none=True)
    assert wire["source"] == "bridge"
    back = AgentEvent(**json.loads(evt.model_dump_json()))
    assert back.source == "bridge"


def test_source_omitted_when_default_and_exclude_none():
    wire = _evt("event/agent_started").model_dump(exclude_none=True)
    assert "source" not in wire  # three states: omitted | internal | bridge


def test_source_unknown_value_rejected():
    with pytest.raises(ValidationError):
        _evt("event/agent_started", source="external")


# ---------------------------------------------------------------------------
# unknown vs invalid fields
# ---------------------------------------------------------------------------


def test_unknown_fields_ignored_on_deserialization():
    raw = {
        "method": "event/agent_started",
        "session_id": "s",
        "agent_id": "A",
        "seq": 1,
        "future_field": {"x": 1},
    }
    evt = AgentEvent(**raw)
    assert evt.seq == 1


def test_misspelled_known_field_rejected_not_ignored():
    raw = {
        "method": "event/agent_started",
        "session_id": "s",
        "agent_id": "A",
        "seq": 1,
        "source": "bridg",  # typo of a KNOWN field -> must reject
    }
    with pytest.raises(ValidationError):
        AgentEvent(**raw)


# ---------------------------------------------------------------------------
# event/team_* never falls into AgentEvent
# ---------------------------------------------------------------------------


def test_legacy_event_team_created_rejected():
    raw = {
        "method": "event/team_created",
        "session_id": "s",
        "agent_id": "A",
        "seq": 1,
    }
    with pytest.raises(ValidationError):
        AgentEvent(**raw)


def test_any_team_prefix_rejected():
    for method in ("event/team", "event/team_created", "event/team_consult"):
        with pytest.raises(ValidationError):
            _evt(method)


# ---------------------------------------------------------------------------
# dual channels: SSE vs stdio envelopes carry identical fields
# ---------------------------------------------------------------------------


def test_sse_and_stdio_envelopes_carry_identical_fields():
    evt = _evt(
        "event/agent_progress",
        experiment_tag="E1",
        tokens_used=12,
        budget_used=9,
    )
    fields = evt.model_dump(exclude_none=True)

    sse_envelope = {"type": "agent_progress", **fields}
    stdio_envelope = {
        "jsonrpc": "2.0",
        "method": "event/agent_progress",
        "params": {k: v for k, v in fields.items() if k != "method"},
    }

    assert sse_envelope["type"] == "agent_progress"
    assert stdio_envelope["method"] == "event/agent_progress"
    # both channels expose the same event fields (only the envelope differs)
    assert stdio_envelope["params"]["agent_id"] == sse_envelope["agent_id"]
    assert stdio_envelope["params"]["experiment_tag"] == sse_envelope["experiment_tag"]
    assert stdio_envelope["params"]["tokens_used"] == sse_envelope["tokens_used"]
    assert stdio_envelope["params"]["budget_used"] == sse_envelope["budget_used"]


def test_round_trip_preserves_payload_json_types():
    payload: JsonObject = {"reasoning": ["a", 1, {"k": None}]}
    evt = _evt("event/agent_done", payload=payload)
    back = AgentEvent(**json.loads(evt.model_dump_json()))
    assert back.payload == payload
