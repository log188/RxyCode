"""FX1 · PrefixProfile type and fingerprint (PHASE-FIX §5 FX1).

Type-only card: frozen prefix identity for chat vs agent prefixes so
prewarm / greeting / keepalive / future Child can be checked for
isomorphism before AgentV2 routing changes.
"""

from __future__ import annotations

from RxyCode.RxyCode1_1_0.core.prefix_profile import (
    PrefixProfile,
    digest_tools,
    profiles_compatible,
)


def test_empty_tools_digest_is_stable():
    assert digest_tools([]) == digest_tools([])
    assert digest_tools(None) == digest_tools([])


def test_tool_order_does_not_change_digest():
    a = [{"name": "bash", "parameters": {"type": "object"}}, {"name": "read", "parameters": {}}]
    b = [{"name": "read", "parameters": {}}, {"name": "bash", "parameters": {"type": "object"}}]
    assert digest_tools(a) == digest_tools(b)


def test_chat_and_agent_identities_differ():
    chat = PrefixProfile(
        kind="chat",
        session_id="ses_1",
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_enabled=False,
        thinking_effort=None,
        tools_digest=digest_tools([]),
        s1_digest="s1chat",
        system_template_version="1.0.0",
        prompt_variant="default",
        agent_id=None,
    )
    agent = PrefixProfile(
        kind="agent",
        session_id="ses_1",
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_enabled=True,
        thinking_effort="balanced",
        tools_digest=digest_tools([{"name": "bash"}]),
        s1_digest="s1agent",
        system_template_version="1.0.0",
        prompt_variant="default",
        agent_id=None,
    )
    assert chat.identity() != agent.identity()
    assert profiles_compatible(chat, agent) is False


def test_same_fields_are_compatible():
    p = PrefixProfile(
        kind="agent",
        session_id="ses_1",
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_enabled=True,
        thinking_effort="balanced",
        tools_digest="abc",
        s1_digest="s1agent",
        system_template_version="1.0.0",
        prompt_variant="default",
        agent_id=None,
    )
    q = PrefixProfile(
        kind="agent",
        session_id="ses_1",
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_enabled=True,
        thinking_effort="balanced",
        tools_digest="abc",
        s1_digest="s1agent",
        system_template_version="1.0.0",
        prompt_variant="default",
        agent_id=None,
    )
    assert p.identity() == q.identity()
    assert profiles_compatible(p, q) is True
