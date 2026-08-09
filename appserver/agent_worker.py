"""Isolated AgentV2 worker subprocess (T1): killable bootstrap + prompt execution."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from .bootstrap import bootstrap_agent
from .emitter import model_to_notification
from .jsonrpc import write_message
from .runtime import bind_prompt_context, install_tui_context_hook, get_bound_tui, reset_prompt_context
from .tui import ProtocolTui

try:
    from ..core.safety.approval import ApprovalBroker, ApprovalDecision, ApprovalRequest
    from ..core.safety.approval import set_approval_broker
    from ..core.session import Session
except ImportError:
    from core.safety.approval import ApprovalBroker, ApprovalDecision, ApprovalRequest
    from core.safety.approval import set_approval_broker
    from core.session import Session

_logger = logging.getLogger(__name__)


class _PipeApproval(ApprovalBroker):
    """Forward approval requests to the parent appserver over worker stdout."""

    def __init__(self, send_request: Callable[[str, dict[str, Any]], Any]) -> None:
        super().__init__()
        self._send_request = send_request

    async def _ask(self, request: ApprovalRequest) -> ApprovalDecision:
        try:
            from .runtime import get_bound_session_id
        except ImportError:
            from appserver.runtime import get_bound_session_id

        session_id = get_bound_session_id()
        try:
            payload = await asyncio.wait_for(
                self._send_request(
                    "approval/request",
                    {
                        "session_id": session_id,
                        "request_id": request.approval_id,
                        "risk_level": request.risk.name,
                        "action": request.tool_name,
                        "details": {"args": request.args_summary},
                    },
                ),
                timeout=120.0,
            )
        except asyncio.TimeoutError:
            return ApprovalDecision.REJECTED
        decision_name = str(payload.get("decision", "rejected"))
        try:
            return ApprovalDecision(decision_name)
        except ValueError:
            return ApprovalDecision.REJECTED


class AgentWorker:
    def __init__(self) -> None:
        install_tui_context_hook()
        self._agent: Any | None = None
        self._session_id = "worker"
        self._workspace_root = Path.cwd()
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 1
        self._approval = _PipeApproval(self._send_parent_request)
        self._thinking_expanded = False
        self._active_tui: Any | None = None
        self._pending_writes: set[asyncio.Task[Any]] = set()
        self._write_failures: list[BaseException] = []
        self._run_task: asyncio.Task[Any] | None = None
        #: Request ids that already got a terminal response, so an early-cancel
        #: path never double-replies to the parent.
        self._answered_request_ids: set[int] = set()

    def _mark_answered(self, request_id: int) -> None:
        self._answered_request_ids.add(request_id)
        # Bound the dedup set: it only needs to cover in-flight prompts plus a
        # short trailing window, so it cannot grow without bound on a long-lived
        # worker.
        if len(self._answered_request_ids) > 64:
            # Discard the oldest half (insertion order is preserved).
            for old in list(self._answered_request_ids)[:32]:
                self._answered_request_ids.discard(old)

    async def _write_interrupted_response(self, request_id: int) -> None:
        """Send the 'interrupted' failed result for a cancelled prompt request.

        A notification flush failure must not prevent the terminal response:
        it is logged, then the response is still written best-effort (shielded)
        so the parent's pending request resolves instead of hanging.
        """
        try:
            await self._flush_pending_writes()
        except BaseException as exc:
            _logger.error("flush failed before interrupted response: %r", exc)
        await asyncio.shield(
            write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "status": "failed",
                        "text": "",
                        "thinking": "",
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "detail": "interrupted",
                    },
                }
            )
        )
        self._mark_answered(request_id)

    def _on_write_done(self, task: asyncio.Task[Any]) -> None:
        """Record a notification-write failure persistently.

        Persisting the exception in ``_write_failures`` survives the set-removal
        in the done callback, so a write that finished before ``_flush`` ran is
        still observable.
        """
        self._pending_writes.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            self._write_failures.append(exc)

    def _schedule_write(self, message: dict[str, Any]) -> None:
        """Queue stdout write from sync emit callbacks (T3: no sync I/O on loop)."""
        task = asyncio.get_running_loop().create_task(write_message(message))
        self._pending_writes.add(task)
        task.add_done_callback(self._on_write_done)

    async def _flush_pending_writes(self) -> None:
        """Wait for all scheduled notifications to hit stdout before a result.

        Write failures are surfaced instead of silently swallowed: a lost
        notification breaks event ordering/observability, and a failing stdout
        means the parent is unreachable, so the caller should stop rather than
        keep running RPCs that can never be answered.
        """
        if self._pending_writes:
            await asyncio.gather(
                *list(self._pending_writes), return_exceptions=True
            )
        failures = self._write_failures
        self._write_failures = []
        for exc in failures:
            _logger.error("notification write failed: %r", exc)
            raise RuntimeError("worker stdout write failed") from exc

    async def _send_parent_request(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[request_id] = future
        try:
            await write_message(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            )
            return await future
        finally:
            # Never leave a parent-response Future dangling: resolve it on any
            # path (response received, exception, timeout, cancellation).
            self._pending.pop(request_id, None)
            if not future.done():
                future.cancel()

    def _fail_all_parent_pending(self, exc: BaseException) -> None:
        """Fail every outstanding parent-request Future on shutdown/EOF."""
        pending = list(self._pending.items())
        self._pending.clear()
        for _request_id, future in pending:
            if not future.done():
                future.set_exception(exc)

    def _resolve_parent_response(self, message: dict[str, Any]) -> bool:
        request_id = message.get("id")
        if not isinstance(request_id, int):
            return False
        future = self._pending.pop(request_id, None)
        if future is None or future.done():
            return False
        if "error" in message:
            error = message.get("error")
            if isinstance(error, dict):
                detail = str(error.get("message", "parent request failed"))
            else:
                detail = str(error or "parent request failed")
            future.set_exception(RuntimeError(detail))
            return True
        result = message.get("result")
        if not isinstance(result, dict):
            result = {}
        future.set_result(result)
        return True

    async def _handle_bootstrap(self, params: dict[str, Any], request_id: int) -> None:
        stub = bool(params.get("stub", False))
        workspace = Path(str(params.get("workspace_root", ".")))
        self._workspace_root = workspace.resolve()
        self._session_id = str(params.get("session_id", "worker"))
        set_approval_broker(self._approval)
        self._agent = await asyncio.to_thread(
            bootstrap_agent,
            stub=stub,
            workspace_root=self._workspace_root,
        )
        await self._flush_pending_writes()
        await write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"ok": True, "workspace_root": str(self._workspace_root)},
            }
        )

    async def _handle_prompt(self, params: dict[str, Any], request_id: int) -> None:
        if self._agent is None:
            await write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32002, "message": "bootstrap first"},
                }
            )
            return
        text = str(params.get("text", ""))
        run_id = str(params.get("run_id") or uuid.uuid4().hex)
        session_id = str(params.get("session_id", self._session_id))

        def emit(notification: BaseModel) -> None:
            self._schedule_write(model_to_notification(notification))

        tui = ProtocolTui(session_id, emit)
        expanded = bool(params.get("thinking_expanded", self._thinking_expanded))
        self._thinking_expanded = expanded
        tui.set_thinking_expanded(expanded)
        tokens = bind_prompt_context(session_id, tui)
        self._active_tui = tui
        session = Session(
            session_id=session_id,
            workspace_root=self._workspace_root,
            emit=emit,
        )
        try:
            result = await session.prompt(
                self._agent, text, mode=str(params.get("mode", "build")), run_id=run_id
            )
        except asyncio.CancelledError:
            # Interrupt RPC cancelled this prompt task (C1): report the
            # cancellation to the host so the pending request resolves instead
            # of hanging until timeout.  Flush queued notifications first so
            # the failed result never overtakes already-emitted stream events.
            # The response write is shielded so an interrupt in the write
            # window cannot leave the parent hanging.
            await self._write_interrupted_response(request_id)
            raise
        except Exception as exc:
            await asyncio.shield(
                write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32000, "message": str(exc)},
                    }
                )
            )
            self._mark_answered(request_id)
            return
        finally:
            reset_prompt_context(tokens)
            self._active_tui = None

        # Ensure notifications (e.g. reasoning_snapshot) reach stdout before
        # the result, so the client never observes the result arrive first.
        # The terminal response write is shielded so an interrupt arriving in
        # the write window cannot cancel it mid-flight; we mark answered only
        # after it has been handed off to the transport.
        await self._flush_pending_writes()
        await asyncio.shield(
            write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "run_id": run_id,
                        "status": result.status,
                        "text": result.answer,
                        "thinking": result.thinking,
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                    },
                }
            )
        )
        self._mark_answered(request_id)

    async def _handle_interrupt(self, request_id: int) -> None:
        """Cancel the running prompt task (C1: run_task.cancel()).

        The interrupt RPC handler runs in its own dispatch task, so cancelling
        ``self._run_task`` (the task awaiting ``session.prompt``) is safe — it
        does not cancel the interrupt handler itself.
        """
        cancelled = False
        run_task = self._run_task
        if run_task is not None and not run_task.done():
            # We cancelled a running prompt task: report the cancel intent.
            # Even if the prompt's own cancellation cleanup (flush/write) fails
            # and replaces the CancelledError with a write exception, the task
            # was genuinely interrupted — so report cancelled, not "not
            # cancelled".  (A task that already finished before the cancel
            # never enters this branch.)
            run_task.cancel()
            with contextlib.suppress(BaseException):
                await run_task
            cancelled = True
        elif self._agent is not None:
            session = Session(
                session_id=self._session_id,
                workspace_root=self._workspace_root,
                emit=lambda _n: None,
            )
            cancelled = session.interrupt(self._agent)
        await write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"cancelled": cancelled},
            }
        )

    async def _handle_set_thinking_expanded(
        self, params: dict[str, Any], request_id: int
    ) -> None:
        expanded = bool(params.get("expanded", False))
        self._thinking_expanded = expanded
        tui = self._active_tui or get_bound_tui()
        if tui is not None and hasattr(tui, "set_thinking_expanded"):
            tui.set_thinking_expanded(expanded)
        await write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"ok": True, "expanded": expanded},
            }
        )

    async def _dispatch(self, message: dict[str, Any]) -> None:
        if "id" in message and ("result" in message or "error" in message):
            if self._resolve_parent_response(message):
                return
        if message.get("method") is None:
            return
        request_id = message.get("id")
        if not isinstance(request_id, int):
            # A request without a valid integer id cannot be answered; treat it
            # as a notification and drop it so callers do not hang waiting.
            return
        params = message.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        method = str(message.get("method", ""))
        if method == "bootstrap":
            await self._handle_bootstrap(params, int(request_id))
        elif method == "prompt":
            await self._handle_prompt(params, int(request_id))
        elif method == "interrupt":
            await self._handle_interrupt(int(request_id))
        elif method == "thinking/set_expanded":
            await self._handle_set_thinking_expanded(params, int(request_id))
        elif method == "shutdown":
            await write_message(
                {"jsonrpc": "2.0", "id": request_id, "result": {"ok": True}}
            )
            raise SystemExit(0)
        else:
            await write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"unknown method: {method}"},
                }
            )

    async def _dispatch_safe(self, message: dict[str, Any]) -> None:
        try:
            await self._dispatch(message)
        except SystemExit:
            raise
        except asyncio.CancelledError:
            # If the prompt task was cancelled *before* its own handler could
            # send the interrupted response (e.g. interrupt arrived before the
            # task first ran), answer here so the parent's pending request does
            # not hang until timeout.  Idempotent via _answered_request_ids
            # (marked only after the response write succeeds, inside
            # _write_interrupted_response).
            request_id = message.get("id")
            if (
                message.get("method") == "prompt"
                and isinstance(request_id, int)
                and request_id not in self._answered_request_ids
            ):
                # The task is in a cancelled state, so a bare await here would
                # re-raise CancelledError immediately; shield the write.
                await asyncio.shield(
                    self._write_interrupted_response(request_id)
                )
            raise
        except Exception as exc:
            _logger.exception("worker dispatch failed for %s", message)
            # Reply with a JSON-RPC error so the parent's pending request does
            # not hang until timeout.
            request_id = message.get("id")
            if isinstance(request_id, int) and not (
                "result" in message or "error" in message
            ):
                await write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32000, "message": str(exc)},
                    }
                )

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        pending: set[asyncio.Task[Any]] = set()
        try:
            while True:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                if "id" in message and ("result" in message or "error" in message):
                    if self._resolve_parent_response(message):
                        continue
                if message.get("method") == "shutdown":
                    await write_message(
                        {"jsonrpc": "2.0", "id": message.get("id"), "result": {"ok": True}}
                    )
                    break
                if message.get("method") == "prompt":
                    self._run_task = loop.create_task(self._dispatch_safe(message))
                    task = self._run_task

                    def _clear_run(
                        _t: asyncio.Task[Any], _rid: int = int(message.get("id"))
                    ) -> None:
                        if self._run_task is _t:
                            self._run_task = None
                        if (
                            _t.cancelled()
                            and _rid not in self._answered_request_ids
                        ):
                            # The prompt task was cancelled before it could
                            # answer (e.g. interrupt before first step): send
                            # the interrupted result from a fresh task so the
                            # parent's pending request does not hang.  Track it
                            # in _pending_writes so shutdown waits for it.  The
                            # answered marker is set inside the write.
                            reply = loop.create_task(
                                self._write_interrupted_response(_rid)
                            )
                            self._pending_writes.add(reply)
                            reply.add_done_callback(self._on_write_done)

                    task.add_done_callback(_clear_run)
                else:
                    task = loop.create_task(self._dispatch_safe(message))
                pending.add(task)
                task.add_done_callback(pending.discard)
        except Exception:
            raise
        finally:
            for task in list(pending):
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            # Wind down scheduled notification writes so they do not race the
            # process exit or the shutdown response, surfacing any failures.
            # Cancel them with a bounded wait so a blocked stdout to_thread can
            # never drag the shutdown out indefinitely.
            for task in list(self._pending_writes):
                task.cancel()
            if self._pending_writes:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        asyncio.gather(
                            *list(self._pending_writes), return_exceptions=True
                        ),
                        timeout=2.0,
                    )
            unfinished = len(self._pending_writes)
            if unfinished:
                _logger.warning(
                    "worker shutdown: %d notification write task(s) did not "
                    "finish within the bounded wait",
                    unfinished,
                )
            for exc in self._write_failures:
                _logger.error("notification write failed during shutdown: %r", exc)
            # Worker is going down: fail any outstanding parent-request
            # Futures (e.g. an approval awaiting a parent response) instead of
            # leaving them pending forever.
            self._fail_all_parent_pending(RuntimeError("worker shutdown"))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    asyncio.run(AgentWorker().run())


if __name__ == "__main__":
    main()
