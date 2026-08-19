"""F8 · MechanicalVerifier 纯确定性检查。"""

from __future__ import annotations

import inspect
import time
from pathlib import Path

import pytest

from RxyCode.RxyCode1_1_0.core.agents.coordinator import Coordinator, StageOutcome
from RxyCode.RxyCode1_1_0.core.agents.verifier import (
    CHECK_LEVELS,
    SOFTWARE_DEV_STAGE_CHECKS,
    MechanicalVerifier,
    VerifyContext,
    subject_hash,
)
from RxyCode.RxyCode1_1_0.core.session import Session
from RxyCode.RxyCode1_1_0.protocol.agents import SopStage, VerdictRecord


def _stage(*checks: str, expected: str = "artifact") -> SopStage:
    return SopStage(
        name="implement",
        role="coder",
        expected_output=expected,
        output_key="implementation",
        verify_before_next=list(checks),
    )


def _result(answer: str = "done", diff: str = "diff --git a/x b/x") -> StageOutcome:
    return StageOutcome(ok=True, answer=answer, diff=diff)


def _ctx(tmp_path: Path, **kwargs: object) -> VerifyContext:
    return VerifyContext(workspace=tmp_path, **kwargs)  # type: ignore[arg-type]


def _run(tmp_path: Path, checks: list[str], **kwargs: object) -> object:
    return MechanicalVerifier().run(_stage(*checks), _result(), ctx=_ctx(tmp_path, **kwargs))


def test_files_exist_pass_and_fail(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    ok = _run(tmp_path, ["files_exist"], claimed_files=["ok.py"], stage_output="ok")
    assert ok.passed
    bad = _run(tmp_path, ["files_exist"], claimed_files=["missing.py"], stage_output="ok")
    assert not bad.passed
    assert "files_exist" in bad.findings[0]


def test_python_parses_pass_and_fail(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("def (\n", encoding="utf-8")
    assert _run(tmp_path, ["python_parses"], claimed_files=["ok.py"]).passed
    bad = _run(tmp_path, ["python_parses"], claimed_files=["bad.py"])
    assert not bad.passed


def test_json_parses_pass_and_fail(tmp_path: Path) -> None:
    (tmp_path / "ok.json").write_text('{"a": 1}\n', encoding="utf-8")
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    assert _run(tmp_path, ["json_parses"], claimed_files=["ok.json"]).passed
    assert not _run(tmp_path, ["json_parses"], claimed_files=["bad.json"]).passed


def test_yaml_parses_pass_and_fail(tmp_path: Path) -> None:
    (tmp_path / "ok.yaml").write_text("a: 1\n", encoding="utf-8")
    (tmp_path / "bad.yaml").write_text(":\n  - [\n", encoding="utf-8")
    assert _run(tmp_path, ["yaml_parses"], claimed_files=["ok.yaml"]).passed
    assert not _run(tmp_path, ["yaml_parses"], claimed_files=["bad.yaml"]).passed


def test_lint_clean_pass_and_fail(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("import os\n", encoding="utf-8")
    assert _run(tmp_path, ["lint_clean"], claimed_files=["ok.py"]).passed
    assert not _run(tmp_path, ["lint_clean"], claimed_files=["bad.py"]).passed


def test_tests_pass_pass_and_fail(tmp_path: Path) -> None:
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (tmp_path / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    assert _run(
        tmp_path, ["tests_pass"], claimed_files=["test_ok.py"], pytest_targets=["test_ok.py"]
    ).passed
    assert not _run(
        tmp_path, ["tests_pass"], claimed_files=["test_bad.py"], pytest_targets=["test_bad.py"]
    ).passed


def test_no_forbidden_pass_and_fail(tmp_path: Path) -> None:
    assert _run(
        tmp_path, ["no_forbidden"], claimed_files=["ok.py"], diff="ok.py", stage_output="ok"
    ).passed
    bad = _run(
        tmp_path,
        ["no_forbidden"],
        claimed_files=["credentials.yaml"],
        diff="",
        stage_output="",
    )
    assert not bad.passed


def test_diff_non_empty_catches_fake_done(tmp_path: Path) -> None:
    assert _run(tmp_path, ["diff_non_empty"], diff="+ added line").passed
    bad = _run(tmp_path, ["diff_non_empty"], diff="   \n")
    assert not bad.passed
    assert "empty" in bad.findings[0]


def test_goal_satisfied_is_high_level() -> None:
    assert CHECK_LEVELS["goal_satisfied"] == "high"
    assert CHECK_LEVELS["python_parses"] == "low"


def test_low_level_pass_high_level_fail(tmp_path: Path) -> None:
    """MAST ChatDev chess: compiles but missing game rules."""
    (tmp_path / "chess.py").write_text("print('board')\n", encoding="utf-8")
    verdict = MechanicalVerifier().run(
        _stage(
            "files_exist",
            "python_parses",
            "lint_clean",
            "goal_satisfied",
            expected="checkmate\ncastling",
        ),
        _result(answer="a python chess UI with pieces"),
        ctx=_ctx(
            tmp_path,
            claimed_files=["chess.py"],
            python_files=["chess.py"],
            stage_output="a python chess UI with pieces",
            expected_output="checkmate\ncastling",
            goal_rules=["checkmate", "castling"],
            diff="+ print('board')",
        ),
    )
    assert not verdict.passed
    assert any("goal_satisfied" in item for item in verdict.findings)
    assert not any(item.startswith("files_exist") for item in verdict.findings)
    assert not any(item.startswith("python_parses") for item in verdict.findings)


def test_verifier_never_calls_an_llm() -> None:
    """机械验证门必须是纯确定性的。"""
    from core.agents import verifier

    src = inspect.getsource(verifier)
    for forbidden in ("ainvoke", "ChatOpenAI", "_llm", "get_role_prompt"):
        assert forbidden not in src, (
            f"verifier must stay LLM-free but references {forbidden!r}"
        )


def test_stale_verdict_is_rejected_after_output_changes() -> None:
    """产出变了，旧的审计通过结论必须失效。"""
    first = subject_hash(" impl ", "diff-a")
    second = subject_hash(" impl ", "diff-b")
    assert first != second
    session = Session(session_id="ses-f8", workspace_root=".", emit=lambda _n: None)
    coord = Coordinator(session)
    coord.store_verdict(
        VerdictRecord(
            subject_hash=first,
            auditor_role="auditor",
            passed=True,
            created_at=time.time(),
        )
    )
    assert coord.verdict_allows(first)
    assert not coord.verdict_allows(second)
    stage = SopStage(
        name="implement",
        role="coder",
        expected_output="code",
        output_key="implementation",
        audit_after_verify=True,
    )
    gated = coord._apply_verify_gates(stage, _result(answer=" impl ", diff="diff-b"))
    assert gated.ok is False
    assert "stale" in gated.error


def test_software_dev_stages_declare_check_levels() -> None:
    implement = SOFTWARE_DEV_STAGE_CHECKS["implement"]
    levels = {CHECK_LEVELS[name] for name in implement}
    assert "low" in levels
    assert "high" in levels
    assert "goal_satisfied" in implement
    assert "diff_non_empty" in implement
    for stage_name, checks in SOFTWARE_DEV_STAGE_CHECKS.items():
        for name in checks:
            assert name in CHECK_LEVELS, f"{stage_name} unknown check {name}"
