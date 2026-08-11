"""B10: 单 agent 桥接层 —— AgentBridge 基类 / ACP 适配器 / CLI 兜底 / 生命周期。

完成判据对应：
1. 委托/流式/回收/超时 kill 测试通过
2. 桥接前后 cache_rate 不降（真实数字记录）
3. token/时间预算超限即 kill（测试）
4. run_official_agent 默认禁用，/bridge 命令可用
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest


# ============================================================================
# 完成判据 1：委托/流式/回收/超时 kill
# ============================================================================


def test_bridge_config_defaults():
    """BridgeConfig 默认预算（token 5万/时间 300s/截断 2000 字符）。"""
    from RxyCode.RxyCode1_1_0.core.bridge.base import BridgeConfig

    cfg = BridgeConfig()
    assert cfg.token_budget == 50_000
    assert cfg.time_budget_s == 300.0
    assert cfg.max_result_chars == 2000


def test_agent_bridge_abstract():
    """AgentBridge 是抽象基类（不能直接实例化）。"""
    from RxyCode.RxyCode1_1_0.core.bridge.base import AgentBridge, BridgeConfig

    with pytest.raises(TypeError):
        AgentBridge(BridgeConfig())


class _FakeACPProcess:
    """模拟子进程：预置 stdin/stdout 行为。"""

    def __init__(self, responses: list[dict]):
        self._responses = responses
        self._written: list[str] = []
        self.returncode: int | None = None
        self.killed = False
        self.stdin = _FakeStdin(self._written)
        self.stdout = _FakeStdout(self._responses)
        self.stderr = _FakeStdout([])

    def kill(self):
        self.killed = True
        self.returncode = 1

    async def wait(self):
        return self.returncode


class _FakeStdin:
    def __init__(self, written: list[str]):
        self._written = written

    def write(self, data: bytes):
        self._written.append(data.decode("utf-8"))

    async def drain(self):
        return None


class _FakeStdout:
    def __init__(self, responses: list[dict], *, hang: bool = False):
        self._lines = [json.dumps(r) + "\n" for r in responses]
        self._hang = hang

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._hang:
            await asyncio.sleep(3600)  # 永不返回（模拟挂起）
        if self._index >= len(self._lines):
            raise StopAsyncIteration
        line = self._lines[self._index]
        self._index += 1
        return line.encode("utf-8")


def _acp_responses():
    return [
        {"method": "agent_message_chunk", "params": {"text": "working..."}},
        {"method": "tool_call", "params": {"name": "grep", "args": {}}},
        {"method": "session/result", "params": {"result": "final answer"}},
    ]


def test_acp_bridge_spawn_and_invoke(monkeypatch):
    """ACP 适配器：spawn → invoke 流式事件 → 回收结果。"""
    from RxyCode.RxyCode1_1_0.core.bridge.acp import ACPBridge

    proc = _FakeACPProcess(_acp_responses())

    async def fake_spawn(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio.subprocess, "PIPE", object())

    async def run():
        bridge = ACPBridge()
        await bridge.start()
        events = []
        async for ev in bridge.invoke("scan repo"):
            events.append(ev)
        return events, bridge

    events, bridge = asyncio.run(run())
    assert [e["type"] for e in events] == [
        "agent_message_chunk", "tool_call", "result",
    ]
    assert events[-1]["content"] == "final answer"
    # 请求已写入 stdin（JSON-RPC session/new_prompt）
    assert any("session/new_prompt" in w for w in proc._written)


def test_cli_bridge_spawn_and_stream(monkeypatch):
    """CLI 兜底适配器：spawn grok agent stdio → 流式事件。"""
    from RxyCode.RxyCode1_1_0.core.bridge.cli import CLIBridge

    proc = _FakeACPProcess([
        {"type": "agent_message_chunk", "content": "scanning"},
        {"type": "result", "content": "done"},
    ])

    async def fake_spawn(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio.subprocess, "PIPE", object())

    async def run():
        bridge = CLIBridge(cmd=["grok", "agent", "stdio"])
        await bridge.start()
        events = []
        async for ev in bridge.invoke("task"):
            events.append(ev)
        return events

    events = asyncio.run(run())
    assert [e["type"] for e in events] == ["agent_message_chunk", "result"]


def test_run_official_agent_result_flow(monkeypatch):
    """run_official_agent 编排：start → invoke → 回收结果（截断后返回）。"""
    from RxyCode.RxyCode1_1_0.core.bridge.base import BridgeConfig
    from RxyCode.RxyCode1_1_0.core.bridge.lifecycle import run_official_agent

    proc = _FakeACPProcess([
        {"method": "agent_message_chunk", "params": {"text": "step1"}},
        {"method": "session/result", "params": {"result": "final summary"}},
    ])

    async def fake_spawn(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio.subprocess, "PIPE", object())

    async def run():
        cfg = BridgeConfig(max_result_chars=100)
        from RxyCode.RxyCode1_1_0.core.bridge.acp import ACPBridge

        result = await run_official_agent(ACPBridge(cfg), "task")
        return result

    result = asyncio.run(run())
    assert "final summary" in result
    assert len(result) <= 100


def test_run_official_agent_timeout_kills(monkeypatch):
    """超时 → 子进程被 kill，返回超时提示（不留僵尸进程）。"""
    from RxyCode.RxyCode1_1_0.core.bridge.base import BridgeConfig
    from RxyCode.RxyCode1_1_0.core.bridge.lifecycle import run_official_agent

    proc = _FakeACPProcess([])  # 无响应 → 挂起直到超时
    proc.killed = False
    proc.stdout = _FakeStdout([], hang=True)  # 挂起

    async def fake_spawn(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio.subprocess, "PIPE", object())

    async def run():
        cfg = BridgeConfig(time_budget_s=0.05, token_budget=10_000)
        from RxyCode.RxyCode1_1_0.core.bridge.acp import ACPBridge

        result = await run_official_agent(ACPBridge(cfg), "task")
        return result, proc

    result, proc = asyncio.run(run())
    assert "time budget" in result or "budget" in result
    assert proc.killed is True


def test_stop_kills_process(monkeypatch):
    """stop() 对运行中的进程执行 kill。"""
    from RxyCode.RxyCode1_1_0.core.bridge.acp import ACPBridge

    proc = _FakeACPProcess([])
    proc.returncode = None  # 运行中

    async def fake_spawn(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio.subprocess, "PIPE", object())

    async def run():
        bridge = ACPBridge()
        await bridge.start()
        await bridge.stop()
        return proc

    proc = asyncio.run(run())
    assert proc.killed is True


# ============================================================================
# 完成判据 3：token/时间预算超限即 kill
# ============================================================================


def test_token_budget_exceeded_kills(monkeypatch):
    """token 预算超限 → kill（usage 归一化后累计超预算）。"""
    from RxyCode.RxyCode1_1_0.core.bridge.base import BridgeConfig
    from RxyCode.RxyCode1_1_0.core.bridge.lifecycle import run_official_agent

    # ACP 格式：usage 在 params 里（超大 → 首个事件即超预算）
    big_chunk = {
        "method": "agent_message_chunk",
        "params": {
            "text": "x",
            "usage": {"input": 60000, "output": 100},
        },
    }
    proc = _FakeACPProcess([big_chunk])

    async def fake_spawn(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio.subprocess, "PIPE", object())

    async def run():
        cfg = BridgeConfig(token_budget=1_000, time_budget_s=30)
        from RxyCode.RxyCode1_1_0.core.bridge.acp import ACPBridge

        result = await run_official_agent(ACPBridge(cfg), "task")
        return result, proc

    result, proc = asyncio.run(run())
    assert "budget" in result
    assert proc.killed is True


# ============================================================================
# 完成判据 4：run_official_agent 默认禁用 + /bridge 命令
# ============================================================================


def test_run_official_agent_tool_default_disabled():
    """配置默认：bridge 工具默认禁用（CB8）。"""
    from RxyCode.RxyCode1_1_0.config.settings import _default_config

    exec_cfg = _default_config()["execution"]
    assert exec_cfg.get("run_official_agent_enabled") is False


def test_run_official_agent_tool_registered_when_enabled():
    """启用时注册 run_official_agent 工具（subagent_task_tool 模式）。"""
    from RxyCode.RxyCode1_1_0.core.builtin_tool_registration import (
        register_builtin_tools,
    )
    from RxyCode.RxyCode1_1_0.execution.tool_orchestrator import ToolOrchestrator
    from RxyCode.RxyCode1_1_0.tools.registry import ToolRegistry

    registry = ToolRegistry()
    orch = ToolOrchestrator()
    register_builtin_tools(
        registry,
        orch,
        rag_enabled=False,
        subagents_enabled=False,
        run_official_agent_enabled=True,
    )
    assert "run_official_agent" in registry.get_names()


def test_run_official_agent_tool_not_registered_when_disabled():
    """禁用时不注册（默认路径工具集不变，CB8）。"""
    from RxyCode.RxyCode1_1_0.core.builtin_tool_registration import (
        register_builtin_tools,
    )
    from RxyCode.RxyCode1_1_0.execution.tool_orchestrator import ToolOrchestrator
    from RxyCode.RxyCode1_1_0.tools.registry import ToolRegistry

    registry = ToolRegistry()
    orch = ToolOrchestrator()
    register_builtin_tools(
        registry,
        orch,
        rag_enabled=False,
        subagents_enabled=False,
        run_official_agent_enabled=False,
    )
    assert "run_official_agent" not in registry.get_names()


def test_bridge_command_available():
    """api_server 有 /bridge 命令分支。"""
    import inspect

    from RxyCode.RxyCode1_1_0 import api_server

    src = inspect.getsource(api_server._execute_command)
    assert 'c == "/bridge"' in src or 'c == "/bridge ' in src


# ============================================================================
# 完成判据 2：主链路前缀零污染
# ============================================================================


def test_bridge_supports_usage_normalization():
    """桥接 usage 经 B9 契约归一化（不散落 if-elif）。"""
    from RxyCode.RxyCode1_1_0.core.catalog import read_cached_tokens

    # 桥接子进程的 usage 格式未知 → 归一到 0（不误报），
    # 但主链路 token_stats 不受桥接影响（独立子进程）。
    assert read_cached_tokens("unknown-bridge", "claude", {}) == 0


def test_bridge_does_not_touch_main_token_stats(monkeypatch):
    """桥接运行不修改主链路 token_stats（前缀零污染前提）。"""
    from RxyCode.RxyCode1_1_0.core.bridge.base import BridgeConfig
    from RxyCode.RxyCode1_1_0.core.bridge.lifecycle import run_official_agent
    from RxyCode.RxyCode1_1_0.utils.streaming import token_stats

    proc = _FakeACPProcess([
        {"method": "agent_message_chunk", "params": {"text": "x"}},
        {"method": "session/result", "params": {"result": "done"}},
    ])

    async def fake_spawn(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio.subprocess, "PIPE", object())

    before_input = token_stats.input_tokens
    before_hit = token_stats.cache_hit_tokens

    async def run():
        cfg = BridgeConfig()
        from RxyCode.RxyCode1_1_0.core.bridge.acp import ACPBridge

        await run_official_agent(ACPBridge(cfg), "task")

    asyncio.run(run())
    # 桥接不写入主链路 token_stats
    assert token_stats.input_tokens == before_input
    assert token_stats.cache_hit_tokens == before_hit


# ============================================================================
# luna R1 修复对应测试
# ============================================================================


def test_event_token_cost_single_authoritative_field():
    """usage 归一化：同义字段并存时不重复计数（luna R1-4）。"""
    from RxyCode.RxyCode1_1_0.core.bridge.lifecycle import _event_token_cost

    # input_tokens 权威字段优先（input 同义不叠加）
    ev = {"type": "chunk", "usage": {"input_tokens": 100, "input": 500}}
    assert _event_token_cost(ev) == 100
    # 无权威字段用 total（不叠加）
    ev2 = {"type": "chunk", "usage": {"total": 300, "input": 200, "output": 100}}
    assert _event_token_cost(ev2) == 300
    # input/output 单取其一
    ev3 = {"type": "chunk", "usage": {"input": 200, "output": 100}}
    assert _event_token_cost(ev3) == 200


def test_bridge_usage_reads_b9_contract():
    """桥接 usage() 按 B9 契约归一化（luna R1-1）。"""
    from RxyCode.RxyCode1_1_0.core.bridge.base import BridgeConfig
    from RxyCode.RxyCode1_1_0.core.bridge.acp import ACPBridge

    bridge = ACPBridge(cfg=BridgeConfig(provider="grok", model="grok-4.5"))
    usage = bridge.usage()
    # grok 契约的 usage_fields
    assert usage["cached_field"] == "cached_prompt_text_tokens"
    assert usage["cost_ticks_field"] == "cost_in_usd_ticks"
    assert usage["cache_mode"] == "auto"

    # 未配置 model → 空（CB8）
    empty = ACPBridge(cfg=BridgeConfig()).usage()
    assert empty == {}


def test_result_hard_limit_enforced():
    """结果摘要硬上限 4000（调用方传大值也不突破，luna R1-5）。"""
    from RxyCode.RxyCode1_1_0.core.bridge.base import BridgeConfig
    from RxyCode.RxyCode1_1_0.core.bridge.lifecycle import (
        MAX_RESULT_CHARS_HARD_LIMIT,
        run_official_agent,
    )

    big_result = {
        "method": "session/result",
        "params": {"result": "x" * 100_000},
    }
    proc = _FakeACPProcess([big_result])

    async def fake_spawn(*args, **kwargs):
        return proc

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    monkeypatch.setattr(asyncio.subprocess, "PIPE", object())

    async def run():
        cfg = BridgeConfig(max_result_chars=100_000)  # 调用方传超大值
        from RxyCode.RxyCode1_1_0.core.bridge.acp import ACPBridge

        return await run_official_agent(ACPBridge(cfg), "task")

    result = asyncio.run(run())
    monkeypatch.undo()
    assert len(result) <= MAX_RESULT_CHARS_HARD_LIMIT