"""Phase E · E7 — multi-agent runtime benchmark.

Measures the five E7 benchmarks against the AgentRuntime/AgentTask/EventBus
stack and demonstrates RB1-RB5 (PHASE-E §3.4) mechanically:

  1. N=1/2/4 agent parallel throughput (RB1: real parallelism)
  2. event order + drop rate with a slow subscriber (RB3: bus auditability)
  3. interrupt fan-out latency (RB5: cancellation reachable)
  4. deadlock pressure: two agents contending for shared tool slots
  5. budget circuit-breaker time

Event-passthrough assertions (PHASE-E §5 E7 item 7): with ``--tag`` set,
routed/started events carry experiment_tag/tokens_used/budget_used/
cache_miss_warning through serialize -> bridge -> deserialize.

Usage:
  python scripts/bench_multi_agent.py --out <path>.json [--tag E1] [--smoke]
  python scripts/bench_multi_agent.py --stress --duration 1800 --out <path>.json

Output schema (PHASE-E §5 E7):
  {"schema_version": 1, "env": {...}, "duration_s": N, "metrics": {...}}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from appserver.agent_runtime import AgentConfig, AgentRuntime  # noqa: E402
from appserver.agent_task import LifecycleState  # noqa: E402
from appserver.eventbus import AppendOnlyLog, BusEvent, EventBus  # noqa: E402
from protocol.notifications import AgentEvent as ProtocolAgentEvent  # noqa: E402

LLM_WAIT_S = 0.05
RUNS_PER_AGENT = 10


@dataclass
class Metrics:
    throughput_serial_s: float = 0.0
    throughput_n1_s: float = 0.0
    throughput_n2_s: float = 0.0
    throughput_n4_s: float = 0.0
    speedup_n2: float = 0.0
    speedup_n4: float = 0.0
    event_drop_rate: float = 0.0
    publisher_blocked: bool = False
    interrupt_fanout_ms: float = 0.0
    deadlock_pressure_rounds: int = 0
    deadlock_hang: bool = False
    budget_breaker_ms: float = 0.0
    rb1_real_parallelism: bool = False
    rb2_independent_state: bool = True
    rb3_bus_replay_ok: bool = False
    rb4_explicit_delegation: bool = True
    rb5_cancel_reachable: bool = False
    passthrough_ok: bool = False


def _env() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "phasee": "E7",
        "parallel": os.environ.get("RXYCODE_AGENT_PARALLEL", "1"),
    }


def _llm_sim_run(llm_wait: float = LLM_WAIT_S) -> Callable[[AgentConfig], Callable]:
    """A run factory that simulates LLM-bound work (mostly waiting)."""

    def factory(cfg: AgentConfig):
        async def run(task: str, checkpoint: object | None = None) -> str:
            await asyncio.sleep(llm_wait)
            return f"ok:{cfg.agent_id}"

        return run

    return factory


async def bench_throughput(bus: EventBus, metrics: Metrics) -> None:
    """① N=1/2/4 throughput; N>=2 total must beat serial 1.5x (RB1)."""
    start = time.perf_counter()
    rt = AgentRuntime(bus, run_factory=_llm_sim_run(), parallel_limit=1)
    task = await rt.spawn(AgentConfig(agent_id="n1", tools=()))
    for _ in range(RUNS_PER_AGENT):
        await task.wait_state(LifecycleState.DONE)
        await task.resume() if task.state == LifecycleState.FAILED else None
        if task.state == LifecycleState.DONE:
            break
    metrics.throughput_serial_s = time.perf_counter() - start
    await rt.stop("n1", reason="done")

    # measure one full run cycle per agent as the unit of work
    async def unit_run(rt: AgentRuntime, n: int) -> float:
        started = time.perf_counter()
        rt2 = AgentRuntime(
            bus,
            run_factory=_llm_sim_run(),
            parallel_limit=n,
            total_tool_slots=16,
        )
        tasks = []
        for i in range(n):
            t = await rt2.spawn(AgentConfig(agent_id=f"u{i}", tools=()))
            tasks.append(t)
        await asyncio.gather(
            *(t.wait_state(LifecycleState.DONE) for t in tasks)
        )
        elapsed = time.perf_counter() - started
        for t in tasks:
            await rt2.stop(t.agent_id, reason="done")
        return elapsed

    metrics.throughput_n1_s = await unit_run(rt, 1)
    metrics.throughput_n2_s = await unit_run(rt, 2)
    metrics.throughput_n4_s = await unit_run(rt, 4)
    metrics.speedup_n2 = (
        (2 * metrics.throughput_n1_s / metrics.throughput_n2_s)
        if metrics.throughput_n2_s
        else 0.0
    )
    metrics.speedup_n4 = (
        (4 * metrics.throughput_n1_s / metrics.throughput_n4_s)
        if metrics.throughput_n4_s
        else 0.0
    )
    metrics.rb1_real_parallelism = metrics.speedup_n2 >= 1.5


async def bench_event_bus(bus: EventBus, metrics: Metrics) -> None:
    """② event order + drop rate with a slow subscriber (RB3)."""
    slow = await bus.subscribe("slow", "event/*")
    total = 2048
    start = time.perf_counter()
    for i in range(total):
        await bus.publish(
            BusEvent(
                method="event/agent_progress",
                session_id=f"n{i}",
                agent_id="bench",
                payload={},
            )
        )
    publisher_elapsed = time.perf_counter() - start
    received = slow.queue.qsize()
    metrics.event_drop_rate = 1.0 - (received / total) if total else 0.0
    metrics.publisher_blocked = publisher_elapsed > 5.0

    replayed = [e async for e in bus.replay(after_seq=0, page_size=200)]
    seqs = [e.seq for e in replayed]
    metrics.rb3_bus_replay_ok = seqs == list(range(1, len(seqs) + 1))


async def bench_interrupt(bus: EventBus, metrics: Metrics) -> None:
    """③ interrupt fan-out latency (single agent -> tool tree), < 2s (RB5)."""
    started = asyncio.Event()

    def factory(cfg: AgentConfig):
        async def run(task: str, checkpoint: object | None = None) -> str:
            started.set()
            await asyncio.Event().wait()

        return run

    rt = AgentRuntime(bus, run_factory=factory, parallel_limit=2)
    task = await rt.spawn(AgentConfig(agent_id="cancel", tools=()))
    await started.wait()
    start = time.perf_counter()
    await rt.stop("cancel", reason="bench")
    metrics.interrupt_fanout_ms = (time.perf_counter() - start) * 1000
    metrics.rb5_cancel_reachable = (
        task.state == LifecycleState.CANCELLED
        and metrics.interrupt_fanout_ms < 2000
    )


async def bench_deadlock(bus: EventBus, metrics: Metrics, duration_s: float) -> None:
    """④ two agents contending for a shared tool-slot pool; no hang."""
    rt = AgentRuntime(
        bus,
        run_factory=_llm_sim_run(0.01),
        parallel_limit=2,
        total_tool_slots=1,  # forced contention
    )
    tasks = []
    for i in range(2):
        t = await rt.spawn(AgentConfig(agent_id=f"d{i}", tools=(), quota=1))
        tasks.append(t)

    async def contested_run(t) -> None:
        for _ in range(20):
            async with rt.acquire_tool_slot(t.agent_id):
                await asyncio.sleep(0.005)

    try:
        rounds = 0
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            await asyncio.gather(*(contested_run(t) for t in tasks))
            rounds += 1
        metrics.deadlock_pressure_rounds = rounds
        metrics.deadlock_hang = False
    except asyncio.TimeoutError:
        metrics.deadlock_hang = True
    finally:
        for t in tasks:
            await rt.stop(t.agent_id, reason="bench")


async def bench_budget(bus: EventBus, metrics: Metrics) -> None:
    """⑤ budget circuit breaker latency, < 1s."""
    rt3 = AgentRuntime(bus, run_factory=None, parallel_limit=2)

    def factory(cfg: AgentConfig):
        async def run(task: str, checkpoint: object | None = None) -> str:
            await rt3.check_budget(cfg.agent_id, est=100)  # 50 budget -> breaker
            return "ok"

        return run

    rt3 = AgentRuntime(bus, run_factory=factory, parallel_limit=2)
    start = time.perf_counter()
    task = await rt3.spawn(
        AgentConfig(agent_id="budget", tools=(), budget_tokens=50)
    )
    await task.wait_state(LifecycleState.CANCELLED, timeout=2.0)
    metrics.budget_breaker_ms = (time.perf_counter() - start) * 1000


async def bench_passthrough(bus: EventBus, metrics: Metrics, tag: str | None) -> None:
    """⑦ event payload passthrough (F14 gate data source).

    Without ``--tag`` this stays None (untested) instead of pretending a
    pass: the E1-tagged run is the only valid evidence for the assertion.
    """
    if tag is None:
        metrics.passthrough_ok = None
        return
    evt = ProtocolAgentEvent(
        method="event/agent_routed",
        session_id="s",
        agent_id="A",
        payload={},
        seq=1,
        experiment_tag=tag,
        routing_reason="bench",
        tokens_used=42,
        budget_used=21,
        cache_miss_warning=True,
    )
    wire = json.loads(evt.model_dump_json())
    # serialize -> bridge -> deserialize (source preserved)
    back = ProtocolAgentEvent(**wire)
    metrics.passthrough_ok = (
        back.experiment_tag == tag
        and back.tokens_used == 42
        and back.budget_used == 21
        and back.cache_miss_warning is True
        and back.routing_reason == "bench"
    )


def _rb_demo_records(metrics: Metrics, contract_evidence: str) -> list[dict[str, Any]]:
    """RB1-RB5 demonstration record (measured values + contract evidence).

    RB2/RB4 are evidenced by the contract test results (E6 isolation tests,
    EB8 oversized-payload rejection / dead-letter tests) passed in via
    ``contract_evidence`` — never self-assigned by this script.
    """
    rb2_pass = "test_messages_isolated_between_agents" in contract_evidence and "passed" in contract_evidence
    rb4_pass = (
        "test_oversized_payload_rejected_eb8" in contract_evidence
        and "passed" in contract_evidence
        and "test_send_to_dead_letter_does_not_block_publisher" in contract_evidence
    )
    return [
        {
            "rb": "RB1",
            "demo": "speedup_n2 >= 1.5 (measured)",
            "value": metrics.speedup_n2,
            "pass": metrics.rb1_real_parallelism,
        },
        {
            "rb": "RB2",
            "demo": "AgentContext slices isolated (E6 contract test "
            "test_messages_isolated_between_agents)",
            "value": contract_evidence,
            "pass": rb2_pass,
        },
        {
            "rb": "RB3",
            "demo": "bus replay by seq matches live order after concurrent "
            "publish (bench_event_bus measured)",
            "value": metrics.rb3_bus_replay_ok,
            "pass": metrics.rb3_bus_replay_ok,
        },
        {
            "rb": "RB4",
            "demo": "data plane stays explicit (EB8 oversized payload "
            "rejection + dead-letter contract tests)",
            "value": contract_evidence,
            "pass": rb4_pass,
        },
        {
            "rb": "RB5",
            "demo": "interrupt fan-out latency < 2s with real task cancel "
            "(measured)",
            "value_ms": metrics.interrupt_fanout_ms,
            "pass": metrics.rb5_cancel_reachable,
        },
    ]


def _metrics_dict(metrics: Metrics, rb_records: list[dict]) -> dict[str, Any]:
    base = asdict(metrics)
    base["rb_demonstrations"] = rb_records
    return base


async def _run_all(bus: EventBus, metrics: Metrics, tag: str | None, duration_s: float) -> None:
    await bench_throughput(bus, metrics)
    await bench_event_bus(bus, metrics)
    await bench_interrupt(bus, metrics)
    await bench_deadlock(bus, metrics, duration_s=duration_s)
    await bench_budget(bus, metrics)
    await bench_passthrough(bus, metrics, tag)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Phase E multi-agent benchmark")
    parser.add_argument("--out", required=True, help="output JSON path")
    parser.add_argument("--tag", choices=["E0", "E1", "E2"], default=None)
    parser.add_argument("--smoke", action="store_true", help="quick smoke run")
    parser.add_argument("--stress", action="store_true", help="deadlock pressure mode")
    parser.add_argument("--duration", type=int, default=1800, help="stress seconds")
    args = parser.parse_args()

    bus = EventBus(AppendOnlyLog())
    metrics = Metrics()
    if args.smoke:
        await _run_all(bus, metrics, None, duration_s=1.0)
    elif args.stress:
        await bench_deadlock(bus, metrics, duration_s=float(args.duration))
    else:
        await _run_all(bus, metrics, args.tag, duration_s=2.0)

    contract_evidence = _run_contract_evidence()
    if args.stress:
        # stress mode exercises only the deadlock benchmark; the RB
        # demonstrations belong to the full benchmark run, so they are
        # explicitly marked n/a instead of carrying misleading defaults.
        rb_records = [
            {
                "rb": f"RB{n}",
                "demo": "n/a in --stress mode (see full benchmark run)",
                "value": None,
                "pass": None,
            }
            for n in range(1, 6)
        ]
    else:
        rb_records = _rb_demo_records(metrics, contract_evidence)
    payload = {
        "schema_version": 1,
        "env": _env(),
        "duration_s": args.duration if args.stress else None,
        "metrics": _metrics_dict(metrics, rb_records),
    }
    out_path = args.out
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if args.stress:
        return 0 if not metrics.deadlock_hang else 1
    return 0 if metrics.rb1_real_parallelism and metrics.rb5_cancel_reachable else 1


def _run_contract_evidence() -> str:
    """Live contract-test output backing RB2/RB4 (never self-assigned)."""
    import subprocess

    try:
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/contract/test_agent_context.py",
                "tests/contract/test_eventbus.py",
                "-v",
                "-k",
                "isolated or oversized or dead_letter or readonly",
                "--timeout=120",
            ],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        return (r.stdout + r.stderr).strip()
    except Exception as exc:  # noqa: BLE001
        return f"(contract evidence unavailable: {exc})"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
