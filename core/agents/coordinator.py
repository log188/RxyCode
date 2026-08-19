"""Coordinator：专家团团长。

职责（抄腾讯 WorkBuddy 专家团主理人，见 PHASE-F §2.3）：
  ① 建团   只有团长能建团，成员不得创建子团队（DC6）
  ② 派活   按 SOP 阶段下发自包含任务
  ③ 中转   所有跨成员消息必经此处（DC2）
  ④ 收口   汇总产出，决定是否进入下一阶段

团长自己**不写代码、不调业务工具**。它的工具集是空的，只能调协调动作。
这是刻意的：团长一旦开始干活，就会和成员抢上下文，而且它的上下文是全局
最宝贵的。

F8 MechanicalVerifier 是默认机械门；F9 BudgetGuard 仍可注入（缺省 noop）。
进入下一阶段前：机械检查不过就打回；audit_after_verify 还要求
当前产出 hash 上有 passed=True 的 VerdictRecord。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from RxyCode.RxyCode1_1_0.core.agents.blackboard import Blackboard
from RxyCode.RxyCode1_1_0.core.agents.mailbox import Mailbox
from RxyCode.RxyCode1_1_0.core.agents.runtime import AgentRuntime
from RxyCode.RxyCode1_1_0.core.agents.sop import SopMachine, StageRecord
from RxyCode.RxyCode1_1_0.core.agents.spec import validate_team
from RxyCode.RxyCode1_1_0.core.agents.verifier import MechanicalVerifier, subject_hash
from RxyCode.RxyCode1_1_0.protocol.agents import (
    AgentSpec,
    ConsultRequest,
    SopStage,
    TeamEvent,
    TeamSpec,
    VerdictRecord,
)
from RxyCode.RxyCode1_1_0.protocol.notifications import AgentEvent

_WRITE_TOOLS = frozenset({"write", "edit", "patch"})
_WRITE_HINTS = ("write", "edit", "file", "patch", "写文件", "修改文件")


class CoordinatorError(RuntimeError):
    """Coordinator refused a team action."""


class PrecheckError(CoordinatorError):
    """Stage role cannot perform the required tools."""


class MemberForbiddenError(CoordinatorError):
    """Members must not create sub-teams (DC6)."""


class ConsultDenied(CoordinatorError):
    """may_consult does not allow this target."""


class ConsultBudgetExceeded(CoordinatorError):
    """Consult count or token budget exhausted."""


@dataclass
class TaskLedger:
    """Outer-loop book (Magentic-One)."""

    facts: list[str] = field(default_factory=list)
    facts_to_lookup: list[str] = field(default_factory=list)
    facts_to_derive: list[str] = field(default_factory=list)
    educated_guesses: list[str] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)


@dataclass
class ProgressLedger:
    """Inner-loop book (Magentic-One)."""

    done: bool = False
    looping: bool = False
    made_progress: bool = False
    next_speaker: str = ""
    instruction: str = ""
    delegations: list[dict[str, str]] = field(default_factory=list)
    stall_count: int = 0


@dataclass
class DispatchPacket:
    """Self-contained member task. Coordinator history is never attached."""

    to_role: str
    goal: str
    expected_output: str
    tools: list[str] | None
    done_when: str
    context_keys: list[str]
    context: dict[str, str]
    coordinator_history: None = None


@dataclass
class StageOutcome:
    ok: bool
    answer: str
    error: str = ""
    packet: DispatchPacket | None = None
    diff: str = ""
    verify_ctx: Any | None = None


@dataclass
class VerifyVerdict:
    passed: bool
    findings: list[str] = field(default_factory=list)


class _BudgetLike(Protocol):
    def start(self, team: TeamSpec) -> None: ...
    def check(self) -> None: ...


class _NoopBudget:
    def start(self, team: TeamSpec) -> None:
        return None

    def check(self) -> None:
        return None


class Coordinator:
    """团长：空工具集，只调度。"""

    tools: list[str] = []

    def __init__(
        self,
        session: Any,
        *,
        runtimes: dict[str, AgentRuntime] | None = None,
        verifier: Any | None = None,
        budget: _BudgetLike | None = None,
        emit: Callable[[Any], None] | None = None,
    ) -> None:
        self.tools = []
        self._session = session
        self._runtimes = runtimes or {}
        self._verifier = verifier
        self._budget = budget or _NoopBudget()
        self._emit_fn = emit if emit is not None else getattr(session, "emit", None)
        self._seq = 0
        self.events: list[Any] = []
        self.mailbox = Mailbox()
        self.blackboard = Blackboard()
        self._coordinator_history: list[str] = []
        self.task_ledger = TaskLedger()
        self.progress_ledger = ProgressLedger()
        self.last_replan: str | None = None
        self._consults = 0
        self._consult_tokens = 0
        self.max_consults = 8
        self.max_consult_tokens = 20_000
        self._verdicts: dict[str, VerdictRecord] = {}

    def form_team(self, team: TeamSpec) -> TeamSpec:
        """只有团长能建团。"""
        validate_team(team)
        self._emit_team_created(team)
        return team

    def member_form_team(self, _member: AgentSpec, _team: TeamSpec) -> None:
        raise MemberForbiddenError("members may not create teams")

    async def run_team(self, team: TeamSpec, user_input: str) -> str:
        """跑完一整支专家团。"""
        self.form_team(team)
        self._budget.start(team)
        self._coordinator_history.append(user_input)
        self.task_ledger.facts.append(user_input)
        self.task_ledger.plan = [stage.name for stage in team.stages]

        sop = SopMachine(team)
        while (stage := sop.current_stage()) is not None:
            self._budget.check()
            self._precheck(stage, team)
            result = await self._dispatch(stage, team, user_input)
            result = self._apply_verify_gates(stage, result)
            self.blackboard.put(stage.output_key, result.answer, stage.role)
            self.record_progress(made_progress=result.ok, looping=not result.ok)
            nxt = sop.advance(ok=result.ok)
            if nxt is None:
                break
        return self._synthesize(sop.history())

    def store_verdict(self, record: VerdictRecord) -> None:
        self._verdicts[record.subject_hash] = record

    def verdict_allows(self, digest: str) -> bool:
        record = self._verdicts.get(digest)
        return bool(record and record.passed and record.subject_hash == digest)

    def _apply_verify_gates(self, stage: SopStage, result: StageOutcome) -> StageOutcome:
        digest = subject_hash(result.answer, result.diff)
        if stage.verify_before_next:
            verifier = self._verifier or MechanicalVerifier()
            verdict = verifier.run(stage, result)
            if not verdict.passed:
                result.ok = False
                result.error = "; ".join(verdict.findings)
                return result
        if stage.audit_after_verify and result.ok and not self.verdict_allows(digest):
            result.ok = False
            result.error = "missing or stale VerdictRecord for current subject_hash"
        return result

    def _precheck(self, stage: SopStage, team: TeamSpec) -> None:
        member = next(m for m in team.members if m.role == stage.role)
        if not self._stage_needs_write(stage):
            return
        if member.tools is None:
            return
        if _WRITE_TOOLS.isdisjoint(member.tools):
            raise PrecheckError(
                f"stage {stage.name!r} needs a write tool but role "
                f"{member.role!r} has {member.tools!r}"
            )

    @staticmethod
    def _stage_needs_write(stage: SopStage) -> bool:
        blob = f"{stage.name} {stage.expected_output} {stage.output_key}".lower()
        return any(hint in blob for hint in _WRITE_HINTS)

    def _packet(self, stage: SopStage, team: TeamSpec, user_input: str) -> DispatchPacket:
        member = next(m for m in team.members if m.role == stage.role)
        context = self.blackboard.view(list(stage.context_keys))
        return DispatchPacket(
            to_role=stage.role,
            goal=f"{user_input}\nstage={stage.name}\nrole_goal={member.goal}",
            expected_output=stage.expected_output,
            tools=None if member.tools is None else list(member.tools),
            done_when=stage.expected_output,
            context_keys=list(stage.context_keys),
            context=context,
            coordinator_history=None,
        )

    async def _dispatch(self, stage: SopStage, team: TeamSpec, user_input: str) -> StageOutcome:
        packet = self._packet(stage, team, user_input)
        self.progress_ledger.delegations.append(
            {"role": stage.role, "stage": stage.name}
        )
        runtime = self._runtimes.get(stage.role)
        if runtime is None:
            return StageOutcome(ok=True, answer=f"[{stage.role}] {stage.expected_output}", packet=packet)
        from protocol.subagents import TaskRequest

        child = await runtime.run(
            TaskRequest(
                parent_session_id=self._session.session_id,
                agent_id=stage.role,
                prompt=packet.goal,
            )
        )
        ok = getattr(child, "status", None)
        summary = getattr(child, "summary", "") or getattr(child, "answer", "")
        return StageOutcome(ok=ok is None or str(ok).endswith("completed") or ok is True, answer=str(summary), packet=packet)

    def consult(
        self,
        team: TeamSpec,
        request: ConsultRequest,
        *,
        answer: str | None = None,
    ) -> str:
        """Member → coordinator → member. Never a direct hop."""
        source = next((m for m in team.members if m.role == request.from_role), None)
        if source is None or request.to_role not in source.may_consult:
            raise ConsultDenied(
                f"{request.from_role!r} may not consult {request.to_role!r}"
            )
        if request.to_role not in {m.role for m in team.members}:
            raise ConsultDenied(f"unknown consult target {request.to_role!r}")
        cost = max(1, len(request.question))
        if self._consults >= self.max_consults or (
            self._consult_tokens + cost > self.max_consult_tokens
        ):
            raise ConsultBudgetExceeded("consult budget exceeded")
        consume = getattr(self._budget, "consume_consult", None)
        if callable(consume):
            consume()
        self._consults += 1
        self._consult_tokens += cost
        self.mailbox.relay(
            from_role=request.from_role,
            to_role=request.to_role,
            body=request.question,
            relayed_by="coordinator",
            kind="consult_q",
        )
        reply = answer if answer is not None else f"ack:{request.question}"
        self.mailbox.relay(
            from_role=request.to_role,
            to_role=request.from_role,
            body=reply,
            relayed_by="coordinator",
            kind="consult_a",
        )
        self.blackboard.put(f"consult:{request.request_id}", reply, request.to_role)
        return reply

    def choose_failure_target(self, candidates: list[str]) -> str:
        """唯一 LLM 决策点：失败后多个候选。其余转移走 SopMachine。"""
        if not candidates:
            raise CoordinatorError("no failure candidates")
        chosen = candidates[0]
        self._seq += 1
        event = TeamEvent(
            session_id=self._session.session_id,
            role="coordinator",
            stage="",
            phase="delegated",
            detail="llm_route_decision",
        )
        self._emit(event)
        return chosen

    def record_progress(self, *, made_progress: bool, looping: bool = False) -> None:
        self.progress_ledger.made_progress = made_progress
        self.progress_ledger.looping = looping
        if (not made_progress) or looping:
            self.progress_ledger.stall_count += 1
        else:
            self.progress_ledger.stall_count = 0
        if self.progress_ledger.stall_count >= 2:
            self._reflect_and_replan()

    def _reflect_and_replan(self) -> None:
        note = "stall: no progress twice; replan"
        self.last_replan = note
        self.task_ledger.plan.append(note)
        self.progress_ledger.stall_count = 0
        self._seq += 1
        self._emit(
            TeamEvent(
                session_id=self._session.session_id,
                role="coordinator",
                stage="",
                phase="failed",
                detail="stall_replan",
            )
        )

    def _synthesize(self, history: list[StageRecord]) -> str:
        names = " -> ".join(record.stage for record in history)
        return names or "empty"

    def _emit_team_created(self, team: TeamSpec) -> None:
        self._seq += 1
        self._emit(
            AgentEvent(
                method="event/agent_team_created",
                session_id=self._session.session_id,
                agent_id="coordinator",
                seq=self._seq,
                tokens_used=0,
                budget_used=0,
                payload={"team": team.name},
            )
        )

    def _emit(self, event: Any) -> None:
        self.events.append(event)
        if self._emit_fn is not None:
            self._emit_fn(event)
