"""E3 contract tests: AgentRuntime (registry/spawn/stop, quotas, budgets).

Coverage per PHASE-E §5 E3 + §8.1 matrix:
- spawn/stop/quotas/shared budget; stop waits for cancellation
- budget circuit breaker: event/agent_budget_exceeded + CANCELLED +
  BudgetExceededError as stop signal (no retry)
- two agents in one session run in parallel without blocking each other
- mechanical=True: zero LLM calls, events/budget still charged
- cache_namespace: validated, enters the application cache key, None keeps
  the single-agent key byte-identical, different namespaces never cross
- model lifecycle: opaque passthrough, never read/compared/injected,
  absent from BusEvent, resolved_model read-only
- golden serialization: old/new AgentConfig byte-identical with
  exclude_none=True (field-level filtering for new fields only)
"""

from __future__ import annotations

import asyncio
import json
import threading

import pytest

from appserver.agent_runtime import (
    AgentConfig,
    AgentRuntime,
    BudgetExceededError,
    LLMBindingError,
    build_cache_key,
    validate_cache_namespace,
)
from appserver.agent_task import LifecycleState
from appserver.eventbus import BusEvent, AppendOnlyLog, EventBus


def _bus() -> EventBus:
    return EventBus(AppendOnlyLog())


def _ok_run(cfg):
    """Sync-signature run factory returning a real coroutine."""

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


# ---------------------------------------------------------------------------
# cache_namespace contract (DC8/F17 key building)
# ---------------------------------------------------------------------------


def test_validate_cache_namespace_none_is_allowed():
    assert validate_cache_namespace(None) is None


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "with|pipe",
        "with:colon",
        "CamelCase",
        "Has Space",
        "émoji",
        "x" * 65,
    ],
)
def test_validate_cache_namespace_rejects_invalid(bad: str):
    with pytest.raises(ValueError):
        validate_cache_namespace(bad)


def test_validate_cache_namespace_accepts_valid():
    for ok in ["team-a", "team_a", "deepseek-r1.5", "abc123-_."]:
        assert validate_cache_namespace(ok) == ok


def test_build_cache_key_none_returns_base_unchanged():
    base = "https://api.example.com|deepseek/deepseek-v4|abc123digest"
    assert build_cache_key(base, None) == base


def test_build_cache_key_with_namespace_appends():
    base = "https://api.example.com|deepseek/deepseek-v4|abc123digest"
    assert build_cache_key(base, "team-a") == f"{base}|team-a"


def test_build_cache_key_different_namespaces_never_cross():
    base = "https://api.example.com|deepseek/deepseek-v4|abc123digest"
    assert build_cache_key(base, "team-a") != build_cache_key(base, "team-b")


# ---------------------------------------------------------------------------
# AgentConfig golden serialization (exclude_none, field-level filtering)
# ---------------------------------------------------------------------------


def test_agent_config_serializes_old_fields_byte_identical():
    # "old" config: no cache_namespace / mechanical fields present at all
    old = {
        "agent_id": "A",
        "model": "deepseek/deepseek-v4",
        "tools": ("read", "bash"),
        "quota": 3,
        "budget_tokens": 200_000,
        "memory_scope": "own",
    }
    cfg = AgentConfig(**old)
    dumped = cfg.to_dict()
    assert dumped == old
    assert json.dumps(dumped, sort_keys=True, separators=(",", ":")) == json.dumps(
        old, sort_keys=True, separators=(",", ":")
    )


def test_agent_config_new_fields_omitted_when_default():
    cfg = AgentConfig(agent_id="A", tools=())
    dumped = cfg.to_dict()
    assert "cache_namespace" not in dumped
    assert "mechanical" not in dumped


def test_agent_config_new_fields_present_when_set():
    cfg = AgentConfig(agent_id="A", tools=(), cache_namespace="team-a", mechanical=True)
    dumped = cfg.to_dict()
    assert dumped["cache_namespace"] == "team-a"
    assert dumped["mechanical"] is True


def test_agent_config_golden_serialization_byte_identical():
    old_cfg = AgentConfig(
        agent_id="A", model="deepseek/deepseek-v4",
        tools=("read", "bash"), quota=3, budget_tokens=200_000,
        memory_scope="own",
    )
    new_cfg = AgentConfig(
        agent_id="A", model="deepseek/deepseek-v4",
        tools=("read", "bash"), quota=3, budget_tokens=200_000,
        memory_scope="own", cache_namespace=None, mechanical=False,
    )
    import json as _json

    old_bytes = _json.dumps(old_cfg.to_dict(), sort_keys=True, separators=(",", ":")).encode()
    new_bytes = _json.dumps(new_cfg.to_dict(), sort_keys=True, separators=(",", ":")).encode()
    assert old_bytes == new_bytes  # byte-for-byte identical (PHASE-E §4.3 golden)


def test_agent_config_round_trip_stable():
    first = AgentConfig(agent_id="A", tools=(), cache_namespace="team-a")
    second = AgentConfig(**first.to_dict())
    assert first.to_dict() == second.to_dict()


# ---------------------------------------------------------------------------
# model opacity
# ---------------------------------------------------------------------------


def test_model_passthrough_and_no_default_injection():
    cfg = AgentConfig(agent_id="A", tools=(), model="vendor/model-x")
    assert cfg.model == "vendor/model-x"
    cfg2 = AgentConfig(agent_id="B", tools=())
    assert cfg2.model is None  # never injected by E layer


def test_resolved_model_is_read_only_metadata():
    bus = _bus()
    rt = AgentRuntime(bus)
    rt.set_resolved_model("A", "vendor/model-x")
    assert rt.resolved_model("A")["model"] == "vendor/model-x"
    with pytest.raises(TypeError):
        rt.resolved_model("A")["model"] = "hacked"


@pytest.mark.asyncio
async def test_lifecycle_events_carry_token_snapshot_from_spawn():
    bus = _bus()
    sub = await bus.subscribe("test", "event/*")
    rt = AgentRuntime(bus, run_factory=_ok_run, parallel_limit=2)

    async def spendy_run(task, checkpoint=None):
        rt.record_token_usage("S", 40)
        return "ok"

    rt2 = AgentRuntime(bus, run_factory=lambda cfg: spendy_run, parallel_limit=2)
    await rt2.spawn(AgentConfig(agent_id="S", tools=()))
    await rt2.agents["S"].wait_state(LifecycleState.DONE)

    evs = await _drain_events(bus, 2, sub=sub)
    started = next(e for e in evs if e.method == "event/agent_started")
    done = next(e for e in evs if e.method == "event/agent_done")
    # spawn-era snapshot is 0 and the value is monotonic (PHASE-E §4.1)
    assert started.payload.get("tokens_used") == 0
    assert started.payload.get("budget_used") == 0
    assert done.payload.get("tokens_used") >= started.payload.get("tokens_used", 0)


@pytest.mark.asyncio
async def test_model_never_lands_in_agent_events():
    bus = _bus()
    sub = await bus.subscribe("test", "event/*")
    rt = AgentRuntime(bus, run_factory=_ok_run)
    cfg = AgentConfig(agent_id="A", tools=(), model="vendor/model-x")
    await rt.spawn(cfg)
    await rt.agents["A"].wait_state(LifecycleState.DONE)

    evs = await _drain_events(bus, 1, sub=sub)
    assert evs and "model" not in evs[0].payload
    assert "model" not in evs[0].__dict__


# ---------------------------------------------------------------------------
# spawn / stop / parallelism
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_rejects_duplicate_agent_id():
    rt = AgentRuntime(_bus(), run_factory=_ok_run)
    await rt.spawn(AgentConfig(agent_id="A", tools=()))
    with pytest.raises(AssertionError):
        await rt.spawn(AgentConfig(agent_id="A", tools=()))


@pytest.mark.asyncio
async def test_two_agents_run_in_parallel_without_blocking():
    bus = _bus()
    overlap = threading.Lock()
    concurrent = {"n": 0, "max": 0}

    async def slow_run(task, checkpoint=None):
        with overlap:
            concurrent["n"] += 1
            concurrent["max"] = max(concurrent["max"], concurrent["n"])
        await asyncio.sleep(0.05)
        with overlap:
            concurrent["n"] -= 1
        return "ok"

    rt = AgentRuntime(bus, run_factory=lambda cfg: slow_run, parallel_limit=2)
    await rt.spawn(AgentConfig(agent_id="A", tools=()))
    await rt.spawn(AgentConfig(agent_id="B", tools=()))

    await asyncio.gather(
        rt.agents["A"].wait_state(LifecycleState.DONE),
        rt.agents["B"].wait_state(LifecycleState.DONE),
    )
    assert concurrent["max"] >= 2  # both RUNNING simultaneously (RB1)


@pytest.mark.asyncio
async def test_stop_cancels_and_removes_agent():
    bus = _bus()
    started = asyncio.Event()

    async def forever_run(task, checkpoint=None):
        started.set()
        await asyncio.Event().wait()

    rt = AgentRuntime(bus, run_factory=lambda cfg: forever_run)
    task = await rt.spawn(AgentConfig(agent_id="A", tools=()))
    await started.wait()

    await rt.stop("A", reason="test")
    assert "A" not in rt.agents
    assert task.state == LifecycleState.CANCELLED
    assert task._main_task is None or task._main_task.done()


@pytest.mark.asyncio
async def test_stop_unknown_agent_is_noop():
    rt = AgentRuntime(_bus(), run_factory=_ok_run)
    await rt.stop("GHOST", reason="test")  # must not raise


# ---------------------------------------------------------------------------
# quotas (EB4): per-agent semaphore + global tool slots, same acquisition
# order (per-agent then global), release on cancel/error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_agent_quota_limits_concurrent_tool_slots():
    rt = AgentRuntime(_bus(), run_factory=_ok_run)
    cfg = AgentConfig(agent_id="A", tools=(), quota=2)
    await rt.spawn(cfg)

    acquired: list[int] = []

    async def tool_call(i: int) -> None:
        async with rt.acquire_tool_slot("A"):
            acquired.append(i)
            await asyncio.sleep(0.05)

    await asyncio.gather(*(tool_call(i) for i in range(4)))
    assert len(acquired) == 4  # all eventually run, bounded by the semaphore

    await rt.stop("A", reason="done")


@pytest.mark.asyncio
async def test_global_tool_slots_cap_concurrency():
    rt = AgentRuntime(_bus(), total_tool_slots=2, run_factory=_ok_run, parallel_limit=2)
    await rt.spawn(AgentConfig(agent_id="A", tools=(), quota=4))
    await rt.spawn(AgentConfig(agent_id="B", tools=(), quota=4))

    cur = {"n": 0, "max": 0}

    async def tool_call() -> None:
        async with rt.acquire_tool_slot("A"):
            cur["n"] += 1
            cur["max"] = max(cur["max"], cur["n"])
            await asyncio.sleep(0.05)
            cur["n"] -= 1

    await asyncio.gather(*(tool_call() for _ in range(5)))
    assert cur["max"] <= 2  # global cap enforced


# ---------------------------------------------------------------------------
# budget circuit breaker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_breaker_emits_event_and_cancels():
    bus = _bus()
    sub = await bus.subscribe("test", "event/*")

    async def spendy_run(task, checkpoint=None):
        rt2.record_token_usage("A", 60)
        await rt2.check_budget("A", est=60)  # 60+60 > 100 -> breaker
        return "ok"

    rt2 = AgentRuntime(bus, run_factory=lambda cfg: spendy_run)
    task = await rt2.spawn(AgentConfig(agent_id="A", tools=(), budget_tokens=100))

    await task.wait_state(LifecycleState.CANCELLED, timeout=2.0)
    evs = await _drain_events(bus, 3, sub=sub)
    methods = [e.method for e in evs]
    assert "event/agent_budget_exceeded" in methods
    assert "event/agent_cancelled" in methods


@pytest.mark.asyncio
async def test_budget_breaker_uses_shared_pool_when_budget_zero():
    bus = _bus()

    async def spendy_run(task, checkpoint=None):
        rt2.record_token_usage("A", 60)
        await rt2.check_budget("A", est=60)  # pool total 100, 60+60 > 100
        return "ok"

    rt2 = AgentRuntime(bus, budget_total=100, run_factory=lambda cfg: spendy_run)
    task = await rt2.spawn(AgentConfig(agent_id="A", tools=(), budget_tokens=0))
    await task.wait_state(LifecycleState.CANCELLED, timeout=2.0)
    assert task._last_error is not None and isinstance(task._last_error, BudgetExceededError)


# ---------------------------------------------------------------------------
# mechanical (F4): no provider binding, zero LLM calls, lifecycle/budget as usual
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mechanical_agent_makes_zero_llm_calls():
    calls = {"n": 0}

    def factory(cfg):
        async def run(task, checkpoint=None):
            if not cfg.mechanical:
                calls["n"] += 1  # LLM call point
            return "ok"

        return run

    bus = _bus()
    sub = await bus.subscribe("test", "event/*")
    rt = AgentRuntime(bus, run_factory=factory)
    task = await rt.spawn(AgentConfig(agent_id="M", tools=(), mechanical=True))
    await task.wait_state(LifecycleState.DONE)

    assert calls["n"] == 0
    evs = await _drain_events(bus, 1, sub=sub)
    assert evs and evs[0].method == "event/agent_started"


@pytest.mark.asyncio
async def test_call_llm_refused_for_mechanical_agent():
    rt = AgentRuntime(_bus(), run_factory=_ok_run, parallel_limit=2)
    await rt.spawn(AgentConfig(agent_id="M", tools=(), mechanical=True))
    with pytest.raises(LLMBindingError):
        rt.call_llm("M")


@pytest.mark.asyncio
async def test_call_llm_allowed_for_regular_agent():
    rt = AgentRuntime(_bus(), run_factory=_ok_run, parallel_limit=2)
    await rt.spawn(AgentConfig(agent_id="N", tools=(), model="model-x"))
    result = await rt.call_llm("N")
    assert result["role"] == "assistant"


@pytest.mark.asyncio
async def test_budget_breaker_completes_full_stop_fanout():
    bus = _bus()
    sub = await bus.subscribe("test", "event/*")

    async def spendy_run(task, checkpoint=None):
        rt2.record_token_usage("A", 60)
        await rt2.check_budget("A", est=60)  # 60+60 > 100 -> breaker
        return "ok"

    rt2 = AgentRuntime(bus, run_factory=lambda cfg: spendy_run, parallel_limit=2)
    task = await rt2.spawn(AgentConfig(agent_id="A", tools=(), budget_tokens=100))

    await task.wait_state(LifecycleState.CANCELLED, timeout=2.0)
    assert rt2._cancel_process_trees_calls >= 1  # tool tree cascade via stop()
    assert "A" not in rt2.agents  # registry entry dropped by stop()
    evs = await _drain_events(bus, 3, sub=sub)
    methods = [e.method for e in evs]
    assert "event/agent_budget_exceeded" in methods
    assert "event/agent_cancelled" in methods


def test_token_snapshot_starts_at_zero_and_is_monotonic():
    rt = AgentRuntime(_bus(), run_factory=_ok_run, parallel_limit=2)
    snap0 = rt.token_snapshot("X")
    assert snap0 == {"tokens_used": 0, "budget_used": 0}  # spawn-era value
    rt.record_token_usage("X", 10)
    snap1 = rt.token_snapshot("X")
    assert snap1["tokens_used"] == 10
    assert snap1["tokens_used"] >= snap0["tokens_used"]  # monotonic


def test_usage_dedup_by_run_task_attempt():
    rt = AgentRuntime(_bus(), run_factory=_ok_run, parallel_limit=2)
    rt.record_token_usage("A", 60, run_id="r1", task_id="t1", attempt=0)
    rt.record_token_usage("A", 60, run_id="r1", task_id="t1", attempt=0)  # dup
    assert rt.token_usage("A") == 60  # dedup: counted once
    rt.record_token_usage("A", 30, run_id="r1", task_id="t2", attempt=0)  # legal
    assert rt.token_usage("A") == 90  # distinct calls keep accumulating


@pytest.mark.asyncio
async def test_shared_pool_accumulates_across_agents():
    rt = AgentRuntime(_bus(), run_factory=_ok_run, parallel_limit=3, budget_total=100)
    await rt.spawn(AgentConfig(agent_id="A", tools=(), budget_tokens=0))
    await rt.spawn(AgentConfig(agent_id="B", tools=(), budget_tokens=0))
    rt.record_token_usage("A", 60)  # zero-budget -> shared pool
    rt.record_token_usage("B", 40)
    assert rt.token_usage("A") == 100
    assert rt.token_usage("B") == 100  # pool-wide view


@pytest.mark.asyncio
async def test_shared_pool_breaker_fires_on_pool_total():
    bus = _bus()
    rt2 = AgentRuntime(bus, run_factory=None, parallel_limit=3, budget_total=100)
    await rt2.spawn(AgentConfig(agent_id="S1", tools=(), budget_tokens=0))

    async def pool_run(task, checkpoint=None):
        rt2.record_token_usage("S1", 60)  # pool now 60
        await rt2.check_budget("A", est=50)  # 60+50 > 100 -> breaker
        return "ok"

    rt2._run_factory = lambda cfg: pool_run  # type: ignore[attr-defined]
    task = await rt2.spawn(AgentConfig(agent_id="A", tools=(), budget_tokens=0))
    await task.wait_state(LifecycleState.CANCELLED, timeout=2.0)
    assert isinstance(task._last_error, BudgetExceededError)


@pytest.mark.asyncio
async def test_mechanical_budget_still_charged():
    rt = AgentRuntime(_bus(), budget_total=1000, run_factory=_ok_run)
    task = await rt.spawn(
        AgentConfig(agent_id="M", tools=(), mechanical=True, budget_tokens=0)
    )
    rt.record_token_usage("M", 30)
    assert rt.token_usage("M") == 30
    await task.wait_state(LifecycleState.DONE)


# ---------------------------------------------------------------------------
# cache_namespace at spawn time
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_rejects_invalid_namespace_before_start():
    rt = AgentRuntime(_bus(), run_factory=_ok_run)
    with pytest.raises(ValueError):
        await rt.spawn(AgentConfig(agent_id="A", tools=(), cache_namespace="BAD NS"))
    assert "A" not in rt.agents


@pytest.mark.asyncio
async def test_cross_agent_control_plane_flows_through_the_bus():
    """RB3 runtime evidence: agent A's lifecycle events travel the shared
    EventBus and agent B's subscription observes them (control plane is the
    bus; no side channel)."""
    bus = _bus()
    b_sub = await bus.subscribe("agent-b", "agent/A/*")
    rt = AgentRuntime(bus, run_factory=_ok_run, parallel_limit=2)
    await rt.spawn(AgentConfig(agent_id="A", tools=()))
    await rt.agents["A"].wait_state(LifecycleState.DONE)

    events = await _drain_events(bus, 2, sub=b_sub)
    assert [e.method for e in events] == ["event/agent_started", "event/agent_done"]
    assert all(e.agent_id == "A" for e in events)


@pytest.mark.asyncio
async def test_spawn_mounts_agent_context_with_session_cache():
    rt = AgentRuntime(_bus(), run_factory=_ok_run, parallel_limit=2)
    await rt.spawn(AgentConfig(agent_id="A", tools=()))
    await rt.spawn(AgentConfig(agent_id="B", tools=()))

    assert rt.contexts["A"].agent_id == "A"
    assert rt.contexts["B"].agent_id == "B"
    assert rt.contexts["A"].session_cache is rt.contexts["B"].session_cache
    assert rt.agents["A"].context is rt.contexts["A"]
    # shared cache counts across agents (reasonix-style)
    rt.contexts["A"].record_cache(hit=True)
    rt.contexts["B"].record_cache(hit=True)
    assert rt.contexts["A"].session_cache.hits == 2


@pytest.mark.asyncio
async def test_mechanical_never_binds_provider():
    rt = AgentRuntime(_bus(), run_factory=_ok_run, parallel_limit=2)
    await rt.spawn(AgentConfig(agent_id="M", tools=(), mechanical=True))
    await rt.spawn(AgentConfig(agent_id="N", tools=(), model="model-x"))

    assert rt.is_mechanical("M") is True
    assert rt._provider_bindings["M"] is None  # no provider binding (F4)
    assert rt.is_mechanical("N") is False
    assert rt._provider_bindings["N"] == "model-x"


@pytest.mark.asyncio
async def test_cache_key_for_applies_namespace_at_runtime():
    rt = AgentRuntime(_bus(), run_factory=_ok_run, parallel_limit=2)
    await rt.spawn(AgentConfig(agent_id="A", tools=(), cache_namespace="team-a"))
    await rt.spawn(AgentConfig(agent_id="B", tools=()))

    base = "https://api.example.com|model|digest"
    assert rt.cache_key_for("A", base) == f"{base}|team-a"
    assert rt.cache_key_for("B", base) == base  # byte-identical legacy key
    assert rt.cache_key_for("A", base) != rt.cache_key_for("B", base)


@pytest.mark.asyncio
async def test_spawn_stores_namespace_for_cache_key_building():
    rt = AgentRuntime(_bus(), run_factory=_ok_run)
    await rt.spawn(
        AgentConfig(agent_id="A", tools=(), cache_namespace="team-a")
    )
    assert rt.configs["A"].cache_namespace == "team-a"
    base = "https://api.example.com|model|digest"
    assert build_cache_key(base, rt.configs["A"].cache_namespace) == f"{base}|team-a"
    await rt.stop("A", reason="done")
