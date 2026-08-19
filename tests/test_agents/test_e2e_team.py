"""F11 · software_dev 专家团端到端（mock LLM）。"""

from __future__ import annotations

import asyncio
import time

from RxyCode.RxyCode1_1_0.core.agents.coordinator import Coordinator, PrecheckError
from RxyCode.RxyCode1_1_0.core.agents.spec import validate_team
from RxyCode.RxyCode1_1_0.core.agents.teams import load_builtin_team
from RxyCode.RxyCode1_1_0.core.agents.verifier import SOFTWARE_DEV_STAGE_CHECKS, subject_hash
from RxyCode.RxyCode1_1_0.core.prompts import list_stages
from RxyCode.RxyCode1_1_0.core.session import Session
from RxyCode.RxyCode1_1_0.protocol.agents import (
    AgentSpec,
    ConsultRequest,
    SopStage,
    TeamSpec,
    VerdictRecord,
)

_WRITE = {"write", "edit", "patch"}
_KNOWN_TOOLS = {
    "bash", "cd", "datetime", "diagnostics", "download_file", "download_mcp",
    "download_skill", "edit", "format", "git", "glob", "grep", "history", "ls",
    "memory", "open_file", "patch", "question", "read", "skill", "task", "view",
    "vision", "webfetch", "websearch", "workflow", "write", "code_search",
}


class _Stamp:
    def __init__(self) -> None:
        self.coord: Coordinator | None = None
        self.fail_first_implement = False
        self._implement_seen = 0
        self.fail_audit_left = 0
        self._audit_seen = 0

    def run(self, stage, result):
        if stage.name == "implement":
            self._implement_seen += 1
            if self.fail_first_implement and self._implement_seen == 1:
                return type("V", (), {"passed": False, "findings": ["lint_clean: dirty"]})()
        if stage.name == "audit":
            self._audit_seen += 1
            if self.fail_audit_left > 0:
                self.fail_audit_left -= 1
                return type("V", (), {"passed": False, "findings": ["audit reject"]})()
        digest = subject_hash(result.answer, getattr(result, "diff", "") or "")
        if self.coord is not None:
            self.coord.store_verdict(
                VerdictRecord(
                    subject_hash=digest,
                    auditor_role="auditor",
                    passed=True,
                    created_at=time.time(),
                )
            )
        return type("V", (), {"passed": True, "findings": []})()


def _coord(stamp: _Stamp | None = None) -> Coordinator:
    gate = stamp or _Stamp()
    coord = Coordinator(
        Session(session_id="ses-f11", workspace_root=".", emit=lambda _n: None),
        verifier=gate,
    )
    gate.coord = coord
    return coord


def test_team_loads_and_validates() -> None:
    team = load_builtin_team("software_dev")
    validate_team(team)
    assert team.name == "software_dev"
    assert {m.role for m in team.members} >= {"architect", "coder", "verifier", "auditor"}


def test_prompt_stages_exist() -> None:
    keys = set(list_stages())
    assert {"agent_architect", "agent_coder", "agent_auditor"} <= keys


def test_yaml_tool_names_are_real() -> None:
    team = load_builtin_team()
    for member in team.members:
        if member.tools:
            unknown = set(member.tools) - _KNOWN_TOOLS
            assert not unknown, unknown


def test_auditor_cannot_edit_files() -> None:
    team = load_builtin_team()
    auditor = next(m for m in team.members if m.role == "auditor")
    assert _WRITE.isdisjoint(auditor.tools or [])
    stage = SopStage(
        name="hack",
        role="auditor",
        expected_output="write the file",
        output_key="hack",
    )
    hacked = TeamSpec(
        name="x",
        display_name="x",
        members=list(team.members),
        stages=[stage],
        entry_stage="hack",
    )
    coord = _coord()
    try:
        coord._precheck(stage, hacked)
        raise AssertionError("auditor write stage must fail precheck")
    except PrecheckError:
        pass


def test_happy_path_plan_implement_audit() -> None:
    text = asyncio.run(_coord().run_team(load_builtin_team(), "add a health endpoint"))
    assert "plan" in text and "implement" in text and "audit" in text


def test_mechanical_fail_retries_implement() -> None:
    stamp = _Stamp()
    stamp.fail_first_implement = True
    text = asyncio.run(_coord(stamp).run_team(load_builtin_team(), "fix lint"))
    assert stamp._implement_seen >= 2
    assert "implement" in text


def test_audit_reject_sends_back_to_implement() -> None:
    stamp = _Stamp()
    stamp.fail_audit_left = 3
    text = asyncio.run(_coord(stamp).run_team(load_builtin_team(), "ship"))
    assert stamp._implement_seen >= 2
    assert "implement" in text


def test_retries_exhausted_then_fails() -> None:
    team = TeamSpec(
        name="tiny",
        display_name="tiny",
        members=[AgentSpec(role="coder", display_name="c", goal="c", prompt_stage="agent_coder")],
        stages=[
            SopStage(
                name="implement",
                role="coder",
                expected_output="note",
                output_key="implementation",
                next_on_success=None,
                next_on_failure=None,
                max_retries=0,
                verify_before_next=["lint_clean"],
            )
        ],
        entry_stage="implement",
    )

    class _AlwaysFail:
        def run(self, stage, result):
            return type("V", (), {"passed": False, "findings": ["no"]})()

    coord = Coordinator(
        Session(session_id="ses-fail", workspace_root=".", emit=lambda _n: None),
        verifier=_AlwaysFail(),
    )
    text = asyncio.run(coord.run_team(team, "x"))
    assert "implement" in text


def test_coder_consults_architect() -> None:
    team = load_builtin_team()
    coord = _coord()
    reply = coord.consult(
        team,
        ConsultRequest(
            session_id="ses-f11",
            request_id="q1",
            from_role="coder",
            to_role="architect",
            question="方案里没提到迁移脚本",
            stage="implement",
        ),
        answer="补一节 migration",
    )
    assert reply == "补一节 migration"
    assert all(msg.relayed_by == "coordinator" for msg in coord.mailbox.all())


def test_budget_returns_partial() -> None:
    text = asyncio.run(
        _coord().run_team(
            load_builtin_team(),
            "big",
            budget_overrides={"max_delegations": 0},
        )
    )
    assert "超出预算" in text


def test_implement_declares_both_check_levels() -> None:
    team = load_builtin_team()
    implement = next(s for s in team.stages if s.name == "implement")
    assert list(implement.verify_before_next) == SOFTWARE_DEV_STAGE_CHECKS["implement"]
