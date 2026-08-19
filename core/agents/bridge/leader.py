"""Star-topology Leader. Workers never talk to each other (DC2)."""

from __future__ import annotations

from typing import Any, Callable

from RxyCode.RxyCode1_1_0.core.agents.blackboard import Blackboard
from RxyCode.RxyCode1_1_0.core.agents.bridge.worker import BridgeWorker
from RxyCode.RxyCode1_1_0.core.agents.mailbox import Mailbox
from RxyCode.RxyCode1_1_0.core.tracing import Tracer
from RxyCode.RxyCode1_1_0.protocol.agents import BridgeResult, TaskDelegate
from RxyCode.RxyCode1_1_0.protocol.notifications import ProgressUpdate


class BridgeLeader:
    """Coordinator-facing façade: relay every hop, span the edges, write the board."""

    def __init__(
        self,
        *,
        session_id: str,
        mailbox: Mailbox | None = None,
        blackboard: Blackboard | None = None,
        tracer: Tracer | None = None,
        emit: Callable[[Any], None] | None = None,
    ) -> None:
        self.session_id = session_id
        self.mailbox = mailbox or Mailbox()
        self.blackboard = blackboard or Blackboard()
        self._tracer = tracer or Tracer(run_id=session_id, manage_retention=False)
        self._emit = emit

    def dispatch(self, worker: BridgeWorker, request: TaskDelegate) -> BridgeResult:
        self.mailbox.relay(
            from_role="coordinator",
            to_role=worker.role,
            body=request.goal,
            relayed_by="coordinator",
            kind="task_delegate",
        )
        span = self._tracer.start_span(
            "delegate",
            task_id=request.task_id,
            role=worker.role,
            kind="delegate",
            session_id=self.session_id,
            detail=request.goal[:80],
        )
        if self._emit is not None:
            self._emit(
                ProgressUpdate(
                    session_id=self.session_id,
                    text=f"[{worker.role}] {request.task_id}",
                )
            )
        try:
            result = worker.delegate(request)
        except Exception:
            self._tracer.end_span(span, status="error")
            raise
        self._tracer.end_span(
            span,
            token_usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": result.tokens_used,
            },
        )
        result_span = self._tracer.start_span(
            "result",
            task_id=request.task_id,
            role=worker.role,
            kind="delegate",
            session_id=self.session_id,
        )
        self._tracer.end_span(
            result_span,
            status="ok" if result.ok else "error",
            token_usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": result.tokens_used,
            },
        )
        self.mailbox.relay(
            from_role=worker.role,
            to_role="coordinator",
            body=result.summary,
            relayed_by="coordinator",
            kind="result",
        )
        self.blackboard.put(f"bridge:{request.task_id}", result.summary, worker.role)
        return result
