"""FX9 · optional agent namespace on application cache keys (PHASE-FIX §5 FX9).

Single-agent keys stay byte-identical when the namespace is unset so
existing precise/semantic entries keep working until Phase F assigns
agent ids. The namespace is a cache key only — never a system/prefix input.
"""

from __future__ import annotations

import hashlib

import pytest

from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2


def _ns_agent(namespace=None) -> AgentV2:
    agent = object.__new__(AgentV2)
    agent.model_config = {
        "base_url": "https://api.example.com/",
        "model_name": "deepseek-v4-flash",
        "api_key": "sk-test-123",
    }
    if namespace is not None:
        agent._agent_namespace = namespace
    return agent


def _expected_base() -> str:
    digest = hashlib.sha256(b"sk-test-123").hexdigest()
    return f"https://api.example.com|deepseek-v4-flash|{digest}"


def test_unset_namespace_byte_identical_to_legacy_template():
    """No _agent_namespace (or explicit None) must keep the legacy template:
    base_url|model|credential_digest — nothing appended."""
    agent = _ns_agent()
    assert agent._application_cache_namespace() == _expected_base()

    agent2 = _ns_agent(None)
    assert agent2._application_cache_namespace() == _expected_base()
    assert agent._application_cache_namespace() == agent2._application_cache_namespace()


def test_valid_namespace_appends_suffix():
    agent = _ns_agent("echo")
    assert agent._application_cache_namespace() == f"{_expected_base()}|echo"

    agent2 = _ns_agent("mcp.notes-v2")
    assert agent2._application_cache_namespace() == f"{_expected_base()}|mcp.notes-v2"


def test_valid_namespace_charset_boundaries():
    agent = _ns_agent("a")  # 1 char
    assert agent._application_cache_namespace().endswith("|a")
    agent = _ns_agent("x" * 64)  # 64 chars max
    assert agent._application_cache_namespace().endswith("|" + "x" * 64)
    agent = _ns_agent("a-z.9_-")
    assert agent._application_cache_namespace().endswith("|a-z.9_-")


@pytest.mark.parametrize(
    "bad",
    [
        "BAD",  # uppercase
        "has space",
        "中文",
        "x" * 65,  # too long
        "",
        "a|b",  # separator
        "a b",
        "@",
    ],
)
def test_invalid_namespace_raises(bad):
    agent = _ns_agent(bad)
    with pytest.raises(ValueError):
        agent._application_cache_namespace()
