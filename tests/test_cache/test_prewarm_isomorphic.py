"""FX4 · isomorphic prewarm archives (PHASE-FIX §5 FX4).

Prewarm must write the same tools/thinking/system bytes as the real turn
for each archive slot (chat vs agent) so a greeting no longer misses a
tools-on warmup prefix.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2
from RxyCode.RxyCode1_1_0.core.cache_policy import build_prewarm_signature
from RxyCode.RxyCode1_1_0.core.prefix_profile import (
    PrefixProfile,
    digest_tools,
    profiles_compatible,
)


def _prewarm_agent() -> AgentV2:
    agent = object.__new__(AgentV2)
    agent.model_config = {"model_name": "test-model"}
    agent._cfg = {}
    agent._workspace_root = "/w"
    agent._prewarm = None
    agent._prewarm_chat = None

    captured = {}

    async def _raw(msgs, tools=None, max_tokens=1):
        captured.setdefault("calls", []).append({"msgs": msgs, "tools": tools})
        if False:  # pragma: no cover - never yields
            yield None

    agent._raw_stream = _raw
    agent._get_core_tools = lambda: [
        SimpleNamespace(name="bash", args_schema={}),
        SimpleNamespace(name="read", args_schema={}),
    ]
    agent._prompt_variant = lambda: "default"
    agent._captured = captured
    return agent


def _core_tools_digest() -> str:
    return digest_tools(
        [
            SimpleNamespace(name="bash", args_schema={}),
            SimpleNamespace(name="read", args_schema={}),
        ]
    )


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
async def test_chat_prewarm_sends_no_tools():
    agent = _prewarm_agent()
    from RxyCode.RxyCode1_1_0.core.prewarm import prewarm_archive

    await prewarm_archive(agent, "chat")
    calls = agent._captured["calls"]
    assert len(calls) == 1
    assert calls[0]["tools"] is None


@pytest.mark.asyncio
async def test_agent_prewarm_sends_core_tools():
    agent = _prewarm_agent()
    from RxyCode.RxyCode1_1_0.core.prewarm import prewarm_archive

    await prewarm_archive(agent, "agent")
    calls = agent._captured["calls"]
    assert len(calls) == 1
    assert calls[0]["tools"] is not None
    assert [t.name for t in calls[0]["tools"]] == ["bash", "read"]


@pytest.mark.asyncio
async def test_prewarm_async_fires_both_slots():
    agent = _prewarm_agent()
    await agent._prewarm_async()
    calls = agent._captured["calls"]
    assert len(calls) == 2
    tools_by_slot = {calls[0]["tools"] is None, calls[1]["tools"] is None}
    assert tools_by_slot == {True, False}
    assert agent._prewarm.warmed_at is not None


def test_chat_prewarm_profile_matches_chat_real_turn():
    chat_digest = digest_tools(None)
    prewarm_p = _profile("chat", chat_digest, thinking=False)
    real_p = _profile("chat", chat_digest, thinking=False)
    assert profiles_compatible(prewarm_p, real_p) is True
    assert profiles_compatible(prewarm_p, _profile("agent", chat_digest, False)) is False


def test_agent_prewarm_profile_matches_agent_real_turn():
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
