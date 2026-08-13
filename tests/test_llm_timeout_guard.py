"""
Tests for LLM call timeout guard (2026-08-13 fix).

Root cause fixed: LLM streaming establishment (`first = await ait.__anext__()`)
and the raw OpenAI client had no effective total timeout (default 600s),
so an upstream hang produced 0-token stalls that appserver's watchdog
(120s) killed first -- surfacing as "job stalled" instead of a real
model-request timeout. Now:
  - UsageTrackingLLM gains `llm_timeout` (default 90s, config-overridable)
  - `_open_stream` / `_open_stream_with_retry` wrap first-chunk wait
  - `AgentV2._openai_client` AsyncOpenAI(timeout=...) defaults to 90s
"""
import asyncio
import pytest
from unittest.mock import MagicMock


def _make_usage_llm(timeout=90.0):
    from RxyCode.RxyCode1_1_0.core.agent_v2 import UsageTrackingLLM
    llm = object.__new__(UsageTrackingLLM)
    llm._llm_timeout = max(1.0, float(timeout))
    return llm


def _make_agent(model_config=None):
    from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2
    agent = object.__new__(AgentV2)
    agent.model_config = dict(model_config or {})
    return agent


class FakeHangingStream:
    """A stream whose first chunk never arrives (upstream hang)."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.Event().wait()  # hangs forever


class StreamHolder:
    """Plain holder so astream() returns an object whose __aiter__ is real."""

    def __init__(self, stream):
        self._stream = stream

    def __aiter__(self):
        return self._stream


class TestLlmCallTimeout:
    def test_default_is_90(self):
        llm = _make_usage_llm()
        assert llm._llm_call_timeout() == 90.0

    def test_config_override(self):
        llm = _make_usage_llm(timeout=25)
        assert llm._llm_call_timeout() == 25.0

    def test_zero_clamped(self):
        llm = _make_usage_llm(timeout=0)
        assert llm._llm_call_timeout() == 1.0


class TestOpenStreamFirstChunkTimeout:
    async def test_hanging_first_chunk_raises_timeout(self):
        llm = _make_usage_llm(timeout=2)
        llm._llm = MagicMock()
        llm._llm.astream.return_value = FakeHangingStream()
        start = asyncio.get_event_loop().time()
        with pytest.raises(asyncio.TimeoutError):
            await llm._open_stream([], **{})
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 6.0  # must not hang forever

    async def test_immediate_first_chunk_returns(self):
        llm = _make_usage_llm(timeout=5)
        first = object()
        stream = MagicMock()
        stream.__aiter__.return_value = stream
        stream.__anext__.side_effect = [first]
        llm._llm = MagicMock()
        llm._llm.astream.return_value = StreamHolder(stream)
        got, _rest = await llm._open_stream([], **{})
        assert got is first


class TestOpenStreamWithRetryTimeout:
    async def test_hang_retries_then_raises(self):
        llm = _make_usage_llm(timeout=2)
        llm._transport_retries = 1  # total 2 attempts
        llm._llm = MagicMock()
        llm._llm.astream.return_value = FakeHangingStream()
        start = asyncio.get_event_loop().time()
        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await llm._open_stream_with_retry([], {})
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 12.0  # 2 attempts x 2s timeout + backoff, bounded

    async def test_retry_recovers_on_second_attempt(self):
        llm = _make_usage_llm(timeout=2)
        llm._transport_retries = 1
        first = object()
        calls = {"n": 0}

        class FlakyStream:
            def __aiter__(self):
                return self

            async def __anext__(self):
                calls["n"] += 1
                if calls["n"] <= 1:
                    await asyncio.Event().wait()  # first attempt hangs
                return first

        llm._llm = MagicMock()
        llm._llm.astream.return_value = StreamHolder(FlakyStream())
        got, _rest = await llm._open_stream_with_retry([], {})
        assert got is first
        assert calls["n"] == 2


class TestOpenAIClientTimeout:
    def test_default_timeout_90(self):
        agent = _make_agent({})
        agent._llm = None
        agent.model_config["api_key"] = "k"
        agent.model_config["base_url"] = "https://example.com/v1"
        client = agent._openai_client()
        value = getattr(client.timeout, "read", client.timeout)
        assert float(value) == 90.0

    def test_config_timeout_respected(self):
        agent = _make_agent({"timeout": 45})
        agent._llm = None
        agent.model_config["api_key"] = "k"
        agent.model_config["base_url"] = "https://example.com/v1"
        client = agent._openai_client()
        value = getattr(client.timeout, "read", client.timeout)
        assert float(value) == 45.0


class TestPrewarmNonBlocking:
    """2026-08-13: 预热必须非阻塞——用户请求绝不被预热请求拖慢。

    根因：预热曾在 run() 入口同步发 max_tokens=1 请求，上游慢/挂时
    每个请求首轮延迟 90s+（实测 117.6s = 90s 预热超时 + 27.6s 正式请求），
    且预热失败不 confirm → 每请求重复触发。现在后台执行 + 60s 冷却。
    """

    async def test_schedule_returns_immediately(self):
        import asyncio
        from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2

        agent = object.__new__(AgentV2)
        agent._llm = object()  # non-None

        started = []
        async def slow_prewarm():
            started.append(True)
            await asyncio.Event().wait()  # never completes

        agent._prewarm_async = slow_prewarm
        agent._prewarm_last_attempt_at = None
        t0 = asyncio.get_event_loop().time()
        agent._schedule_prewarm()  # must not await the hang
        assert asyncio.get_event_loop().time() - t0 < 1.0
        await asyncio.sleep(0.01)  # 让后台任务被调度
        assert started == [True]
        # 清理挂起的后台任务
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for t in tasks:
            t.cancel()

    async def test_cooldown_prevents_repeat_trigger(self):
        from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2

        agent = object.__new__(AgentV2)
        agent._llm = object()
        agent._prewarm_last_attempt_at = None
        calls = {"n": 0}

        async def counting_prewarm():
            calls["n"] += 1

        agent._prewarm_async = counting_prewarm
        agent._schedule_prewarm()
        await asyncio.sleep(0.01)  # 让任务跑完
        agent._schedule_prewarm()  # 冷却期内 → 第二次被跳过
        assert calls["n"] == 1

    def test_no_llm_skips(self):
        from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2

        agent = object.__new__(AgentV2)
        agent._llm = None
        agent._prewarm_last_attempt_at = None
        agent._schedule_prewarm()  # 无 llm → 直接返回，不创建任务
        assert agent._prewarm_last_attempt_at is None
