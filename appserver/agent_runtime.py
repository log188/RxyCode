"""Phase E · E3 — AgentRuntime (registry, spawn/stop, quotas, budgets).

One AgentRuntime owns every agent of a session worker process: spawning
agents as ``AgentTask`` objects (E2) with per-agent quotas and budgets
(EB4), enforcing budget circuit breaking, and exposing the runtime
protocol (checkpoints, tool-process-tree cancellation) that AgentTask
uses.  See PHASE-E §4.3 / §5 E3.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

from .agent_task import AgentTask, LifecycleState
from .eventbus import BusEvent, EventBus

RunTarget = Callable[[str, object | None], Awaitable[Any]]


class BudgetExceededError(asyncio.CancelledError):
    """Raised by the budget breaker; callers must never retry.

    The CANCELLED state transition is performed by the runtime's breaker
    path (or an external ``stop``); this error is only the stop signal.
    """


class ParallelLimitError(RuntimeError):
    """Raised when a spawn would exceed ``RXYCODE_AGENT_PARALLEL``.

    The denied spawn publishes ``event/agent_denied`` before raising (E5).
    """


def agent_parallel_limit() -> int:
    """``RXYCODE_AGENT_PARALLEL`` (default 1 = legacy serial)."""
    raw = os.environ.get("RXYCODE_AGENT_PARALLEL", "1").strip()
    try:
        value = int(raw)
    except ValueError:
        return 1
    return value if value >= 1 else 1


# ---------------------------------------------------------------------------
# cache_namespace (DC8/F17): fail-closed validation and key building
# ---------------------------------------------------------------------------

_NS_OK_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_.-")


def validate_cache_namespace(ns: str | None) -> str | None:
    """Validate a cache namespace; raises ValueError on any illegal value.

    Rules (PHASE-E §4.3 / E3): None allowed; empty rejected; 1-64 ASCII
    bytes; lowercase ``[a-z0-9_.-]`` only; ``|`` and ``:`` forbidden;
    whitespace rejected; uppercase rejected (no auto-normalization).
    """
    if ns is None:
        return None
    if not isinstance(ns, str):
        raise ValueError(f"cache_namespace must be str or None, got {type(ns).__name__}")
    if ns == "":
        raise ValueError("cache_namespace must not be empty")
    if len(ns.encode("ascii", errors="strict")) > 64:
        raise ValueError("cache_namespace must be at most 64 ASCII bytes")
    if any(ch not in _NS_OK_CHARS for ch in ns):
        raise ValueError(
            "cache_namespace may only contain lowercase [a-z0-9_.-]"
            " (no |, :, whitespace, or uppercase)"
        )
    return ns


def build_cache_key(base: str, ns: str | None) -> str:
    """DC8 key building: ``f"{base}|{ns}"`` when ns is set, else base as-is.

    The base triple-key (``base_url|model|sha256(api_key)``) never contains
    ``|`` (F2 guarantee), so the separator cannot collide.
    """
    if ns is None:
        return base
    validate_cache_namespace(ns)
    return f"{base}|{ns}"


# ---------------------------------------------------------------------------
# AgentConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentConfig:
    """Per-agent configuration (PHASE-E §4.3).

    ``model`` is an opaque identifier (Phase A capability metadata) — the E
    layer must never read/compare/normalize it; ``None`` means the F-layer
    default (never injected here).  ``cache_namespace`` and ``mechanical``
    are 2026-08-12 additions with field-level serialization filtering so old
    byte-for-byte serialization is preserved.
    """

    agent_id: str
    model: str | None = None
    tools: tuple[str, ...] = ()
    quota: int = 3
    budget_tokens: int = 200_000
    memory_scope: Literal["session", "own"] = "own"
    cache_namespace: str | None = None
    mechanical: bool = False

    def to_dict(self) -> dict[str, Any]:
        """exclude_none-compatible serialization with field-level filtering.

        Legacy fields keep their original explicit-output behavior; only the
        2026-08-12 fields (cache_namespace/mechanical) are omitted when equal
        to their defaults (PHASE-E §4.3 golden-test contract).
        """
        result: dict[str, Any] = {
            "agent_id": self.agent_id,
            "model": self.model,
            "tools": self.tools,
            "quota": self.quota,
            "budget_tokens": self.budget_tokens,
            "memory_scope": self.memory_scope,
        }
        if self.cache_namespace is not None:
            result["cache_namespace"] = self.cache_namespace
        if self.mechanical:
            result["mechanical"] = True
        return result


# ---------------------------------------------------------------------------
# AgentRuntime
# ---------------------------------------------------------------------------


class AgentRuntime:
    """Owns the session's agents: spawn/stop, quotas, budgets, checkpoints.

    Quota model (EB4): per-agent ``asyncio.Semaphore(config.quota)`` plus a
    session-global tool-slot semaphore; acquisition order is always
    per-agent then global (deadlock-free) with rollback on the second step
    and double release in ``finally``.
    """

    def __init__(
        self,
        bus: EventBus,
        *,
        total_tool_slots: int = 16,
        budget_total: int | None = None,
        run_factory: Callable[[AgentConfig], RunTarget] | None = None,
        parallel_limit: int | None = None,
        cancel_storm_limit: int = 4,
    ) -> None:
        self._bus = bus
        self._sem_global = asyncio.Semaphore(max(1, int(total_tool_slots)))
        self._budget_total = budget_total
        self._run_factory = run_factory
        self._parallel_limit = (
            parallel_limit if parallel_limit is not None else agent_parallel_limit()
        )
        self._cancel_slots = asyncio.Semaphore(max(1, int(cancel_storm_limit)))
        self.agents: dict[str, AgentTask] = {}
        self.configs: dict[str, AgentConfig] = {}
        self.quotas: dict[str, asyncio.Semaphore] = {}
        self._token_usage: dict[str, int] = {}
        self._checkpoints: dict[str, object] = {}
        self._resolved_models: dict[str, str] = {}
        self._cancel_process_trees_calls = 0

    # -- lifecycle --------------------------------------------------------

    async def spawn(self, config: AgentConfig) -> AgentTask:
        """Create + start an agent; rejects duplicate ids and bad namespaces.

        E5: when the running-agent count already equals
        ``RXYCODE_AGENT_PARALLEL`` (default 1 = legacy serial), the spawn is
        denied: ``event/agent_denied`` is published and ParallelLimitError
        raised (the caller must not treat this as a runtime failure).
        """
        if config.agent_id in self.agents:
            raise AssertionError(f"agent {config.agent_id} already spawned")
        validate_cache_namespace(config.cache_namespace)  # raises ValueError
        if len(self.agents) >= self._parallel_limit:
            await self._bus.publish(
                BusEvent(
                    method="event/agent_denied",
                    session_id="",
                    agent_id=config.agent_id,
                    payload={"reason": "parallel_limit"},
                )
            )
            raise ParallelLimitError(
                f"agent {config.agent_id} denied: parallel limit "
                f"{self._parallel_limit} reached"
            )

        sem = asyncio.Semaphore(max(1, int(config.quota)))
        raw_target = (
            self._run_factory(config) if self._run_factory is not None else self._default_run
        )
        task = AgentTask(config.agent_id, self._bus, self, raw_target)
        self.agents[config.agent_id] = task
        self.configs[config.agent_id] = config
        self.quotas[config.agent_id] = sem
        task._run_target = self._make_guarded(config, raw_target)
        await task.spawn("")
        return task

    async def stop(self, agent_id: str, reason: str) -> None:
        """Cancel fan-out: interrupt (state -> CANCELLED, real cancel,
        tool-process cascade) and drop the registry entry.  Agents that
        already reached a terminal state are just removed (stopping is
        idempotent).

        E5: cancel storms are rate-limited — at most ``cancel_storm_limit``
        fan-outs run at the same moment, the rest queue (§7 security).
        """
        async with self._cancel_slots:
            task = self.agents.pop(agent_id, None)
            if task is None:
                return
            if task.state in (
                LifecycleState.DONE,
                LifecycleState.FAILED,
                LifecycleState.CANCELLED,
            ):
                return
            await task.interrupt(cascade_tools=True)

    # -- quotas -----------------------------------------------------------

    @asynccontextmanager
    async def acquire_tool_slot(self, agent_id: str) -> Iterator[None]:
        """Acquire per-agent then global tool slot; roll back on failure.

        Both semaphores are released in ``finally`` so cancellation/error
        paths never leak slots (EB4).
        """
        sem_agent = self.quotas[agent_id]
        await sem_agent.acquire()
        try:
            await self._sem_global.acquire()
        except BaseException:
            sem_agent.release()
            raise
        try:
            yield
        finally:
            self._sem_global.release()
            sem_agent.release()

    # -- budgets ----------------------------------------------------------

    def record_token_usage(self, agent_id: str, tokens: int) -> None:
        """Session-level cumulative usage (reasonix-style, never reset on
        agent switch)."""
        self._token_usage[agent_id] = self._token_usage.get(agent_id, 0) + int(tokens)

    def token_usage(self, agent_id: str) -> int:
        return self._token_usage.get(agent_id, 0)

    async def check_budget(self, agent_id: str, est: int = 1) -> None:
        """Circuit breaker check before an LLM/tool call (E3 §4.3).

        Uses the per-agent budget; ``budget_tokens=0`` selects the shared
        pool.  On breach: publish ``event/agent_budget_exceeded`` with the
        cumulative snapshot, then raise ``BudgetExceededError`` (caller must
        not retry).
        """
        cfg = self.configs[agent_id]
        budget = cfg.budget_tokens if cfg.budget_tokens else self._budget_total
        if budget is None:
            return
        used = self.token_usage(agent_id)
        if used + est <= budget:
            return
        await self._bus.publish(
            BusEvent(
                method="event/agent_budget_exceeded",
                session_id="",
                agent_id=agent_id,
                payload={"tokens_used": used, "budget_used": used},
            )
        )
        raise BudgetExceededError(
            f"agent {agent_id} budget exceeded: {used}+{est} > {budget}"
        )

    # -- model metadata ---------------------------------------------------

    def set_resolved_model(self, agent_id: str, model: str) -> None:
        """F12/F17 write point for the resolved-model read-only metadata."""
        self._resolved_models[agent_id] = model

    def resolved_model(self, agent_id: str) -> MappingProxyType[str, str] | None:
        """Read-only resolved-model metadata (never writable by consumers)."""
        model = self._resolved_models.get(agent_id)
        if model is None:
            return None
        return MappingProxyType({"model": model})

    # -- runtime protocol used by AgentTask (E2) --------------------------

    async def save_checkpoint(self, agent_id: str) -> object | None:
        marker = {"agent_id": agent_id, "saved_at": time.time()}
        self._checkpoints[agent_id] = marker
        return marker

    async def load_checkpoint(self, agent_id: str) -> object | None:
        return self._checkpoints.get(agent_id)

    async def cancel_process_trees(self, agent_id: str) -> None:
        """C7 process-tree cancellation hook (E2 interrupt cascade)."""
        self._cancel_process_trees_calls += 1

    # -- internals --------------------------------------------------------

    async def _default_run(self, task_str: str, checkpoint: object | None = None) -> Any:
        return "ok"

    def _make_guarded(self, config: AgentConfig, target: RunTarget) -> RunTarget:
        async def guarded(task_str: str, checkpoint: object | None = None) -> Any:
            task = self.agents.get(config.agent_id)
            try:
                try:
                    return await target(task_str, checkpoint=checkpoint)
                except TypeError:
                    return await target(task_str)
            except BudgetExceededError:
                # breaker path: the CANCELLED transition happens here (the
                # external stop() is the other, fully equivalent, route)
                if task is not None:
                    await task._set_state(LifecycleState.CANCELLED)
                    await self._bus.publish(
                        BusEvent(
                            method="event/agent_cancelled",
                            session_id="",
                            agent_id=config.agent_id,
                            payload={},
                        )
                    )
                raise

        return guarded
