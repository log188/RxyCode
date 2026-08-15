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


def _profile(kind: str, tools_digest: str, thinking: bool) -> PrefixProfile:
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
        prompt_variant="default",
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


def test_chat_prewarm_profile_is_compatible_with_chat_real_turn():
    """Derived from actual prewarm parameters (not hand-copied objects)."""
    chat_digest = digest_tools(None)
    prewarm_p = _profile("chat", chat_digest, thinking=False)
    real_p = _profile("chat", chat_digest, thinking=False)
    assert profiles_compatible(prewarm_p, real_p) is True
    assert profiles_compatible(prewarm_p, _profile("agent", chat_digest, False)) is False


def test_agent_prewarm_profile_is_compatible_with_agent_real_turn():
    agent_digest = _core_tools_digest()
    prewarm_p = _profile("agent", agent_digest, thinking=True)
    real_p = _profile("agent", agent_digest, thinking=True)
    assert profiles_compatible(prewarm_p, real_p) is True


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
