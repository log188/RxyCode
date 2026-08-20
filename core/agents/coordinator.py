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
from pathlib import Path
from typing import Any, Callable, Protocol

from RxyCode.RxyCode1_1_0.core.agents.blackboard import Blackboard
from RxyCode.RxyCode1_1_0.core.agents.budget import BudgetExceeded, BudgetGuard
from RxyCode.RxyCode1_1_0.core.agents.mailbox import Mailbox
from RxyCode.RxyCode1_1_0.core.agents.runtime import AgentRuntime, LiveRoleRuntime
from RxyCode.RxyCode1_1_0.core.agents.team_prompt import compact_summary
from RxyCode.RxyCode1_1_0.core.prompts.templates import DELEGATE_REQUEST_TEMPLATE
from RxyCode.RxyCode1_1_0.protocol.subagents import ContextEnvelope
from RxyCode.RxyCode1_1_0.core.agents.sop import SopMachine, StageRecord
from RxyCode.RxyCode1_1_0.core.agents.spec import validate_team
from RxyCode.RxyCode1_1_0.core.agents.verifier import MechanicalVerifier, subject_hash
from RxyCode.RxyCode1_1_0.core.tracing import (
    Tracer,
    distillation_ui_notice,
    format_current_role,
)
from RxyCode.RxyCode1_1_0.protocol.agents import (
    AgentSpec,
    ConsultRequest,
    SopStage,
    TeamEvent,
    TeamSpec,
    VerdictRecord,
)
from RxyCode.RxyCode1_1_0.protocol.notifications import AgentEvent, ProgressUpdate

_WRITE_TOOLS = frozenset({"write", "edit", "patch"})
_WRITE_HINTS = ("write", "edit", "file", "patch", "写文件", "修改文件")
_STAGE_LABELS = {
    "plan": "正在制定方案",
    "implement": "正在实现",
    "audit": "正在审计",
}


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
        self._budget = budget or BudgetGuard()
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
        self._tracer = Tracer(run_id=session.session_id, manage_retention=False)
        self._trace_parent = ""
        self._last_delegate_id = ""
        self._delegate_by_stage: dict[str, str] = {}
        self.current_role_display = ""
        self.mode = "TEAM"
        self.decided_by = "heuristic"

    def form_team(self, team: TeamSpec) -> TeamSpec:
        """只有团长能建团。 Bind per-role runtimes when a live Primary is present."""
        validate_team(team)
        if not self._runtimes:
            self._runtimes = self._live_runtimes(team)
        self._emit_team_created(team)
        return team

    def _live_runtimes(self, team: TeamSpec) -> dict[str, Any]:
        primary = getattr(self._session, "_active_agent", None)
        if primary is None:
            return {}
        bound: dict[str, Any] = {}
        for member in team.members:
            if member.mechanical:
                continue
            bound[member.role] = LiveRoleRuntime(
                member, session=self._session, primary=primary
            )
        return bound

    def member_form_team(self, _member: AgentSpec, _team: TeamSpec) -> None:
        raise MemberForbiddenError("members may not create teams")

    async def run_team(
        self,
        team: TeamSpec,
        user_input: str,
        *,
        budget_overrides: dict[str, Any] | None = None,
    ) -> str:
        """跑完一整支专家团。"""
        self.form_team(team)
        if budget_overrides:
            self._budget = BudgetGuard(team, overrides=budget_overrides)
        self._budget.start(team)
        notice = distillation_ui_notice()
        if notice:
            self._emit(ProgressUpdate(session_id=self._session.session_id, text=notice))
        self._coordinator_history.append(user_input)
        self.task_ledger.facts.append(user_input)
        self.task_ledger.plan = [stage.name for stage in team.stages]
        root = self._tracer.start_span(
            "team",
            session_id=self._session.session_id,
            team=team.name,
            mode=self.mode,
            decided_by=self.decided_by,
            kind="team",
        )
        self._trace_parent = root.span_id
        self._last_delegate_id = ""
        self._delegate_by_stage = {}

        sop = SopMachine(team)
        try:
            while (stage := sop.current_stage()) is not None:
                self._budget.check()
                add = getattr(self._budget, "add_delegation", None)
                if callable(add):
                    add()
                self._precheck(stage, team)
                self._emit(
                    TeamEvent(
                        session_id=self._session.session_id,
                        role=stage.role,
                        stage=stage.name,
                        phase="stage_started",
                    )
                )
                self._emit_role_progress(stage.role, stage.name)
                delegated = self._record_span(
                    "delegate",
                    kind="delegate",
                    role=stage.role,
                    stage=stage.name,
                )
                self._last_delegate_id = delegated.span_id
                self._delegate_by_stage[stage.name] = delegated.span_id
                result = await self._dispatch(stage, team, user_input)
                result = self._apply_verify_gates(stage, result)
                if stage.verify_before_next:
                    self._record_span(
                        "verify",
                        kind="verify",
                        role=stage.role,
                        stage=stage.name,
                        parent_id=delegated.span_id,
                        detail="; ".join(stage.verify_before_next),
                        ok=result.ok,
                    )
                    self._emit(
                        TeamEvent(
                            session_id=self._session.session_id,
                            role=stage.role,
                            stage=stage.name,
                            phase="verified",
                            detail="; ".join(stage.verify_before_next),
                        )
                    )
                if stage.audit_after_verify:
                    self._record_span(
                        "audit",
                        kind="audit",
                        role="auditor",
                        stage=stage.name,
                        parent_id=delegated.span_id,
                        ok=result.ok,
                    )
                    self._emit(
                        TeamEvent(
                            session_id=self._session.session_id,
                            role="auditor",
                            stage=stage.name,
                            phase="audited",
                        )
                    )
                self.blackboard.put(stage.output_key, result.answer, stage.role)
                self.record_progress(made_progress=result.ok, looping=not result.ok)
                nxt = sop.advance(ok=result.ok)
                if nxt is None:
                    break
        except BudgetExceeded as exc:
            self._finish_root(root)
            return self._partial_result(sop, team, exc)
        self._finish_root(root)
        return self._synthesize(sop.history())

    def _finish_root(self, root: Any) -> None:
        snap = getattr(self._budget, "snapshot", None)
        budget = snap() if callable(snap) else {}
        if budget:
            root.budget = dict(budget)
            root.tokens = int(budget.get("tokens_used") or 0)
        rate = self._cache_hit_rate()
        root.cache_hit_rate = rate
        if rate is not None and rate < 0.85:
            import logging

            logging.getLogger(__name__).warning("team cache_hit_rate %s < 0.85", rate)
            self._seq += 1
            self._emit(
                AgentEvent(
                    method="event/agent_done",
                    session_id=self._session.session_id,
                    agent_id="coordinator",
                    seq=self._seq,
                    tokens_used=int(root.tokens or 0),
                    budget_used=0,
                    cache_miss_warning=True,
                )
            )
        self._tracer.end_span(
            root,
            token_usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": int(root.tokens or 0),
            },
        )

    @staticmethod
    def _cache_hit_rate() -> float:
        try:
            from RxyCode.RxyCode1_1_0.utils.streaming import token_stats

            return float(getattr(token_stats, "cache_hit_rate", 0.0) or 0.0)
        except Exception:
            return 0.0

    def _partial_result(self, sop: SopMachine, team: TeamSpec, exc: BudgetExceeded) -> str:
        done = len(sop.history())
        total = max(1, len(team.stages))
        body = self._synthesize(sop.history())
        return (
            f"{body}\n\n因为超出预算而提前停止，已完成 {done}/{total} 个阶段。 "
            f"({exc})"
        )

    def store_verdict(self, record: VerdictRecord) -> None:
        self._verdicts[record.subject_hash] = record

    def verdict_allows(self, digest: str) -> bool:
        record = self._verdicts.get(digest)
        return bool(record and record.passed and record.subject_hash == digest)

    def _apply_verify_gates(self, stage: SopStage, result: StageOutcome) -> StageOutcome:
        digest = subject_hash(result.answer, result.diff)
        if stage.verify_before_next:
            verifier = self._verifier or MechanicalVerifier()
            workspace = Path(getattr(self._session, "workspace_root", ".") or ".")
            from RxyCode.RxyCode1_1_0.core.agents.verifier import VerifyContext

            ctx = VerifyContext(
                workspace=workspace,
                stage_output=result.answer,
                expected_output=stage.expected_output,
                diff=result.diff,
            )
            try:
                verdict = verifier.run(stage, result, ctx=ctx)
            except TypeError:
                verdict = verifier.run(stage, result)
            if not verdict.passed:
                result.ok = False
                result.error = "; ".join(verdict.findings)
                return result
        if stage.audit_after_verify and result.ok and not self.verdict_allows(digest):
            if getattr(self._session, "_active_agent", None) is None:
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
        refs = [f"blackboard://{key}" for key in stage.context_keys]
        tools = "all" if member.tools is None else ",".join(member.tools)
        goal = DELEGATE_REQUEST_TEMPLATE.format(
            goal=f"{user_input}\nstage={stage.name}\nrole_goal={member.goal}",
            expected_output=stage.expected_output,
            tools=tools,
            context_refs=",".join(refs) or "(none)",
        )
        ContextEnvelope(
            parent_session_id=self._session.session_id,
            task=stage.expected_output,
            attachments=tuple(refs),
        )
        return DispatchPacket(
            to_role=stage.role,
            goal=goal,
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
            agent = getattr(self._session, "_active_agent", None)
            if agent is not None:
                member = next(m for m in team.members if m.role == stage.role)
                runtime = LiveRoleRuntime(
                    member, session=self._session, primary=agent
                )
                self._runtimes[stage.role] = runtime
            else:
                return StageOutcome(
                    ok=True,
                    answer=compact_summary(f"[{stage.role}] {stage.expected_output}"),
                    packet=packet,
                )
        from protocol.subagents import TaskRequest

        child = await runtime.run(
            TaskRequest(
                parent_session_id=self._session.session_id,
                agent_id=stage.role,
                prompt=packet.goal,
            )
        )
        status = getattr(child, "status", None)
        status_value = str(getattr(status, "value", status) or "").lower()
        ok = (
            status is None
            or status is True
            or status_value in {"completed", "ok", "succeeded", "success"}
        )
        summary = getattr(child, "summary", "") or getattr(child, "answer", "")
        return StageOutcome(
            ok=ok,
            answer=compact_summary(str(summary)),
            packet=packet,
        )

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
        self._record_span(
            "consult",
            kind="consult",
            role=request.from_role,
            stage=request.stage,
            parent_id=self._delegate_by_stage.get(request.stage)
            or self._last_delegate_id
            or self._trace_parent,
            detail=f"{request.from_role} → {request.to_role} {request.question[:40]}",
        )
        self._emit(
            TeamEvent(
                session_id=self._session.session_id,
                role=request.from_role,
                stage=request.stage,
                phase="consulted",
                detail=request.question[:80],
            )
        )
        return reply

    def _record_span(
        self,
        name: str,
        *,
        kind: str,
        role: str,
        stage: str,
        parent_id: str = "",
        detail: str = "",
        ok: bool = True,
        tokens: int = 0,
    ):
        depth = 0 if kind == "team" else 1 if kind == "delegate" else 2
        span = self._tracer.start_span(
            name,
            task_id=self._session.session_id,
            role=role,
            stage=stage,
            kind=kind,
            parent_id=parent_id or self._trace_parent,
            detail=detail,
            session_id=self._session.session_id,
            delegation_depth=depth,
        )
        self._tracer.end_span(
            span,
            status="ok" if ok else "error",
            token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": tokens},
        )
        self.current_role_display = format_current_role(span)
        return span

    def _emit_role_progress(self, role: str, stage: str) -> None:
        label = _STAGE_LABELS.get(stage, stage)
        snap = getattr(self._budget, "snapshot", None)
        budget = snap() if callable(snap) else {}
        used = int(budget.get("tokens_used") or 0)
        cap = int(budget.get("token_budget") or 0)
        budget_txt = f"{used}/{cap}" if cap else ""
        text = f"[{role}] {label}..."
        if budget_txt:
            text = f"{text} {budget_txt}"
        self.current_role_display = f"{role} @ {stage}".strip(" @")
        self._emit(
            ProgressUpdate(
                session_id=self._session.session_id,
                text=f"──────── {stage} · {role} ────────",
            )
        )
        self._emit(ProgressUpdate(session_id=self._session.session_id, text=text))

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
