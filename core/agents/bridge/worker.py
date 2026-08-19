"""Per-task bridge Worker: spawn, isolate, recycle. No resident pool."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from RxyCode.RxyCode1_1_0.core.agents.bridge.envelope import encode, truncate_summary
from RxyCode.RxyCode1_1_0.core.agents.bridge.stdio import StdioChannel
from RxyCode.RxyCode1_1_0.core.agents.budget import BudgetExceeded, BudgetGuard
from RxyCode.RxyCode1_1_0.protocol.agents import (
    BridgeAbort,
    BridgePlan,
    BridgeProgress,
    BridgeResult,
    BridgeToolCall,
    TaskDelegate,
)

_LOG = logging.getLogger(__name__)
_LIVE: set[int] = set()


def live_bridge_processes() -> int:
    return len(_LIVE)


class BridgeError(RuntimeError):
    """Bridge worker failed or was aborted."""


class BridgeWorker:
    """One external agent instance for one task. Recycled on any terminal state."""

    def __init__(
        self,
        *,
        worker_id: str,
        command: list[str] | None = None,
        channel: Any | None = None,
        workspace: Path,
        session_id: str,
        role: str = "bridge",
        budget: BudgetGuard | None = None,
        on_event: Callable[[Any], None] | None = None,
    ) -> None:
        if command is None and channel is None:
            raise ValueError("bridge worker needs a command or an injected channel")
        self.worker_id = worker_id
        self.session_id = session_id
        self.role = role
        self.cache_namespace = f"bridge:{session_id}:{worker_id}"
        self._command = list(command or [])
        self._injected = channel
        self._channel: Any | None = None
        self._budget = budget
        self._on_event = on_event or (lambda _e: None)
        self.worktree = workspace / "worktrees" / f"{worker_id}-{uuid.uuid4().hex[:8]}"
        self.worktree.mkdir(parents=True, exist_ok=True)
        self._try_git_worktree(workspace)
        self.recycled = False
        self.events: list[Any] = []

    def _try_git_worktree(self, workspace: Path) -> None:
        git_dir = workspace / ".git"
        if not git_dir.exists():
            return
        try:
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(self.worktree), "HEAD"],
                cwd=str(workspace),
                check=False,
                capture_output=True,
                timeout=10,
            )
        except Exception:
            _LOG.warning("git worktree add skipped", exc_info=True)

    def _open(self) -> Any:
        if self._channel is not None:
            return self._channel
        if self._injected is not None:
            self._channel = self._injected
            return self._channel
        channel = StdioChannel(self._command, cwd=self.worktree, env=os.environ.copy())
        if channel.pid:
            _LIVE.add(channel.pid)
        self._channel = channel
        return channel

    def delegate(self, request: TaskDelegate, *, poll: float = 0.05) -> BridgeResult:
        channel = self._open()
        if self._budget is not None:
            self._budget.add_delegation()
            if request.budget.tokens:
                # Fuse trips if this single hop already exceeds remaining budget.
                if getattr(self._budget, "_tokens_used", 0) > request.budget.tokens:
                    self.abort(request.task_id, reason="budget")
                    raise BudgetExceeded("task_delegate.budget tokens exceeded")
        channel.send(encode(request, rpc_id=1))
        deadline = time.monotonic() + max(0.05, float(request.budget.timeout_s))
        result: BridgeResult | None = None
        try:
            while time.monotonic() < deadline:
                if self._budget is not None:
                    self._budget.check()
                raw = channel.recv(timeout=poll)
                if raw is None:
                    if hasattr(channel, "is_alive") and not channel.is_alive():
                        break
                    continue
                if raw.get("method") is None and "result" in raw:
                    continue
                method = raw.get("method")
                params = raw.get("params") or {}
                if method == "progress":
                    event = BridgeProgress.model_validate(params)
                    self._emit(event)
                elif method == "tool_call":
                    self._emit(BridgeToolCall.model_validate(params))
                elif method == "plan":
                    self._emit(BridgePlan.model_validate(params))
                elif method == "result":
                    event = BridgeResult.model_validate(params)
                    event = event.model_copy(
                        update={"summary": truncate_summary(event.summary)}
                    )
                    if self._budget is not None and event.tokens_used:
                        self._budget.add_tokens(event.tokens_used)
                    result = event
                    self._emit(event)
                    break
            if result is None:
                self.abort(request.task_id, reason="timeout")
                raise BridgeError(f"worker {self.worker_id} timed out")
            return result
        finally:
            self.recycle()

    def abort(self, task_id: str, *, reason: str = "timeout") -> None:
        channel = self._channel
        if channel is None:
            return
        why = reason if reason in {"budget", "timeout", "user"} else "timeout"
        try:
            channel.send(
                encode(
                    BridgeAbort(task_id=task_id, reason=why, partial=True),
                    rpc_id=None,
                )
            )
        except Exception:
            _LOG.warning("abort send failed", exc_info=True)
        if hasattr(channel, "kill"):
            channel.kill()

    def recycle(self) -> None:
        if self.recycled:
            return
        self.recycled = True
        channel = self._channel
        pid = getattr(channel, "pid", None) if channel is not None else None
        if channel is not None:
            if hasattr(channel, "kill"):
                channel.kill()
            elif hasattr(channel, "close"):
                channel.close()
        if isinstance(pid, int):
            _LIVE.discard(pid)
        if self.worktree.exists():
            shutil.rmtree(self.worktree, ignore_errors=True)

    def _emit(self, event: Any) -> None:
        self.events.append(event)
        self._on_event(event)
