"""Headless session facade over AgentV2 (Phase 2 strangler entry point)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

try:
    from ..protocol.notifications import ErrorNotification, FinalAnswer, TokenUsage
except ImportError:  # repo-root pytest/dev imports (top-level core + protocol)
    from protocol.notifications import ErrorNotification, FinalAnswer, TokenUsage

from RxyCode.RxyCode1_1_0.log.log_helpers import classify_agent_result
from RxyCode.RxyCode1_1_0.utils.streaming import token_stats


EmitCallback = Callable[[BaseModel], None]


@dataclass(frozen=True)
class PromptResult:
    """Terminal outcome of one Session.prompt() turn."""

    answer: str
    status: str
    detail: str = ""
    thinking: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_hit_tokens: int | None = None
    cache_write_tokens: int | None = None
    cache_hit_rate: float | None = None
    reporting_status: str = "not_reported"


def thinking_cursor(agent: Any) -> tuple[tuple[str, ...], str]:
    """Snapshot agent thinking state before a prompt."""
    history = tuple(str(item) for item in getattr(agent, "_thinking_history", []))
    return history, str(getattr(agent, "_last_thinking", "") or "")


def thinking_since(agent: Any, cursor: tuple[tuple[str, ...], str]) -> str:
    """Return thinking text produced since ``thinking_cursor``."""
    previous_history, previous_last = cursor
    current_history = tuple(
        str(item) for item in getattr(agent, "_thinking_history", [])
    )
    if current_history[: len(previous_history)] == previous_history:
        new_history = current_history[len(previous_history) :]
    else:
        new_history = current_history
    if new_history:
        return "\n".join(new_history)
    current_last = str(getattr(agent, "_last_thinking", "") or "")
    return current_last if current_last != previous_last else ""


def notification_to_sse_event(notification: BaseModel) -> dict[str, Any] | None:
    """Map protocol notifications to legacy HTTP SSE event dicts.

    P3 strangler scope: only terminal ``final`` / ``error`` events are converted
    here. Mid-run events (token, tool_call, approval_request, ...) still flow
    through ``StreamTUI`` until P4/P5 migrate the full emit path.
    """
    if isinstance(notification, FinalAnswer):
        event: dict[str, Any] = {
            "type": "final",
            "run_id": notification.run_id,
            "text": notification.text,
            "thinking": notification.thinking or "",
            # Preserve provider reporting semantics for the legacy SSE bridge.
            # ``None`` means the provider did not report the metric; converting
            # it to zero makes the Desktop under-report usage and cache rate.
            "input_tokens": notification.input_tokens,
            "output_tokens": notification.output_tokens,
            "cache_hit_tokens": notification.cache_hit_tokens,
            "cache_hit_rate": notification.cache_hit_rate,
        }
        if notification.session_schema_version is not None:
            event["session_schema_version"] = notification.session_schema_version
        return event
    if isinstance(notification, ErrorNotification):
        event = {
            "type": "error",
            "message": notification.message,
        }
        if notification.run_id is not None:
            event["run_id"] = notification.run_id
        if notification.status is not None:
            event["status"] = notification.status
        return event
    if isinstance(notification, TokenUsage):
        return None
    method = getattr(notification, "method", None)
    if isinstance(method, str) and method.startswith("event/"):
        return None
    return None


class Session:
    """One conversation session. No direct I/O — output flows through ``emit``."""

    def __init__(
        self,
        *,
        session_id: str,
        workspace_root: Path | str,
        emit: EmitCallback,
        session_schema_version: int | None = None,
    ) -> None:
        self.session_id = session_id
        self.workspace_root = Path(workspace_root)
        self.emit = emit
        self.session_schema_version = session_schema_version
        # Phase F: Session may hold many expert-role runtimes. Single-agent
        # is zero or one role="default" entry; prompt() still runs AgentV2.
        self.agent_runtimes: dict[str, Any] = {}
        self._shared_agent_memory: dict[str, Any] = {}

    async def prompt(
        self,
        agent: Any,
        text: str,
        *,
        mode: str,
        run_id: str,
        tui: Any | None = None,
        permission_mode: str | None = None,
    ) -> PromptResult:
        """Run one user turn through AgentV2 and emit terminal protocol events."""
        previous_input = token_stats.input_tokens
        previous_output = token_stats.output_tokens
        previous_cache_hit_tokens = token_stats.cache_hit_tokens
        cursor = thinking_cursor(agent)
        workspace = Path(self.workspace_root).expanduser().resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        if hasattr(agent, "_session_id"):
            agent._session_id = self.session_id
        if hasattr(agent, "_workspace_root"):
            agent._workspace_root = workspace

        from RxyCode.RxyCode1_1_0.core.session_runtime import (
            bind_session,
            reset_session_binding,
            set_working_directory,
        )

        session_token = bind_session(self.session_id)
        try:
            set_working_directory(workspace)
            try:
                if permission_mode is None:
                    answer = await agent.run(text, mode=mode)
                else:
                    from RxyCode.RxyCode1_1_0.execution.tool_orchestrator import permission_mode_override

                    with permission_mode_override(permission_mode):
                        answer = await agent.run(text, mode=mode)
            except Exception as exc:
                detail = str(exc)
                if tui is not None and hasattr(tui, "exhaust_active_recovery"):
                    tui.exhaust_active_recovery(detail)
                self.emit(
                    ErrorNotification(
                        session_id=self.session_id,
                        run_id=run_id,
                        message=detail,
                        status="failed",
                    )
                )
                return PromptResult(answer="", status="failed", detail=detail)

            status, detail = classify_agent_result(answer)
            delta_input = token_stats.input_tokens - previous_input
            delta_output = token_stats.output_tokens - previous_output
            delta_cache_hit_tokens = token_stats.cache_hit_tokens - previous_cache_hit_tokens
            cache_hit_rate = (
                max(delta_cache_hit_tokens, 0) / max(delta_input, 1) * 100
                if delta_input > 0
                else 0.0
            )
            thinking = thinking_since(agent, cursor)

            usage_reported = bool(delta_input or delta_output or delta_cache_hit_tokens)
            usage_kwargs = {
                "input_tokens": max(delta_input, 0) if usage_reported else None,
                "output_tokens": max(delta_output, 0) if usage_reported else None,
                "cache_hit_tokens": max(delta_cache_hit_tokens, 0) if usage_reported else None,
                "cache_hit_rate": cache_hit_rate if usage_reported else None,
                "reporting_status": "reported" if usage_reported else "not_reported",
            }
            self.emit(TokenUsage(session_id=self.session_id, **usage_kwargs))

            if status == "succeeded":
                if tui is not None and hasattr(tui, "resolve_active_recovery"):
                    tui.resolve_active_recovery()
                self.emit(
                    FinalAnswer(
                        session_id=self.session_id,
                        run_id=run_id,
                        text=answer,
                        thinking=thinking or None,
                        **usage_kwargs,
                        session_schema_version=self.session_schema_version,
                    )
                )
                return PromptResult(
                    answer=answer,
                    status=status,
                    detail=detail,
                    thinking=thinking,
                    **usage_kwargs,
                )

            if tui is not None and hasattr(tui, "exhaust_active_recovery"):
                tui.exhaust_active_recovery(detail)
            self.emit(
                ErrorNotification(
                    session_id=self.session_id,
                    run_id=run_id,
                    message=detail,
                    status=status,
                )
            )
            return PromptResult(
                answer=answer,
                status=status,
                detail=detail,
                thinking=thinking,
                **usage_kwargs,
            )
        finally:
            reset_session_binding(session_token)

    def interrupt(self, agent: Any) -> bool:
        """Request cancellation on the underlying agent, if supported."""
        cancel = getattr(agent, "cancel", None)
        if callable(cancel):
            return bool(cancel())
        return False
