"""Server -> client one-way notifications (SSE sources in api_server.py)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, Strict, model_validator

from .types import JobState, JsonObject, RunStatus


# ---------------------------------------------------------------------------
# Phase E · E4 — agent runtime event domain (PHASE-E §4.1)
#
# EB1: add-only.  The ten methods below are the frozen AgentMethod list;
# later additions append, never rename/remove.  The field matrix (per-method
# required/optional/forbidden) is enforced by ``AgentEvent`` validation.
# ``event/team_*`` belongs to the F-layer TeamEvent; AgentEvent must never
# accept it (no default fallback).
# ---------------------------------------------------------------------------

AgentMethod = Literal[
    "event/agent_started",
    "event/agent_tool",
    "event/agent_progress",
    "event/agent_done",
    "event/agent_paused",
    "event/agent_cancelled",
    "event/agent_budget_exceeded",
    "event/agent_denied",
    "event/agent_routed",
    "event/agent_team_created",
]

ExperimentTag = Literal["E0", "E1", "E2"]

#: Methods that must carry routing metadata (F10 projection).
_ROUTED_METHODS = frozenset({"event/agent_routed"})

#: Methods that must never carry routing metadata (forbid).
_ROUTING_FORBIDDEN = frozenset(
    {
        "event/agent_started",
        "event/agent_tool",
        "event/agent_progress",
        "event/agent_done",
        "event/agent_paused",
        "event/agent_cancelled",
        "event/agent_budget_exceeded",
        "event/agent_denied",
        "event/agent_team_created",
    }
)

#: Methods that must carry the cumulative token snapshot (F14 anchor).
_BUDGET_SNAPSHOT_REQUIRED = frozenset({"event/agent_budget_exceeded"})


class AgentEvent(BaseModel):
    """Runtime agent event (Phase E4; E-layer bus carries these).

    Field matrix (PHASE-E §4.1, authoritative):
      method                | experiment_tag | cache_miss | tokens | budget | source | routing_reason
      ----------------------|--------------- |------------|--------|--------|--------|---------------
      agent_started         | opt            | opt        | req*   | req*   | opt    | forbid
      agent_tool            | opt            | opt        | req*   | req*   | opt    | forbid
      agent_progress        | opt            | opt        | req*   | req*   | opt    | forbid
      agent_done            | opt            | opt        | req*   | req*   | opt    | forbid
      agent_paused          | opt            | opt        | req*   | req*   | opt    | forbid
      agent_cancelled       | opt            | opt        | req*   | req*   | opt    | forbid
      agent_budget_exceeded | opt            | opt        | **req  | **req  | opt    | forbid
      agent_denied          | opt            | opt        | req*   | req*   | opt    | forbid
      agent_routed          | **req          | opt        | req*   | req*   | opt    | **req
      agent_team_created    | forbid         | opt        | req*   | req*   | opt    | forbid

    ``req*`` = the E3 runtime always writes these (0 at spawn, monotonic);
    the schema compatibility layer allows them to be absent (historical
    events).  ``**req`` = hard requirement at this layer; ``forbid`` =
    carrying the field is rejected.  ``tokens_used``/``budget_used`` are
    strict ints (bool/str/float rejected) and non-negative cumulative
    snapshots.  ``source`` distinguishes bridge-replayed events; unknown
    values are rejected on construction and deserialization.
    """

    method: AgentMethod
    session_id: str
    agent_id: str
    run_id: str | None = None
    payload: JsonObject = Field(default_factory=dict)
    seq: int
    experiment_tag: ExperimentTag | None = None
    cache_miss_warning: bool = False
    tokens_used: Annotated[int, Strict()] | None = None
    budget_used: Annotated[int, Strict()] | None = None
    source: Literal["internal", "bridge"] | None = None
    routing_reason: str | None = None

    @model_validator(mode="after")
    def _check_field_matrix(self) -> "AgentEvent":
        if self.method in _ROUTED_METHODS:
            if self.experiment_tag is None:
                raise ValueError("event/agent_routed requires experiment_tag")
            if self.routing_reason is None:
                raise ValueError("event/agent_routed requires routing_reason")
        if self.method in _ROUTING_FORBIDDEN and self.routing_reason is not None:
            raise ValueError(
                f"{self.method} must not carry routing_reason"
            )
        if self.method == "event/agent_team_created" and self.experiment_tag is not None:
            raise ValueError(
                "event/agent_team_created must not carry experiment_tag"
            )
        if self.method in _BUDGET_SNAPSHOT_REQUIRED:
            if self.tokens_used is None or self.budget_used is None:
                raise ValueError(
                    "event/agent_budget_exceeded requires tokens_used and budget_used"
                )
        for name in ("tokens_used", "budget_used"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.experiment_tag is not None:
            _check_text_field("experiment_tag", self.experiment_tag, 256)
        if self.routing_reason is not None:
            _check_text_field("routing_reason", self.routing_reason, 256)
        return self


def _check_text_field(name: str, value: str, max_len: int) -> None:
    """Non-empty, length-capped, control-character-free text (PHASE-E §4.1)."""
    if not value:
        raise ValueError(f"{name} must be a non-empty string")
    if len(value) > max_len:
        raise ValueError(f"{name} must be at most {max_len} characters")
    if any(ch < " " for ch in value):
        raise ValueError(f"{name} must not contain control characters")


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
    """Token deltas from chat ``final`` SSE payload fields (api_server.py queue)."""

    method: Literal["event/token_usage"] = "event/token_usage"
    session_id: str
    input_tokens: int
    output_tokens: int
    cache_hit_tokens: int = 0
    cache_hit_rate: float = 0.0


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
    cache_hit_rate: float | None = None
    session_schema_version: int | None = None


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
    AgentEvent,
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
    ErrorNotification,
    RunComplete,
    JobStatusUpdate,
    ServerHeartbeat,
)
