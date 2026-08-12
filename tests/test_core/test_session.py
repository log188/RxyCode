import pytest
from pathlib import Path
from pydantic import BaseModel

from core.session import (
    PromptResult,
    Session,
    notification_to_sse_event,
    thinking_cursor,
    thinking_since,
)
from protocol.notifications import ErrorNotification, FinalAnswer, TokenUsage
from RxyCode.RxyCode1_1_0.utils.streaming import token_stats


class _FakeAgent:
    def __init__(self, answer: str = "ok", *, fail: bool = False):
        self._answer = answer
        self._fail = fail
        self._cancelled = False
        self._thinking_history: list[str] = []
        self._last_thinking = ""

    async def run(self, text: str, mode: str = "build") -> str:
        if self._fail:
            raise RuntimeError("boom")
        return self._answer

    def cancel(self) -> bool:
        self._cancelled = True
        return True


class _UsageAgent(_FakeAgent):
    async def run(self, text: str, mode: str = "build") -> str:
        token_stats.add_real_usage(100, 25, cache_read_tokens=40)
        return await super().run(text, mode)


@pytest.mark.asyncio
async def test_session_prompt_emits_final_answer():
    emitted: list[BaseModel] = []
    session = Session(
        session_id="s1",
        workspace_root=Path("/tmp/ws"),
        emit=emitted.append,
        session_schema_version=3,
    )
    result = await session.prompt(
        _FakeAgent("hello"),
        "hi",
        mode="build",
        run_id="run-1",
    )
    assert result.status == "succeeded"
    assert result.answer == "hello"
    assert any(isinstance(item, FinalAnswer) for item in emitted)
    final = next(item for item in emitted if isinstance(item, FinalAnswer))
    assert final.text == "hello"
    assert final.run_id == "run-1"
    assert final.input_tokens is None
    assert final.output_tokens is None
    assert final.reporting_status == "not_reported"


@pytest.mark.asyncio
async def test_session_prompt_forwards_provider_cache_usage_for_this_turn():
    """Desktop reports require a per-turn provider-cache metric, not globals."""
    token_stats.reset()
    try:
        emitted: list[BaseModel] = []
        session = Session(session_id="s-cache", workspace_root=Path("/tmp/ws"), emit=emitted.append)

        result = await session.prompt(_UsageAgent("cached"), "hi", mode="build", run_id="run-cache")

        usage = next(item for item in emitted if isinstance(item, TokenUsage))
        assert result.cache_hit_tokens == 40
        assert result.cache_hit_rate == 40.0
        assert usage.cache_hit_tokens == 40
        assert usage.cache_hit_rate == 40.0
    finally:
        token_stats.reset()


@pytest.mark.asyncio
async def test_session_prompt_emits_error_on_exception():
    emitted: list[BaseModel] = []
    session = Session(session_id="s1", workspace_root=Path("/tmp/ws"), emit=emitted.append)
    result = await session.prompt(
        _FakeAgent(fail=True),
        "hi",
        mode="build",
        run_id="run-2",
    )
    assert result.status == "failed"
    assert any(isinstance(item, ErrorNotification) for item in emitted)


def test_notification_to_sse_event_maps_final():
    event = notification_to_sse_event(
        FinalAnswer(
            session_id="s1",
            run_id="run-1",
            text="answer",
            thinking="thought",
            input_tokens=1,
            output_tokens=2,
            session_schema_version=3,
        )
    )
    assert event == {
        "type": "final",
        "run_id": "run-1",
        "text": "answer",
        "thinking": "thought",
        "input_tokens": 1,
        "output_tokens": 2,
        "cache_hit_tokens": 0,
        "cache_hit_rate": 0.0,
        "session_schema_version": 3,
    }


def test_session_interrupt_delegates_to_agent():
    agent = _FakeAgent()
    session = Session(session_id="s1", workspace_root=Path("/tmp/ws"), emit=lambda _: None)
    assert session.interrupt(agent) is True
    assert agent._cancelled is True


def test_thinking_since_returns_delta():
    agent = _FakeAgent()
    agent._thinking_history = ["a"]
    cursor = thinking_cursor(agent)
    agent._thinking_history = ["a", "b"]
    assert thinking_since(agent, cursor) == "b"
