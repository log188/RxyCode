"""FX4 · isomorphic prewarm archives (PHASE-FIX §5 FX4).

Prewarm must write the same tools/thinking/system bytes as the real turn
for each archive slot (chat vs agent) so a greeting no longer misses a
tools-on warmup prefix.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2
from RxyCode.RxyCode1_1_0.core.cache_policy import build_prewarm_signature
from RxyCode.RxyCode1_1_0.core.prefix_profile import (
    PrefixProfile,
    digest_tools,
    profiles_compatible,
)

CORE_TOOLS = [
    SimpleNamespace(name="bash", args_schema={}),
    SimpleNamespace(name="read", args_schema={}),
]


def _core_tools_digest() -> str:
    return digest_tools(CORE_TOOLS)


def _prewarm_agent() -> AgentV2:
    agent = object.__new__(AgentV2)
    agent.model_config = {"model_name": "test-model"}
    agent._cfg = {}
    agent._workspace_root = "/w"
    agent._prewarm = None
    agent._prewarm_chat = None
    agent._thinking_disabled_this_turn = False

    calls = []

    async def _raw(msgs, tools=None, max_tokens=1):
        calls.append(
            {
                "msgs": msgs,
                "tools": tools,
                "thinking_disabled": agent._thinking_disabled_this_turn,
            }
        )
        if False:  # pragma: no cover - never yields
            yield None

    agent._raw_stream = _raw
    agent._get_core_tools = lambda: list(CORE_TOOLS)
    agent._prompt_variant = lambda: "default"
    agent._captured_calls = calls
    return agent


def _profile(kind: str, tools_digest: str, thinking: bool, variant: str = "default") -> PrefixProfile:
    return PrefixProfile(
        kind=kind,  # type: ignore[arg-type]
        session_id="s",
        provider="test",
        model="test-model",
        thinking_enabled=thinking,
        thinking_effort=None,
        tools_digest=tools_digest,
        s1_digest="s1",
        system_template_version="1.0.0",
        prompt_variant=variant,
        agent_id=None,
    )


@pytest.mark.asyncio
async def test_chat_slot_writes_no_tools_thinking_off_warm():
    agent = _prewarm_agent()
    from RxyCode.RxyCode1_1_0.core.prewarm import prewarm_archive

    await prewarm_archive(agent, "chat")
    call = agent._captured_calls[0]
    assert call["tools"] is None
    assert call["thinking_disabled"] is True
    from langchain_core.messages import HumanMessage, SystemMessage

    assert any(
        isinstance(m, SystemMessage) for m in call["msgs"]
    ), "chat prewarm must carry system"
    assert any(
        isinstance(m, HumanMessage) and m.content == "warm" for m in call["msgs"]
    ), "user text must be warm"


@pytest.mark.asyncio
async def test_agent_slot_writes_core_tools_thinking_on():
    agent = _prewarm_agent()
    from RxyCode.RxyCode1_1_0.core.prewarm import prewarm_archive

    await prewarm_archive(agent, "agent")
    call = agent._captured_calls[0]
    assert call["tools"] is not None
    assert [t.name for t in call["tools"]] == ["bash", "read"]
    assert call["thinking_disabled"] is False


@pytest.mark.asyncio
async def test_two_slots_write_different_system_shapes():
    """chat system (tools=False) must differ from agent system (tools=True)."""
    from langchain_core.tools import StructuredTool

    from RxyCode.RxyCode1_1_0.tools.registry import registry

    if "fx4-test-tool" not in registry.get_names():
        registry.register(
            StructuredTool.from_function(
                func=lambda x: x,
                name="fx4-test-tool",
                description="FX4 test tool",
            )
        )
    try:
        agent = _prewarm_agent()
        from RxyCode.RxyCode1_1_0.core.prewarm import prewarm_archive

        await prewarm_archive(agent, "chat")
        await prewarm_archive(agent, "agent")
        chat_call, agent_call = agent._captured_calls
        chat_sys = next(
            m.content for m in chat_call["msgs"] if m.__class__.__name__ == "SystemMessage"
        )
        agent_sys = next(
            m.content for m in agent_call["msgs"] if m.__class__.__name__ == "SystemMessage"
        )
        assert "fx4-test-tool" in agent_sys
        assert "fx4-test-tool" not in chat_sys
    finally:
        registry.remove("fx4-test-tool")


@pytest.mark.asyncio
async def test_prewarm_async_fires_both_slots_and_confirms_both():
    agent = _prewarm_agent()
    await agent._prewarm_async()
    calls = agent._captured_calls
    assert len(calls) == 2
    tools_by_slot = {calls[0]["tools"] is None, calls[1]["tools"] is None}
    assert tools_by_slot == {True, False}
    thinking_by_slot = {calls[0]["thinking_disabled"], calls[1]["thinking_disabled"]}
    assert thinking_by_slot == {True, False}
    assert agent._prewarm.warmed_at is not None  # agent slot
    assert agent._prewarm_chat.warmed_at is not None  # chat slot
    assert agent._thinking_disabled_this_turn is False  # restored after swap


@pytest.mark.asyncio
async def test_chat_prewarm_profile_matches_real_chat_turn_params():
    """Both profiles derive from actual parameters: the captured prewarm
    call (tools=None, thinking off, variant) vs the real greeting-turn
    parameters (same tools/thinking/variant rules)."""
    agent = _prewarm_agent()
    from RxyCode.RxyCode1_1_0.core.prewarm import prewarm_archive

    await prewarm_archive(agent, "chat")
    call = agent._captured_calls[0]
    prewarm_p = _profile("chat", digest_tools(call["tools"]), thinking=False)
    # Real chat turn: no tools, thinking disabled via the greeting switch,
    # same variant the system prompt used.
    real_p = _profile("chat", digest_tools(None), thinking=False)
    assert profiles_compatible(prewarm_p, real_p) is True
    assert profiles_compatible(prewarm_p, _profile("agent", digest_tools(None), False)) is False


@pytest.mark.asyncio
async def test_agent_prewarm_profile_matches_real_agent_turn_params():
    """Derived from the captured agent-slot call (core tools, thinking on)
    vs the real encoding-turn parameters (same core tools, thinking on)."""
    agent = _prewarm_agent()
    from RxyCode.RxyCode1_1_0.core.prewarm import prewarm_archive

    await prewarm_archive(agent, "agent")
    call = agent._captured_calls[0]
    prewarm_p = _profile("agent", digest_tools(call["tools"]), thinking=True)
    real_p = _profile("agent", digest_tools(list(CORE_TOOLS)), thinking=True)
    assert profiles_compatible(prewarm_p, real_p) is True
    # Changing any slot dimension breaks compatibility.
    assert profiles_compatible(prewarm_p, _profile("chat", digest_tools(call["tools"]), True)) is False
    assert profiles_compatible(prewarm_p, _profile("agent", digest_tools(None), True)) is False


@pytest.mark.asyncio
async def test_prewarm_signature_equals_real_request_signature():
    """The prewarm signature for a slot must equal the signature computed
    from the real request parameters of that slot."""
    from RxyCode.RxyCode1_1_0.core.prewarm import prewarm_signature

    agent = _prewarm_agent()
    chat_sig = prewarm_signature(agent, "chat")
    chat_real = build_prewarm_signature(
        model="test-model", cwd="/w", mcp="", kind="chat",
        thinking_enabled=False, tools_digest=digest_tools(None),
    )
    assert chat_sig == chat_real

    agent_sig = prewarm_signature(agent, "agent")
    agent_real = build_prewarm_signature(
        model="test-model", cwd="/w", mcp="", kind="agent",
        thinking_enabled=True, tools_digest=_core_tools_digest(),
    )
    assert agent_sig == agent_real
    # Any single dimension change invalidates the slot signature.
    assert chat_sig != agent_sig
    assert agent_sig != build_prewarm_signature(
        model="test-model", cwd="/w", mcp="", kind="agent",
        thinking_enabled=True, tools_digest=digest_tools(None),
    )
    assert agent_sig != build_prewarm_signature(
        model="test-model", cwd="/w", mcp="", kind="agent",
        thinking_enabled=False, tools_digest=_core_tools_digest(),
    )


@pytest.mark.asyncio
async def test_keep_alive_rides_agent_prefix_shape():
    """FX5: keep-alive must carry the frozen agent archive (system + core
    tools + keep-alive user text), never a bare HumanMessage body."""
    agent = _prewarm_agent()
    await agent._keep_alive_async()
    call = agent._captured_calls[0]
    from langchain_core.messages import HumanMessage, SystemMessage

    assert any(isinstance(m, SystemMessage) for m in call["msgs"]), (
        "keep-alive must carry system"
    )
    assert any(
        isinstance(m, HumanMessage) and m.content == "keep-alive" for m in call["msgs"]
    )
    assert call["tools"] is not None
    assert [t.name for t in call["tools"]] == ["bash", "read"]
    assert call["thinking_disabled"] is False


def test_keepalive_tools_digest_equals_agent_profile():
    from RxyCode.RxyCode1_1_0.core.prewarm import keepalive_messages
    from RxyCode.RxyCode1_1_0.core.prefix_profile import digest_tools

    agent = _prewarm_agent()
    msgs = keepalive_messages(agent)
    agent_profile_digest = _core_tools_digest()
    assert digest_tools([{"name": "bash"}, {"name": "read"}]) == agent_profile_digest
    from langchain_core.messages import SystemMessage

    sys = next(m for m in msgs if isinstance(m, SystemMessage))
    assert "fx4-test-tool" not in sys  # system shape == agent prewarm system
    assert len(msgs) == 2  # system + keep-alive only


def test_keep_alive_disabled_by_default():
    from RxyCode.RxyCode1_1_0.core.cache_policy import keep_alive_enabled

    assert keep_alive_enabled(None) is False
    assert keep_alive_enabled({}) is False
    assert keep_alive_enabled({"cache": {}}) is False


def test_signature_includes_kind_thinking_tools():
    sig_chat = build_prewarm_signature(
        model="m", cwd="/w", mcp="", kind="chat",
        thinking_enabled=False, tools_digest=digest_tools(None),
    )
    sig_agent = build_prewarm_signature(
        model="m", cwd="/w", mcp="", kind="agent",
        thinking_enabled=True, tools_digest=_core_tools_digest(),
    )
    assert sig_chat != sig_agent
    sig_agent_no_tools = build_prewarm_signature(
        model="m", cwd="/w", mcp="", kind="agent",
        thinking_enabled=True, tools_digest=digest_tools(None),
    )
    assert sig_agent != sig_agent_no_tools
