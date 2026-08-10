"""Protocol TUI adapter: maps AgentV2 TUI calls to protocol notifications."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

try:
    from ..protocol.notifications import (
        MessageDelta,
        ProgressUpdate,
        ReasoningSnapshot,
        ToolBegin,
        ToolEnd,
    )
except ImportError:
    from protocol.notifications import (
        MessageDelta,
        ProgressUpdate,
        ReasoningSnapshot,
        ToolBegin,
        ToolEnd,
    )

EmitCallback = Callable[[BaseModel], None]


class ProtocolTui:
    """Minimal TUI surface for appserver: emit protocol models, no direct I/O.

    C3: when a StreamCoalescer is bound (``set_coalescer``), streaming kinds
    (token/reasoning/progress) are pushed into it so the worker writes stdout
    once per batch instead of once per token (RXYCODE_STREAM_COALESCE=1).
    Without a coalescer the legacy per-call emit path is kept unchanged
    (switch 0 = old behaviour).
    """

    def __init__(self, session_id: str, emit: EmitCallback) -> None:
        self.session_id = session_id
        self._emit = emit
        self._expand_thinking = False
        self._thinking_acc = ""
        self._mode = "build"
        self._model_name = ""
        self._coalescer: Any = None
        self._push_tasks: set[asyncio.Task[Any]] = set()
        self._push_failures: list[BaseException] = []

    def set_coalescer(self, coalescer: Any) -> None:
        """Bind a StreamCoalescer (C3); pass None to restore direct emit."""
        self._coalescer = coalescer

    @property
    def push_failures(self) -> list[BaseException]:
        return list(self._push_failures)

    async def drain_push_tasks(self) -> None:
        """Wait for ALL scheduled coalescer pushes before a final flush, so
        buffered tokens never race the trailing flush (C3 ordering).

        Loops until the task set is empty: a sync TUI callback that fires
        while draining (e.g. during a concurrent flush) creates another push
        task which is also awaited, so the drain is strict.  Exception
        collection is owned by the per-task done callback (``_on_push_done``),
        so failures are recorded exactly once; after the drain we yield once
        so callbacks run before the caller reads ``push_failures``.
        """
        while self._push_tasks:
            await asyncio.gather(*list(self._push_tasks), return_exceptions=True)
            await asyncio.sleep(0)  # let done callbacks / new pushes settle
        await asyncio.sleep(0)  # let final done callbacks collect failures

    async def push(self, kind: str, text: str) -> None:
        """Async push for streaming kinds: coalesce when bound, else emit."""
        coalescer = self._coalescer
        if coalescer is not None:
            await coalescer.push(kind, str(text))
            return
        self._emit_direct(kind, str(text))

    def _emit_direct(self, kind: str, text: str) -> None:
        """Single kind→notification mapping used by both the async push()
        fallback and the sync _push_async() legacy path (switch 0)."""
        if kind == "token":
            self._emit(MessageDelta(session_id=self.session_id, text=str(text)))
        elif kind == "reasoning":
            self._emit(
                ReasoningSnapshot(
                    session_id=self.session_id,
                    text=str(text),
                    snapshot=False,
                )
            )
        elif kind == "progress":
            self._emit(ProgressUpdate(session_id=self.session_id, text=str(text)))

    def set_thinking_expanded(self, expanded: bool) -> None:
        was = self._expand_thinking
        self._expand_thinking = bool(expanded)
        # Mid-run expand: push accumulated thinking so the client can show it.
        # The snapshot is a plain notification: order it after any buffered
        # stream content (barrier) so it cannot overtake earlier tokens.
        if self._expand_thinking and not was and self._thinking_acc:
            self._flush_pending_stream()
            self._emit(
                ReasoningSnapshot(
                    session_id=self.session_id,
                    text=self._thinking_acc,
                    snapshot=True,
                )
            )

    def get_thinking_expanded(self) -> bool:
        return self._expand_thinking

    def set_mode(self, mode: str) -> None:
        self._mode = str(mode)

    def set_model(self, model_name: str) -> None:
        self._model_name = str(model_name)

    def write_progress(self, text: str) -> None:
        self._push_async("progress", text)

    def write(self, text: str, color: str = "") -> None:
        self.write_progress(text)

    def write_info(self, text: str) -> None:
        self.write_progress(text)

    def write_success(self, text: str) -> None:
        self.write_progress(text)

    def write_warning(self, text: str) -> None:
        self.write_progress(text)

    def write_error(self, text: str) -> None:
        self.write_progress(f"[error] {text}")

    def write_reasoning(self, text: str) -> None:
        chunk = str(text)
        self._thinking_acc += chunk
        if self._expand_thinking:
            self._push_async("reasoning", chunk)

    def stream_token(self, token: str) -> None:
        self._push_async("token", token)

    def _push_async(self, kind: str, text: str) -> None:
        """Submit a streaming notification from sync TUI callbacks (agent_v2
        calls the TUI synchronously).

        Coalesced path: the buffer append happens SYNCHRONOUSLY (push_sync)
        so the coalescer's pending batch is ordered exactly against plain
        emits (e.g. write_tool_call) that enqueue immediately after; only a
        threshold-triggered flush is scheduled as a tracked task.  The
        direct-emit path (switch 0) keeps the legacy behaviour.
        """
        coalescer = self._coalescer
        if coalescer is not None:
            if coalescer.push_sync(kind, str(text)):
                task = asyncio.get_running_loop().create_task(coalescer.flush())
                self._push_tasks.add(task)
                task.add_done_callback(self._on_push_done)
            return
        self._emit_direct(kind, str(text))

    def _on_push_done(self, task: asyncio.Task[Any]) -> None:
        self._push_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            self._push_failures.append(exc)

    def write_plan(self, steps: Any) -> None:
        self.write_progress(f"plan: {steps}")

    def write_step(self, num: int, total: int, desc: str) -> None:
        self.write_progress(f"step {num}/{total}: {desc}")

    def _flush_pending_stream(self) -> None:
        """Ordering barrier: submit any buffered stream content to the FIFO
        writer BEFORE a plain emit, so a tool notification that follows a
        token can never overtake it (sync sink only; no-op otherwise)."""
        coalescer = self._coalescer
        if coalescer is not None:
            coalescer.flush_submit_sync()

    def write_tool_call(self, name: str, args: Any, call_id: str | None = None) -> str:
        self._flush_pending_stream()
        resolved_id = str(call_id or uuid.uuid4().hex)
        arguments = args if isinstance(args, dict) else {"raw": str(args)}
        self._emit(
            ToolBegin(
                session_id=self.session_id,
                call_id=resolved_id,
                tool_name=str(name),
                arguments=arguments,
            )
        )
        return resolved_id

    def write_tool_result(
        self,
        result: Any,
        *,
        call_id: str | None = None,
        status: str = "success",
    ) -> None:
        self._flush_pending_stream()
        self._emit(
            ToolEnd(
                session_id=self.session_id,
                call_id=str(call_id or uuid.uuid4().hex),
                ok=status == "success",
                summary=str(result),
                status=status,
            )
        )

    def set_session_list_fn(self, fn: Any) -> None:
        return None

    def set_new_session_fn(self, fn: Any) -> None:
        return None