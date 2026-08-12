"""Server -> client one-way notifications (SSE sources in api_server.py)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .types import JobState, JsonObject, RunStatus


class MessageDelta(BaseModel):
    """SSE ``type: token`` via ``StreamTUI._buffer("token")`` / flush (api_server.py)."""

    method: Literal["event/message_delta"] = "event/message_delta"
    session_id: str
    text: str


class ProgressUpdate(BaseModel):
    """SSE ``type: progress`` from ``StreamTUI.write_progress`` (api_server.py)."""

    method: Literal["event/progress"] = "event/progress"
    session_id: str
    text: str


class ReasoningSnapshot(BaseModel):
    """SSE ``type: reasoning`` with ``snapshot: true`` from ``StreamTUI._emit_thinking_snapshot`` (api_server.py)."""

    method: Literal["event/reasoning_snapshot"] = "event/reasoning_snapshot"
    session_id: str
    text: str
    snapshot: bool = True


class PlanUpdate(BaseModel):
    """SSE ``type: plan`` from ``StreamTUI.write_plan`` (api_server.py)."""

    method: Literal["event/plan"] = "event/plan"
    session_id: str
    steps: list[str]


class StepProgress(BaseModel):
    """SSE ``type: step`` from ``StreamTUI.write_step`` (api_server.py)."""

    method: Literal["event/step"] = "event/step"
    session_id: str
    index: int
    total: int
    text: str


class TaskStarted(BaseModel):
    """Structured task boundary for LangGraph runs (future emit from chat worker)."""

    method: Literal["event/task_started"] = "event/task_started"
    session_id: str
    task_id: str
    title: str


class ToolBegin(BaseModel):
    """SSE ``type: tool_call`` from ``StreamTUI.write_tool_call`` (api_server.py)."""

    method: Literal["event/tool_begin"] = "event/tool_begin"
    session_id: str
    call_id: str
    tool_name: str
    arguments: JsonObject = Field(default_factory=dict)


class ToolEnd(BaseModel):
    """SSE ``type: tool_result`` from ``StreamTUI.write_tool_result`` (api_server.py)."""

    method: Literal["event/tool_end"] = "event/tool_end"
    session_id: str
    call_id: str
    ok: bool
    summary: str
    status: str | None = None


class TaskComplete(BaseModel):
    """Structured task completion paired with ``TaskStarted``."""

    method: Literal["event/task_complete"] = "event/task_complete"
    session_id: str
    task_id: str
    ok: bool


class TokenUsage(BaseModel):
    """Reported token usage; unknown provider values stay explicitly null."""

    method: Literal["event/token_usage"] = "event/token_usage"
    session_id: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_hit_tokens: int | None = None
    cache_write_tokens: int | None = None
    cache_hit_rate: float | None = None
    reporting_status: Literal["reported", "partial", "not_reported"] = "reported"


class FinalAnswer(BaseModel):
    """SSE ``type: final`` payload in ``/chat/stream`` worker (api_server.py)."""

    method: Literal["event/final"] = "event/final"
    session_id: str
    run_id: str
    text: str
    thinking: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_hit_tokens: int | None = None
    cache_write_tokens: int | None = None
    cache_hit_rate: float | None = None
    reporting_status: Literal["reported", "partial", "not_reported"] = "reported"
    session_schema_version: int | None = None


class RecoveryEventBase(BaseModel):
    """Common cursor-safe envelope for recovery lifecycle notifications."""

    session_id: str
    run_id: str
    recovery_id: str
    event_id: str
    seq: int
    timestamp: str


class RecoveryStarted(RecoveryEventBase):
    """Recovery budget opened after an operational failure."""
    method: Literal["event/recovery_started"] = "event/recovery_started"
    source_call_id: str
    recovery_kind: Literal["transport_retry", "model_recovery", "graph_replan"]
    error_kind: str
    max_attempts: int


class RecoveryAnalyzing(RecoveryEventBase):
    """Recovery planner is selecting the next user-safe strategy."""
    method: Literal["event/recovery_analyzing"] = "event/recovery_analyzing"


class RecoveryAttempt(RecoveryEventBase):
    """One concrete recovery strategy has been scheduled."""
    method: Literal["event/recovery_attempt"] = "event/recovery_attempt"
    attempt: int
    strategy: Literal[
        "same_tool",
        "corrected_arguments",
        "alternative_tool",
        "retry_task",
        "replan",
    ]
    replacement_call_id: str | None = None
    display_summary: str


class RecoveryResolved(RecoveryEventBase):
    """Recovery completed and the task returned to normal execution."""
    method: Literal["event/recovery_resolved"] = "event/recovery_resolved"
    attempts: int
    display_summary: str


class RecoveryExhausted(RecoveryEventBase):
    """Recovery budget was exhausted and a terminal error may be shown."""
    method: Literal["event/recovery_exhausted"] = "event/recovery_exhausted"
    attempts: int
    final_error: str


class ErrorNotification(BaseModel):
    """SSE ``type: error`` from ``StreamTUI.write_error`` and chat worker (api_server.py)."""

    method: Literal["event/error"] = "event/error"
    session_id: str
    message: str
    run_id: str | None = None
    status: RunStatus | None = None


class RunComplete(BaseModel):
    """SSE ``type: done`` from chat stream teardown (api_server.py)."""

    method: Literal["event/done"] = "event/done"
    session_id: str
    run_id: str
    status: RunStatus


class JobStatusUpdate(BaseModel):
    """Background job state for watchdog / appserver (submitted|running|failed)."""

    method: Literal["event/job_status"] = "event/job_status"
    session_id: str
    job_id: str
    state: JobState



class ServerHeartbeat(BaseModel):
    """Periodic appserver liveness signal (T4 watchdog)."""

    method: Literal["event/server_heartbeat"] = "event/server_heartbeat"
    uptime_seconds: float
    active_jobs: int
    degraded: bool


NOTIFICATION_MODELS: tuple[type[BaseModel], ...] = (
    MessageDelta,
    ProgressUpdate,
    ReasoningSnapshot,
    PlanUpdate,
    StepProgress,
    TaskStarted,
    ToolBegin,
    ToolEnd,
    TaskComplete,
    TokenUsage,
    FinalAnswer,
    RecoveryStarted,
    RecoveryAnalyzing,
    RecoveryAttempt,
    RecoveryResolved,
    RecoveryExhausted,
    ErrorNotification,
    RunComplete,
    JobStatusUpdate,
    ServerHeartbeat,
)
