"""Regression tests for empty-credential model switching."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_llm_kwargs_rejects_empty_api_key():
    from RxyCode.RxyCode1_1_0.config.model_capabilities import DEFAULT_CAPABILITIES
    from RxyCode.RxyCode1_1_0.core.providers.base import BaseProvider

    class _P(BaseProvider):
        name = "test"

        def matches(self, base_url: str, model_name: str) -> bool:
            return True

        def capabilities(self, model_config: dict):
            return DEFAULT_CAPABILITIES

    with pytest.raises(ValueError, match="non-empty api_key"):
        _P().llm_kwargs(
            {
                "model_name": "deepseek-v4-flash-free",
                "api_key": "",
                "base_url": "https://opencode.ai/zen/v1",
                "resolved_max_tokens": 1024,
            },
            DEFAULT_CAPABILITIES,
        )


def test_switch_model_rejects_empty_credential_without_mutating_llm(monkeypatch):
    from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2

    agent = AgentV2.__new__(AgentV2)
    agent._active_task = None
    agent._cfg = {}
    agent._memory = SimpleNamespace(save_session=lambda: None)
    previous_llm = object()
    previous_config = {"model_name": "keep-me", "api_key": "sk-old"}
    agent._llm = previous_llm
    agent.model_config = previous_config

    monkeypatch.setattr(
        "RxyCode.RxyCode1_1_0.core.agent_v2._settings.get_model_config",
        lambda name, cfg: {
            "model_name": "deepseek-v4-flash-free",
            "api_key": "",
            "api_key_env": "OPENCODE_ZEN_API_KEY",
            "base_url": "https://opencode.ai/zen/v1",
        },
    )

    with pytest.raises(ValueError, match="API credential is unavailable"):
        agent.switch_model("zen/deepseek-v4-flash-free")

    assert agent._llm is previous_llm
    assert agent.model_config is previous_config
