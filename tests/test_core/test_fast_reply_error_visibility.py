"""RL9: the chat-path fallback must not hide why it fired."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2


class _Memory:
    async def initialize(self):
        return None

    def load_session(self, append_only=False):
        return None

    def get_context_for_prompt(self):
        return ""

    def add_interaction(self, *_args):
        return None

    def save_session(self):
        return None


def _chat_agent() -> AgentV2:
    agent = object.__new__(AgentV2)
    agent._cancelled = False
    agent._active_task = None
    agent._session_loaded = True
    agent._session_id = "rl9"
    agent._memory = _Memory()
    agent._llm = None
    agent._tool_orchestrator = None
    agent._tool_tracer = None
    agent._thinking_history = []
    agent._last_thinking = ""
    agent._detect_file_operation = MagicMock(return_value=None)
    agent._detect_download_intent = MagicMock(return_value=None)
    agent._has_creation_product_intent = MagicMock(return_value=False)
    agent._fast_reply = AsyncMock(side_effect=RuntimeError("rl9-boom"))
    agent._graph = SimpleNamespace(ainvoke=AsyncMock())
    return agent


@pytest.mark.asyncio
async def test_strict_mode_reraises_fast_reply_exception():
    agent = _chat_agent()
    with pytest.raises(RuntimeError, match="rl9-boom"):
        await agent._run_impl("你好")


@pytest.mark.asyncio
async def test_non_strict_mode_returns_fallback_and_logs_stack(monkeypatch, caplog):
    monkeypatch.setenv("RXYCODE_STRICT_ERRORS", "0")
    agent = _chat_agent()
    with caplog.at_level(logging.ERROR, logger="RxyCode.RxyCode1_1_0.core.agent_v2"):
        result = await agent._run_impl("你好")
    assert "刚才没能完整回复你" in result
    assert any(
        rec.levelno >= logging.ERROR and rec.exc_info is not None
        for rec in caplog.records
    )
