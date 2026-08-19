"""F5 · SopMachine 纯逻辑转移。"""

from __future__ import annotations

import ast
from pathlib import Path

from RxyCode.RxyCode1_1_0.core.agents.sop import SopMachine
from RxyCode.RxyCode1_1_0.protocol.agents import AgentSpec, SopStage, TeamSpec


def _member(role: str) -> AgentSpec:
    return AgentSpec(role=role, display_name=role, goal=role, prompt_stage="default")


def _stage(
    name: str,
    role: str,
    *,
    next_on_success: str | None = None,
    next_on_failure: str | None = None,
    max_retries: int = 2,
) -> SopStage:
    return SopStage(
        name=name,
        role=role,
        expected_output="out",
        output_key=name,
        next_on_success=next_on_success,
        next_on_failure=next_on_failure,
        max_retries=max_retries,
    )


def _team(*stages: SopStage) -> TeamSpec:
    roles = {stage.role for stage in stages}
    return TeamSpec(
        name="t",
        display_name="T",
        members=[_member(role) for role in roles],
        stages=list(stages),
        entry_stage=stages[0].name,
    )


def test_advance_success_path() -> None:
    sop = SopMachine(
        _team(
            _stage("plan", "architect", next_on_success="code"),
            _stage("code", "coder"),
        )
    )
    assert sop.current_stage() is not None
    assert sop.current_stage().name == "plan"
    nxt = sop.advance(ok=True)
    assert nxt is not None
    assert nxt.name == "code"
    assert sop.advance(ok=True) is None


def test_retry_until_max_then_failure_branch() -> None:
    sop = SopMachine(
        _team(
            _stage("code", "coder", next_on_success="done", next_on_failure="fix", max_retries=2),
            _stage("fix", "coder"),
            _stage("done", "coder"),
        )
    )
    assert sop.advance(ok=False).name == "code"
    assert sop.advance(ok=False).name == "code"
    nxt = sop.advance(ok=False)
    assert nxt is not None
    assert nxt.name == "fix"


def test_failure_branch_without_waiting() -> None:
    sop = SopMachine(
        _team(
            _stage("code", "coder", next_on_success="done", next_on_failure="fix", max_retries=0),
            _stage("fix", "coder"),
            _stage("done", "coder"),
        )
    )
    nxt = sop.advance(ok=False)
    assert nxt is not None
    assert nxt.name == "fix"


def test_terminal_none() -> None:
    sop = SopMachine(_team(_stage("only", "coder")))
    assert sop.advance(ok=True) is None
    assert sop.current_stage() is None
    assert sop.advance(ok=True) is None


def test_max_retries_zero_success_still_advances() -> None:
    sop = SopMachine(
        _team(
            _stage("plan", "architect", next_on_success="code", max_retries=0),
            _stage("code", "coder"),
        )
    )
    assert sop.advance(ok=True).name == "code"


def test_history_replays_a_run() -> None:
    sop = SopMachine(
        _team(
            _stage("code", "coder", next_on_success="review", next_on_failure="code", max_retries=1),
            _stage("review", "reviewer"),
        )
    )
    sop.advance(ok=False)
    sop.advance(ok=True)
    sop.advance(ok=True)
    names = [(rec.stage, rec.ok, rec.next_stage) for rec in sop.history()]
    assert names == [
        ("code", False, "code"),
        ("code", True, "review"),
        ("review", True, None),
    ]
    replay = [rec.stage for rec in sop.history()]
    assert replay == ["code", "code", "review"]


def test_sop_module_has_no_llm_or_io_imports() -> None:
    source = Path("core/agents/sop.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            imported.add(node.module)
    forbidden = {
        "openai",
        "httpx",
        "requests",
        "aiohttp",
        "socket",
        "subprocess",
        "pathlib",
        "Session",
        "agent_v2",
        "core.session",
        "core.agent_v2",
        "RxyCode.RxyCode1_1_0.core.session",
        "RxyCode.RxyCode1_1_0.core.agent_v2",
    }
    assert imported.isdisjoint(forbidden)
    assert "protocol" in imported or "RxyCode.RxyCode1_1_0.protocol.agents" in imported
