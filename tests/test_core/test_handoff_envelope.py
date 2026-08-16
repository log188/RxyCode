"""FX10 · HandoffEnvelope without chat history fields (PHASE-FIX §5 FX10).

Future multi-model handoff cannot smuggle transcripts into another
prefix. The type rejects history/thinking keys at the boundary.
"""

from __future__ import annotations

import dataclasses

import pytest

from RxyCode.RxyCode1_1_0.core.handoff import HandoffEnvelope

VALID = {
    "summary": "fixed the calc.py off-by-one",
    "artifact_paths": ("fix.patch",),
    "attachment_ids": ("att-1",),
    "source_model": "deepseek-v4-flash",
    "target_model": "gpt-5.6-luna",
}


def test_valid_envelope_roundtrip():
    env = HandoffEnvelope.from_dict(dict(VALID))
    assert env.summary == VALID["summary"]
    assert env.artifact_paths == ("fix.patch",)
    assert env.attachment_ids == ("att-1",)
    assert env.source_model == "deepseek-v4-flash"
    assert env.target_model == "gpt-5.6-luna"
    assert dataclasses.is_dataclass(env)
    assert env.__dataclass_params__.frozen is True
    assert getattr(env.__dataclass_params__, "slots", True) is True


def test_from_dict_requires_all_fields():
    with pytest.raises(TypeError):
        HandoffEnvelope.from_dict({"summary": "s"})


@pytest.mark.parametrize(
    "bad_key",
    ["messages", "history", "thinking", "reasoning_content", "tool_calls"],
)
def test_from_dict_rejects_history_keys(bad_key):
    payload = dict(VALID)
    payload[bad_key] = [{"role": "user", "content": "x"}]
    with pytest.raises(TypeError):
        HandoffEnvelope.from_dict(payload)


def test_child_must_not_copy_primary_history():
    """Documentation test: a HandoffEnvelope has NO transcript fields — a
    child prefix can never be rebuilt from the primary's chat history."""
    field_names = {f.name for f in dataclasses.fields(HandoffEnvelope)}
    assert "messages" not in field_names
    assert "history" not in field_names
    assert "thinking" not in field_names
    assert "reasoning_content" not in field_names
    assert "tool_calls" not in field_names
    assert not hasattr(HandoffEnvelope, "messages")
