"""Serial, cancellable lifecycle for operations sharing one agent instance."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import TypeVar


T = TypeVar("T")


class SessionSlots:
    """Session-level concurrency slots (PHASE-C C4 §4.4).

    - Global: one ``asyncio.Semaphore(max_concurrent)`` caps concurrent
      sessions process-wide; ``max_concurrent=1`` reproduces the legacy
      global-serial behaviour.
    - Session level: one ``asyncio.Semaphore(1)`` per session id guarantees
      strict serial execution inside a session.
    - Sessions are created on first acquire; callers release a finished
      session with :meth:`release_session` so the dictionary cannot grow
      unboundedly.

    ``acquire`` waits for a slot (used by ``/chat`` / ``/command`` / task
    services, matching the legacy queued lifecycle).  ``try_acquire`` never
    queues for a slot and is used by ``/chat/stream`` so a busy client keeps
    receiving the legacy busy-rejection message instead of a hanging stream
    (its only possible wait is the brief synchronous critical section inside
    ``_lock``).
    """

    def __init__(self, max_concurrent: int) -> None:
        self.max_concurrent = max(1, int(max_concurrent))
        self._global = asyncio.Semaphore(self.max_concurrent)
        self._per_session: dict[str, asyncio.Semaphore] = {}
        self._active: dict[str, int] = {}  # per-session registered count
        self._lock = asyncio.Lock()        # guards _per_session / _active

    async def acquire(self, session_id: str) -> None:
        """Wait for the global quota and the per-session slot (serial).

        Registration happens inside ``_lock`` BEFORE waiting on the session
        semaphore, so ``release_session`` can never delete the semaphore out
        from under a task that already holds or is about to take it: the
        ``_active`` counter is the single authority for "session occupied",
        and it is incremented atomically with the slot lookup.
        """
        await self._global.acquire()          # global quota: N=1 == legacy
        session_registered = False
        try:
            async with self._lock:
                sem = self._per_session.get(session_id)
                if sem is None:
                    sem = asyncio.Semaphore(1)
                    self._per_session[session_id] = sem
                self._active[session_id] = self._active.get(session_id, 0) + 1
                session_registered = True
            await sem.acquire()               # serial inside a session
        except asyncio.CancelledError:
            if session_registered:
                async with self._lock:
                    n = self._active.get(session_id, 0)
                    if n > 0:
                        self._active[session_id] = n - 1
            self._global.release()            # return the global slot
            raise

    async def try_acquire(self, session_id: str) -> bool:
        """Non-blocking admission for ``/chat/stream``: False when the global
        cap or the session slot is already taken.

        Never queues for a slot.  The only possible wait is the brief
        critical section inside ``_lock`` (synchronous bookkeeping), which
        never waits for a slot to free.  Registration, the occupancy probe
        and the semaphore lookup happen atomically under ``_lock``, so this
        shares the exact session authority with :meth:`acquire` and
        ``release_session`` cannot delete the slot mid-admission.
        """
        if self._global.locked():
            return False
        await self._global.acquire()
        session_registered = False
        try:
            async with self._lock:
                sem = self._per_session.get(session_id)
                if sem is None:
                    sem = asyncio.Semaphore(1)
                    self._per_session[session_id] = sem
                if self._active.get(session_id, 0) > 0:
                    self._global.release()
                    return False
                if sem.locked():              # defence in depth
                    self._global.release()
                    return False
                self._active[session_id] = 1
                session_registered = True
            await sem.acquire()               # value > 0: no suspension
            return True
        except asyncio.CancelledError:
            if session_registered:
                async with self._lock:
                    n = self._active.get(session_id, 0)
                    if n > 0:
                        self._active[session_id] = n - 1
            self._global.release()
            raise

    def release(self, session_id: str) -> None:
        """Release one acquired slot (paired with acquire/try_acquire)."""
        sem = self._per_session.get(session_id)
        if sem is not None:
            sem.release()
        n = self._active.get(session_id, 0)
        if n > 0:
            self._active[session_id] = n - 1
        self._global.release()

    async def release_session(self, session_id: str) -> None:
        """Drop a finished session's slot; idempotent.

        Refuses (RuntimeError) while the session still has registered tasks
        (running or waiting for its slot) so the global quota count and the
        per-session semaphore can never be torn down under an admission;
        callers must finish/cancel their tasks first.
        """
        async with self._lock:
            if self._active.get(session_id, 0) > 0:
                raise RuntimeError(
                    f"cannot release session {session_id}: "
                    f"{self._active[session_id]} in-flight task(s)"
                )
            self._per_session.pop(session_id, None)


class RunLifecycle:
    """Serialize runs per session and expose one thread-safe cancellation handle.

    C4: the gate is downgraded from a process-wide gate to a *per-session*
    gate — different sessions no longer queue behind each other, while the
    "one task per session" guarantee is preserved.  ``busy`` reflects any
    session with an active task; ``cancel()`` cancels all active tasks.

    ``asyncio.Lock`` instances can become tied to a TestClient/event loop when
    they contend.  The API is intentionally exercised from multiple loops, so
    this lifecycle uses process-local per-session gates with cancellable async
    polling.  The protected operation still runs on its caller's event loop.
    """

    def __init__(self, *, poll_interval: float = 0.01) -> None:
        self._gates: dict[str, threading.Lock] = {}
        self._gates_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._active: dict[str, dict] = {}  # session_id -> task/loop/kind
        self._poll_interval = poll_interval

    def _gate_for(self, session_id: str) -> threading.Lock:
        with self._gates_lock:
            gate = self._gates.get(session_id)
            if gate is None:
                gate = threading.Lock()
                self._gates[session_id] = gate
            return gate

    @property
    def busy(self) -> bool:
        with self._state_lock:
            return any(
                slot.get("task") is not None for slot in self._active.values()
            )

    @property
    def active_kind(self) -> str | None:
        with self._state_lock:
            for slot in self._active.values():
                if slot.get("task") is not None:
                    return slot.get("kind")
            return None

    async def run(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        session_id: str = "default",
        kind: str = "operation",
    ) -> T:
        """Wait for the session's shared slot, then run ``operation``.

        Different sessions run concurrently; the same session is strictly
        serial (one active task at a time).
        """
        gate = self._gate_for(session_id)
        while not gate.acquire(blocking=False):
            await asyncio.sleep(self._poll_interval)

        task = asyncio.current_task()
        loop = asyncio.get_running_loop()
        with self._state_lock:
            self._active[session_id] = {
                "task": task,
                "loop": loop,
                "kind": kind,
            }
        try:
            return await operation()
        finally:
            with self._state_lock:
                slot = self._active.get(session_id)
                if slot is not None and slot.get("task") is task:
                    self._active.pop(session_id, None)
            gate.release()

    def cancel(self) -> bool:
        """Cancel every active operation from this or another loop thread."""
        with self._state_lock:
            snapshot = list(self._active.values())
        cancelled = False
        for slot in snapshot:
            task = slot.get("task")
            loop = slot.get("loop")
            if task is None or task.done() or loop is None or loop.is_closed():
                continue

            def cancel_task(_task: asyncio.Task = task) -> None:
                if not _task.done():
                    _task.cancel()

            if loop.is_running():
                loop.call_soon_threadsafe(cancel_task)
                cancelled = True
        return cancelled

