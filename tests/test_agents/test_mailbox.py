"""F7 · mailbox 中转与 blackboard 授权可见。"""

from __future__ import annotations

import pytest

from RxyCode.RxyCode1_1_0.core.agents.blackboard import Blackboard, BlackboardFullError
from RxyCode.RxyCode1_1_0.core.agents.coordinator import (
    ConsultBudgetExceeded,
    ConsultDenied,
    Coordinator,
)
from RxyCode.RxyCode1_1_0.core.session import Session
from RxyCode.RxyCode1_1_0.protocol.agents import AgentSpec, ConsultRequest, SopStage, TeamSpec


def _session() -> Session:
    return Session(session_id="ses-f7", workspace_root=".", emit=lambda _n: None)


def _team() -> TeamSpec:
    return TeamSpec(
        name="dev",
        display_name="Dev",
        members=[
            AgentSpec(
                role="coder",
                display_name="coder",
                goal="code",
                prompt_stage="default",
                may_consult=["architect"],
            ),
            AgentSpec(
                role="architect",
                display_name="architect",
                goal="design",
                prompt_stage="default",
            ),
        ],
        stages=[
            SopStage(
                name="code",
                role="coder",
                expected_output="note",
                output_key="code",
            )
        ],
        entry_stage="code",
    )


def test_may_consult_denied() -> None:
    coord = Coordinator(_session())
    req = ConsultRequest(
        session_id="ses-f7",
        request_id="c1",
        from_role="architect",
        to_role="coder",
        question="why",
        stage="code",
    )
    with pytest.raises(ConsultDenied):
        coord.consult(_team(), req)


def test_consult_counts_against_budget() -> None:
    coord = Coordinator(_session())
    coord.max_consults = 1
    team = _team()
    req = ConsultRequest(
        session_id="ses-f7",
        request_id="c1",
        from_role="coder",
        to_role="architect",
        question="api shape?",
        stage="code",
    )
    assert coord.consult(team, req, answer="use REST") == "use REST"
    with pytest.raises(ConsultBudgetExceeded):
        coord.consult(team, req, answer="again")


def test_mailbox_records_relayed_by() -> None:
    coord = Coordinator(_session())
    req = ConsultRequest(
        session_id="ses-f7",
        request_id="c2",
        from_role="coder",
        to_role="architect",
        question="boundary?",
        stage="code",
    )
    coord.consult(_team(), req, answer="keep it thin")
    assert coord.mailbox.all()
    assert all(msg.relayed_by == "coordinator" for msg in coord.mailbox.all())


def test_blackboard_is_append_only() -> None:
    board = Blackboard()
    board.put("design", "v1", "architect")
    board.put("design", "v2", "architect")
    assert board.get("design") == "v2"
    versions = board.versions("design")
    assert [row.value for row in versions] == ["v1", "v2"]
    assert not hasattr(board, "delete")
    assert not hasattr(board, "overwrite")


def test_context_keys_are_authorized() -> None:
    board = Blackboard()
    board.put("design", "plan", "architect")
    board.put("secret", "hidden", "architect")
    assert board.view(["design"]) == {"design": "plan"}
    assert "secret" not in board.view(["design"])
    assert board.view([]) == {}


def test_blackboard_byte_cap() -> None:
    board = Blackboard(max_bytes=8)
    board.put("a", "1234", "coder")
    with pytest.raises(BlackboardFullError):
        board.put("b", "12345", "coder")
