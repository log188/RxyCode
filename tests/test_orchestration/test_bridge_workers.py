"""F16 bridge workers: protocol, stdio e2e, recycle, timeout, budget, isolation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from RxyCode.RxyCode1_1_0.core.agents.blackboard import Blackboard
from RxyCode.RxyCode1_1_0.core.agents.bridge.envelope import decode_line, encode, truncate_summary
from RxyCode.RxyCode1_1_0.core.agents.bridge.leader import BridgeLeader
from RxyCode.RxyCode1_1_0.core.agents.bridge.registry import load_bridge_workers
from RxyCode.RxyCode1_1_0.core.agents.bridge.worker import (
    BridgeError,
    BridgeWorker,
    live_bridge_processes,
)
from RxyCode.RxyCode1_1_0.core.agents.budget import BudgetExceeded, BudgetGuard
from RxyCode.RxyCode1_1_0.core.session import Session
from RxyCode.RxyCode1_1_0.protocol.agents import (
    AgentSpec,
    BridgeAbort,
    BridgePlan,
    BridgeProgress,
    BridgeResult,
    BridgeToolCall,
    SopStage,
    TaskDelegate,
    TeamSpec,
)

_MOCK = Path(__file__).with_name("mock_bridge_worker.py")


def _team() -> TeamSpec:
    return TeamSpec(
        name="b",
        display_name="B",
        members=[AgentSpec(role="coder", display_name="c", goal="c", prompt_stage="default")],
        stages=[SopStage(name="a", role="coder", expected_output="note", output_key="a")],
        entry_stage="a",
        total_token_budget=20,
    )


def test_six_message_types_roundtrip() -> None:
    models = [
        TaskDelegate(task_id="t1", goal="g", context_refs=["blackboard://plan"]),
        BridgeProgress(task_id="t1", status="running", notes="n"),
        BridgeToolCall(task_id="t1", tool="write", result_ref="a.txt"),
        BridgePlan(task_id="t1", steps=["one"], ack=True),
        BridgeResult(task_id="t1", ok=True, summary="ok"),
        BridgeAbort(task_id="t1", reason="timeout"),
    ]
    for model in models:
        wire = encode(model, rpc_id=1)
        assert wire["jsonrpc"] == "2.0"
        back = decode_line(json.dumps(wire))
        assert back is not None
        assert back.method == model.method


def test_summary_is_truncated() -> None:
    assert "truncated" in truncate_summary("x" * 9000)


def test_unused_bridge_has_zero_processes() -> None:
    assert live_bridge_processes() == 0


def test_stdio_delegate_progress_and_result(tmp_path: Path) -> None:
    worker = BridgeWorker(
        worker_id="echo",
        command=[sys.executable, str(_MOCK)],
        workspace=tmp_path,
        session_id="ses-bridge",
        role="grok-builder",
    )
    leader = BridgeLeader(session_id="ses-bridge")
    result = leader.dispatch(
        worker,
        TaskDelegate(task_id="t-1", goal="ship stdio", acceptance=["ok"]),
    )
    assert result.ok
    assert result.summary == "done"
    kinds = [type(e).__name__ for e in worker.events]
    assert "BridgeProgress" in kinds
    assert "BridgeToolCall" in kinds
    assert worker.recycled
    assert not worker.worktree.exists()
    assert leader.blackboard.view(["bridge:t-1"])["bridge:t-1"] == "done"
    assert all(m.relayed_by == "coordinator" for m in leader.mailbox.all())
    assert live_bridge_processes() == 0


def test_timeout_abort_kills_hanging_worker(tmp_path: Path) -> None:
    class _Hang:
        pid = None
        killed = False

        def send(self, _message):
            return None

        def recv(self, timeout):
            import time

            time.sleep(min(timeout, 0.05))
            return None

        def is_alive(self):
            return not self.killed

        def kill(self):
            self.killed = True

        def close(self):
            self.killed = True

    hang = _Hang()
    worker = BridgeWorker(
        worker_id="hang",
        channel=hang,
        workspace=tmp_path,
        session_id="ses-to",
    )
    with pytest.raises(BridgeError, match="timed out"):
        worker.delegate(TaskDelegate(task_id="t-to", goal="x", budget={"tokens": 10, "timeout_s": 0.12}))
    assert hang.killed
    assert worker.recycled


def test_budget_abort(tmp_path: Path) -> None:
    class _Rich:
        pid = None

        def send(self, _m):
            return None

        def recv(self, timeout):
            return {
                "jsonrpc": "2.0",
                "method": "result",
                "params": {
                    "task_id": "t-b",
                    "ok": True,
                    "summary": "x",
                    "artifact_paths": [],
                    "tokens_used": 50,
                    "duration_s": 0.1,
                },
            }

        def is_alive(self):
            return True

        def kill(self):
            return None

        def close(self):
            return None

    guard = BudgetGuard(_team(), overrides={"total_token_budget": 5})
    guard.start(_team())
    worker = BridgeWorker(
        worker_id="rich",
        channel=_Rich(),
        workspace=tmp_path,
        session_id="ses-b",
        budget=guard,
    )
    with pytest.raises(BudgetExceeded):
        worker.delegate(TaskDelegate(task_id="t-b", goal="x"))
    assert worker.recycled


def test_bridge_cache_namespaces_do_not_collide(tmp_path: Path) -> None:
    left = BridgeWorker(
        worker_id="a",
        channel=object(),
        workspace=tmp_path / "a",
        session_id="ses-1",
    )
    right = BridgeWorker(
        worker_id="b",
        channel=object(),
        workspace=tmp_path / "b",
        session_id="ses-1",
    )
    leader_ns = None
    assert left.cache_namespace != right.cache_namespace
    assert left.cache_namespace != leader_ns
    left.recycle()
    right.recycle()


def test_lineage_only_refs_not_history() -> None:
    req = TaskDelegate(
        task_id="t",
        goal="do",
        context_refs=["core/agents/coordinator.py:1", "blackboard://plan"],
    )
    dumped = req.model_dump()
    assert "messages" not in dumped
    assert "history" not in dumped
    assert dumped["context_refs"]


def test_load_default_registry_is_empty() -> None:
    specs = load_bridge_workers()
    assert specs == []
