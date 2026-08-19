"""F17 acceptance: team cache namespaces stay isolated."""

from __future__ import annotations

from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2
from RxyCode.RxyCode1_1_0.core.agents.runtime import AgentRuntime
from RxyCode.RxyCode1_1_0.core.session import Session
from RxyCode.RxyCode1_1_0.protocol.agents import AgentSpec


def test_runtime_spawn_assigns_agent_prefix() -> None:
    session = Session(session_id="ses-ns", workspace_root=".", emit=lambda _n: None)
    runtime = AgentRuntime(
        AgentSpec(role="coder", display_name="c", goal="c", prompt_stage="default"),
        session=session,
    )
    assert runtime.cache_namespace == "agent:coder"
    solo = AgentRuntime(
        AgentSpec(role="default", display_name="d", goal="d", prompt_stage="default"),
        session=session,
    )
    assert solo.cache_namespace is None


def test_single_agent_v2_key_unchanged_without_namespace() -> None:
    agent = AgentV2.__new__(AgentV2)
    agent.model_config = {"base_url": "http://x", "model_name": "m", "api_key": "k"}
    agent._agent_namespace = None
    other = AgentV2.__new__(AgentV2)
    other.model_config = {"base_url": "http://x", "model_name": "m", "api_key": "k"}
    assert agent._application_cache_namespace() == other._application_cache_namespace()
