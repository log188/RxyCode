"""
Tests for LLM call timeout guard (2026-08-13 fix).

Root cause fixed: LLM streaming establishment (`first = await ait.__anext__()`)
and the raw OpenAI client had no effective first-response deadline, so an
upstream hang produced 0-token stalls that appserver's watchdog killed first.
Now the total request timeout remains configurable, while the first response
deadline is independently bounded to 30 seconds (or a shorter model setting):
  - UsageTrackingLLM gains `llm_timeout` and a bounded first-token timeout
  - `_open_stream` / `_open_stream_with_retry` wrap first-chunk wait
  - `AgentV2._raw_stream` uses the same bounded deadline
  - a first-token timeout is not retried as a blind transport retry
"""
import asyncio
import pytest
from unittest.mock import MagicMock


def _make_usage_llm(timeout=90.0):
    from RxyCode.RxyCode1_1_0.core.agent_v2 import UsageTrackingLLM
    llm = object.__new__(UsageTrackingLLM)
    llm._llm_timeout = max(1.0, float(timeout))
    llm._first_token_timeout = min(llm._llm_timeout, 30.0)
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

    def test_first_token_timeout_is_bounded_and_can_only_be_shorter(self):
        from RxyCode.RxyCode1_1_0.core.agent_v2 import _resolve_first_token_timeout

        assert _resolve_first_token_timeout(90) == 30.0
        assert _resolve_first_token_timeout(90, 12) == 12.0
        assert _resolve_first_token_timeout(90, 45) == 30.0
        assert _resolve_first_token_timeout(10) == 10.0

    def test_stream_idle_timeout_is_bounded_and_can_only_be_shorter(self):
        from RxyCode.RxyCode1_1_0.core.agent_v2 import _resolve_stream_idle_timeout

        assert _resolve_stream_idle_timeout(90) == 15.0
        assert _resolve_stream_idle_timeout(90, 12) == 12.0
        assert _resolve_stream_idle_timeout(90, 45) == 30.0
        assert _resolve_stream_idle_timeout(10) == 10.0


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
    async def test_first_token_hang_does_not_repeat_the_same_stall(self):
        llm = _make_usage_llm(timeout=2)
        llm._transport_retries = 1  # total 2 attempts
        llm._llm = MagicMock()
        llm._llm.astream.return_value = FakeHangingStream()
        calls = {"n": 0}
        original = llm._llm.astream

        def counted(*args, **kwargs):
            calls["n"] += 1
            return original(*args, **kwargs)

        llm._llm.astream = counted
        start = asyncio.get_event_loop().time()
        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await llm._open_stream_with_retry([], {})
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 6.0
        assert calls["n"] == 1

    async def test_transport_reset_still_recovers_on_second_attempt(self):
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
                    raise ConnectionError("stream reset")
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


class TestRawStreamFirstChunkTimeout:
    """_fast_reply uses _raw_stream, which previously had no first-chunk wait_for.

    A silent thinking hang then lost the race to the 120s appserver watchdog.
    """

    async def test_hanging_first_chunk_raises_timeout(self, monkeypatch):
        from types import SimpleNamespace

        from RxyCode.RxyCode1_1_0.core import agent_v2
        from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2
        from langchain_core.messages import HumanMessage

        monkeypatch.setattr(
            agent_v2._circuit_breaker, "circuit_breaker_enabled", lambda: False
        )

        class HangingCompletions:
            async def create(self, **_kwargs):
                class Stream:
                    def __aiter__(self):
                        return self

                    async def __anext__(self):
                        await asyncio.Event().wait()

                return Stream()

        agent = object.__new__(AgentV2)
        agent.model_config = {"timeout": 1.0, "model_name": "x", "temperature": 0}
        agent._llm = SimpleNamespace()
        agent._rate_limiter = None
        agent._provider = None
        agent._capabilities = None
        agent._openai_client = lambda: HangingCompletions()

        async def drain() -> None:
            async for _chunk in agent._raw_stream(
                [HumanMessage(content="hi")], max_tokens=1
            ):
                pass

        start = asyncio.get_event_loop().time()
        try:
            await asyncio.wait_for(drain(), timeout=8.0)
            pytest.fail("_raw_stream completed without a first-chunk timeout")
        except (asyncio.TimeoutError, TimeoutError):
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed >= 7.0:
                pytest.fail(
                    "_raw_stream first-chunk wait is unbounded; hung until the test watchdog"
                )
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 6.0

    async def test_partial_stream_cannot_wait_forever_for_next_chunk(self, monkeypatch):
        """A response that starts and then goes silent has its own deadline."""
        from types import SimpleNamespace

        from RxyCode.RxyCode1_1_0.core import agent_v2
        from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2, StreamIdleTimeoutError
        from langchain_core.messages import HumanMessage

        monkeypatch.setattr(
            agent_v2._circuit_breaker, "circuit_breaker_enabled", lambda: False
        )

        first = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="partial", reasoning_content="")
                )
            ]
        )

        class PartialHangingStream:
            def __init__(self):
                self._first = True

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._first:
                    self._first = False
                    return first
                await asyncio.Event().wait()

        class Completions:
            async def create(self, **_kwargs):
                return PartialHangingStream()

        agent = object.__new__(AgentV2)
        agent.model_config = {
            "timeout": 5.0,
            "stream_idle_timeout": 1.0,
            "model_name": "x",
            "temperature": 0,
        }
        agent._llm = SimpleNamespace()
        agent._rate_limiter = None
        agent._provider = None
        agent._capabilities = None
        agent._openai_client = lambda: Completions()

        async def drain() -> None:
            async for _chunk in agent._raw_stream(
                [HumanMessage(content="hi")], max_tokens=1
            ):
                pass

        start = asyncio.get_event_loop().time()
        with pytest.raises(StreamIdleTimeoutError):
            await drain()
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 4.0


class TestFastReplyDisablesThinking:
    async def test_raw_stream_forces_thinking_disabled(self, monkeypatch):
        from types import SimpleNamespace

        from RxyCode.RxyCode1_1_0.core import agent_v2
        from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2
        from langchain_core.messages import HumanMessage

        monkeypatch.setattr(
            agent_v2._circuit_breaker, "circuit_breaker_enabled", lambda: False
        )
        captured: dict = {}

        class Completions:
            async def create(self, **kwargs):
                captured.update(kwargs)

                class Stream:
                    def __aiter__(self):
                        return self

                    async def __anext__(self):
                        raise StopAsyncIteration

                return Stream()

        class Provider:
            def llm_kwargs(self, model_config, caps):
                return {"extra_body": {"thinking": {"type": "enabled"}}}

        agent = object.__new__(AgentV2)
        agent.model_config = {"timeout": 5.0, "model_name": "deepseek-v4-flash"}
        agent._llm = SimpleNamespace()
        agent._rate_limiter = None
        agent._provider = Provider()
        agent._capabilities = SimpleNamespace(
            provider="deepseek", prompt_cache_key_required=False
        )
        agent._thinking_disabled_this_turn = True
        agent._openai_client = lambda: Completions()

        async for _chunk in agent._raw_stream(
            [HumanMessage(content="hi")], max_tokens=1
        ):
            pass
        assert captured["extra_body"]["thinking"] == {"type": "disabled"}


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
