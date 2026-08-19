"""F9 · BudgetGuard 四道闸门。"""

from __future__ import annotations

import asyncio
import time

import pytest

from RxyCode.RxyCode1_1_0.core.agents.budget import BudgetExceeded, BudgetGuard
from RxyCode.RxyCode1_1_0.core.agents.coordinator import Coordinator, MemberForbiddenError
from RxyCode.RxyCode1_1_0.core.session import Session
from RxyCode.RxyCode1_1_0.protocol.agents import AgentSpec, SopStage, TeamSpec


def _team(*, tokens: int = 500_000, timeout: float = 1800.0, delegations: int = 20) -> TeamSpec:
    return TeamSpec(
        name="t",
        display_name="T",
        members=[
            AgentSpec(role="coder", display_name="c", goal="c", prompt_stage="default"),
        ],
        stages=[
            SopStage(
                name="a",
                role="coder",
                expected_output="note",
                output_key="a",
                next_on_success="b",
            ),
            SopStage(name="b", role="coder", expected_output="note", output_key="b"),
        ],
        entry_stage="a",
        total_token_budget=tokens,
        total_timeout_s=timeout,
        max_delegations=delegations,
    )


def test_token_budget_stops_the_team() -> None:
    team = _team(tokens=1)
    guard = BudgetGuard(team, overrides={"total_token_budget": 1})
    guard.start(team)
    with pytest.raises(BudgetExceeded, match="token budget"):
        guard.add_tokens(2)


def test_wall_clock_deadline_stops_the_team() -> None:
    team = _team(timeout=0.01)
    guard = BudgetGuard(team, overrides={"total_timeout_s": 0.01})
    guard.start(team)
    time.sleep(0.05)
    with pytest.raises(BudgetExceeded, match="wall-clock"):
        guard.check()


def test_delegation_count_catches_ping_pong_loop() -> None:
    team = _team(delegations=1)
    guard = BudgetGuard(team, overrides={"max_delegations": 1})
    guard.start(team)
    guard.add_delegation()
    with pytest.raises(BudgetExceeded, match="delegation count"):
        guard.add_delegation()


def test_member_cannot_create_a_subteam() -> None:
    coord = Coordinator(Session(session_id="ses-f9", workspace_root=".", emit=lambda _n: None))
    with pytest.raises(MemberForbiddenError):
        coord.member_form_team(
            AgentSpec(role="coder", display_name="c", goal="c", prompt_stage="default"),
            _team(),
        )


def test_budget_exceeded_returns_partial_result_not_crash() -> None:
    class _Trip:
        def start(self, team: TeamSpec) -> None:
            return None

        def check(self) -> None:
            raise BudgetExceeded("token budget 1 exhausted")

    coord = Coordinator(
        Session(session_id="ses-f9", workspace_root=".", emit=lambda _n: None),
        budget=_Trip(),
    )
    text = asyncio.run(coord.run_team(_team(), "go"))
    assert "提前停止" in text
    assert "已完成" in text


def test_partial_result_tells_the_user_it_was_truncated() -> None:
    text = asyncio.run(
        Coordinator(
            Session(session_id="ses-f9b", workspace_root=".", emit=lambda _n: None)
        ).run_team(_team(), "go", budget_overrides={"max_delegations": 0})
    )
    assert "超出预算" in text
    assert "已完成" in text
    assert "阶段" in text


def test_request_override_beats_team_defaults() -> None:
    team = _team(tokens=500_000)
    guard = BudgetGuard(team, overrides={"total_token_budget": 3})
    guard.start(team)
    with pytest.raises(BudgetExceeded, match="token budget 3"):
        guard.add_tokens(4)
