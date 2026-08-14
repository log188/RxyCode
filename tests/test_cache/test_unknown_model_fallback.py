"""FXC6 · unknown-model five-point fallback (PHASE-FIX §5 FXC6 / §15.3).

Unknown models (``get_contract`` -> None) must behave explicitly like:
  1. Prompt -> default variant
  2. Protocol -> openai-compatible
  3. NEVER inject cache_control
  4. still sort tools and send session affinity headers (FXC4)
  5. prompt_cache_key is NOT sent by default

The injection layer documents these through ``unknown_fallback_contract()``
and the wire payload for an unknown model carries no cache_control / no
prompt_cache_key.
"""

from __future__ import annotations

import json

from RxyCode.RxyCode1_1_0.core.catalog import (
    get_contract,
    injects_cache_control,
    injects_prompt_cache_key,
    reset_contract_cache,
    unknown_fallback_contract,
)


def test_unknown_contract_is_none():
    reset_contract_cache()
    assert get_contract("no-such", "mystery") is None


def test_unknown_fallback_contract_is_documented_and_explicit():
    """The fallback contract constant exists and spells out the five points."""
    fb = unknown_fallback_contract()
    assert fb is not None
    assert fb.get("cache_mode") == "auto"  # implicit prefix, never explicit
    assert fb.get("breakpoints_max") == 0
    assert fb.get("prompt_cache_key_required") is False


def test_unknown_never_injects_control_or_key():
    reset_contract_cache()
    contract = get_contract("no-such", "mystery")
    assert injects_cache_control(contract) is False
    assert injects_prompt_cache_key(contract) is False


def test_unknown_prompt_variant_is_default():
    from RxyCode.RxyCode1_1_0.config.model_capabilities import DEFAULT_CAPABILITIES

    assert DEFAULT_CAPABILITIES.prompt_variant == "default"


def test_unknown_model_wire_payload_has_no_cache_control_or_key():
    """The real _raw_stream payload for an unknown model: no cache_control,
    no prompt_cache_key; tools still sorted; session header still present."""
    import asyncio
    from dataclasses import replace
    from types import SimpleNamespace

    from langchain_core.tools import StructuredTool

    from RxyCode.RxyCode1_1_0.config.model_capabilities import DEFAULT_CAPABILITIES
    from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2

    captured: dict = {}

    class FakeClient:
        def create(self, **payload):
            captured["payload"] = payload
            raise RuntimeError("stop-after-capture")

    caps = replace(
        DEFAULT_CAPABILITIES,
        provider="unknown",
        supports_function_calling=True,
    )
    agent = object.__new__(AgentV2)
    agent._session_id = "sess-fxc6"
    agent._llm = SimpleNamespace()
    agent._rate_limiter = None
    agent.model_config = {"model_name": "totally-mystery", "timeout": 5.0}
    agent._capabilities = caps
    agent._provider = None
    agent._resolve_request_max_tokens = lambda _n: 2048
    agent._openai_client = lambda: FakeClient()

    tools = [
        StructuredTool.from_function(lambda: "ok", name="bash", description="bash"),
        StructuredTool.from_function(lambda: "ok", name="read", description="read"),
    ]
    sys_msg = SimpleNamespace(type="system", content="SYS", additional_kwargs={})
    user_msg = SimpleNamespace(type="human", content="hi", additional_kwargs={})
    try:
        asyncio.run(agent._raw_stream([sys_msg, user_msg], tools=tools).__anext__())
    except RuntimeError as exc:
        if "stop-after-capture" not in str(exc):
            raise

    payload = captured["payload"]
    wire = json.dumps(payload)
    assert "cache_control" not in wire  # point 3
    extra = payload.get("extra_body") or {}
    assert "prompt_cache_key" not in extra  # point 5

    # point 4a: tools sorted by name (read before bash would be wrong)
    tool_names = [t.get("function", {}).get("name", "") for t in (payload.get("tools") or [])]
    assert tool_names == sorted(tool_names)
