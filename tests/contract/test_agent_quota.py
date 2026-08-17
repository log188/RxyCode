"""E5 contract tests: RXYCODE_AGENT_PARALLEL switch + cancel-storm limit.

Coverage per PHASE-E §5 E5:
- PARALLEL=1 (legacy serial): second spawn denied with event/agent_denied
- PARALLEL=2: up to two agents run in parallel; third is denied
- switch missing -> default 1; invalid values -> default 1
- cancel-storm: at most K concurrent cancel fan-outs, the rest queue
  (same-moment fan-out cap, §7 security)
"""

from __future__ import annotations

import asyncio

import pytest

from appserver.agent_runtime import AgentConfig, AgentRuntime, ParallelLimitError
from appserver.agent_task import LifecycleState
from appserver.eventbus import AppendOnlyLog, BusEvent, EventBus


def _bus() -> EventBus:
    return EventBus(AppendOnlyLog())


def _ok_run(cfg):
    async def run(task, checkpoint=None):
        return "ok"

    return run


async def _drain_events(
    bus: EventBus, count: int, timeout: float = 2.0, sub=None
) -> list[BusEvent]:
    if sub is None:
        sub = await bus.subscribe("test", "event/*")
    got: list[BusEvent] = []
    for _ in range(count):
        try:
            got.append(await asyncio.wait_for(sub.queue.get(), timeout=timeout))
        except asyncio.TimeoutError:
            break
    return got


@pytest.mark.asyncio
async def test_parallel_1_denies_second_spawn(monkeypatch):
    monkeypatch.setenv("RXYCODE_AGENT_PARALLEL", "1")
    bus = _bus()
    sub = await bus.subscribe("test", "event/*")
    rt = AgentRuntime(bus, run_factory=_ok_run)

    await rt.spawn(AgentConfig(agent_id="A", tools=()))
    with pytest.raises(ParallelLimitError):
        await rt.spawn(AgentConfig(agent_id="B", tools=()))
    assert "B" not in rt.agents

    evs = await _drain_events(bus, 2, sub=sub)
    methods = [e.method for e in evs]
    assert "event/agent_started" in methods
    assert "event/agent_denied" in methods


@pytest.mark.asyncio
async def test_parallel_2_allows_two_and_denies_third(monkeypatch):
    monkeypatch.setenv("RXYCODE_AGENT_PARALLEL", "2")
    rt = AgentRuntime(_bus(), run_factory=_ok_run)

    await rt.spawn(AgentConfig(agent_id="A", tools=()))
    await rt.spawn(AgentConfig(agent_id="B", tools=()))
    with pytest.raises(ParallelLimitError):
        await rt.spawn(AgentConfig(agent_id="C", tools=()))
    assert set(rt.agents) == {"A", "B"}


@pytest.mark.asyncio
async def test_parallel_defaults_to_1(monkeypatch):
    monkeypatch.delenv("RXYCODE_AGENT_PARALLEL", raising=False)
    rt = AgentRuntime(_bus(), run_factory=_ok_run)
    await rt.spawn(AgentConfig(agent_id="A", tools=()))
    with pytest.raises(ParallelLimitError):
        await rt.spawn(AgentConfig(agent_id="B", tools=()))


@pytest.mark.asyncio
async def test_parallel_invalid_falls_back_to_1(monkeypatch):
    monkeypatch.setenv("RXYCODE_AGENT_PARALLEL", "banana")
    rt = AgentRuntime(_bus(), run_factory=_ok_run)
    await rt.spawn(AgentConfig(agent_id="A", tools=()))
    with pytest.raises(ParallelLimitError):
        await rt.spawn(AgentConfig(agent_id="B", tools=()))


@pytest.mark.asyncio
async def test_denied_agent_can_spawn_after_stop(monkeypatch):
    monkeypatch.setenv("RXYCODE_AGENT_PARALLEL", "1")
    rt = AgentRuntime(_bus(), run_factory=_ok_run)
    task = await rt.spawn(AgentConfig(agent_id="A", tools=()))
    await task.wait_state(LifecycleState.DONE)
    await rt.stop("A", reason="done")

    await rt.spawn(AgentConfig(agent_id="B", tools=()))  # slot freed
    assert "B" in rt.agents


@pytest.mark.asyncio
async def test_cancel_storm_caps_concurrent_fanout():
    bus = _bus()
    started = asyncio.Event()

    async def forever_run(task, checkpoint=None):
        started.set()
        await asyncio.Event().wait()

    rt = AgentRuntime(bus, run_factory=lambda cfg: forever_run, parallel_limit=5, cancel_storm_limit=2)
    agents = []
    for i in range(5):
        task = await rt.spawn(AgentConfig(agent_id=f"A{i}", tools=()))
        agents.append(task)
        await asyncio.sleep(0.02)
        await started.wait()

    active = {"n": 0, "max": 0}
    orig_cancel = rt.cancel_process_trees

    async def slow_cancel(agent_id: str) -> None:
        active["n"] += 1
        active["max"] = max(active["max"], active["n"])
        await asyncio.sleep(0.05)
        active["n"] -= 1
        await orig_cancel(agent_id)

    rt.cancel_process_trees = slow_cancel  # type: ignore[method-assign]

    await asyncio.gather(*(rt.stop(f"A{i}", reason="storm") for i in range(5)))
    assert active["max"] <= 2  # storm cap enforced


@pytest.mark.asyncio
async def test_cancel_storm_all_stops_eventually_complete():
    rt = AgentRuntime(_bus(), run_factory=lambda cfg: _forever, parallel_limit=4, cancel_storm_limit=2)
    for i in range(4):
        await rt.spawn(AgentConfig(agent_id=f"A{i}", tools=()))
        await asyncio.sleep(0.01)

    await asyncio.gather(*(rt.stop(f"A{i}", reason="storm") for i in range(4)))
    assert all(a not in rt.agents for a in ("A0", "A1", "A2", "A3"))


async def _forever(task, checkpoint=None):
    await asyncio.Event().wait()
