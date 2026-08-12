"""Persistent task queue with synchronous and native async execution."""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import threading
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config.settings import get_data_dir
from .atomic_file import atomic_write_text


def _queue_path() -> Path:
    path = get_data_dir() / "queue.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


#: C6: the process's one shared event loop, registered by the API lifespan
#: (and appserver main).  Synchronous callers submit coroutines to it instead
#: of creating a fresh loop per task.
_shared_loop: asyncio.AbstractEventLoop | None = None
_shared_loop_lock = threading.Lock()

#: C6: process-wide dedicated queue loop, created once on first use and run
#: forever on a daemon thread.  Used when no shared loop is registered
#: (standalone CLI) so even that path never builds a fresh loop per task.
_fallback_loop: asyncio.AbstractEventLoop | None = None
_fallback_thread: threading.Thread | None = None
_fallback_lock = threading.Lock()
_fallback_ready = threading.Event()

#: Timeouts for bringing the process-wide queue loop up (kept as module
#: constants so tests can shorten them).
_FALLBACK_READY_TIMEOUT_S = 5.0
_FALLBACK_JOIN_TIMEOUT_S = 2.0


def register_shared_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """Register (or clear) the process-wide shared event loop (C6).

    Called by the API lifespan with its running loop; pass ``None`` on
    shutdown.  Idempotent and thread-safe.  With nested/overlapping
    lifespans the most recent registration wins; a lifespan clears the
    registration only when it still owns it (see api_server shutdown).
    """
    global _shared_loop
    with _shared_loop_lock:
        _shared_loop = loop


def get_shared_loop() -> asyncio.AbstractEventLoop | None:
    """Return the registered shared loop while it is running, else None.

    A closed/stopped loop (e.g. a lifespan that ended) is treated as absent
    so callers submit to the process-wide queue loop instead of a dead loop.
    """
    with _shared_loop_lock:
        loop = _shared_loop
    if loop is not None and loop.is_running():
        return loop
    return None


def _get_fallback_loop() -> asyncio.AbstractEventLoop:
    """Return the process-wide queue loop, creating it once if needed.

    The loop runs forever on a daemon thread; repeated calls reuse the same
    loop, so no per-task event loop is ever created.  A crashed/stopped loop
    is replaced lazily.  The creation is race-free: the ready event is set
    from inside ``run_forever``'s first iteration, so a concurrent caller
    waits for the loop to actually be schedulable instead of building a
    second loop.
    """
    global _fallback_loop, _fallback_thread
    with _fallback_lock:
        if _fallback_loop is None or not _fallback_loop.is_running():
            old_loop = _fallback_loop
            if old_loop is not None and not old_loop.is_running():
                old_loop.close()   # never leak a stopped loop
            loop = asyncio.new_event_loop()
            ready = _fallback_ready
            ready.clear()

            def _run() -> None:
                loop.call_soon_threadsafe(ready.set)
                loop.run_forever()

            thread = threading.Thread(
                target=_run,
                daemon=True,
                name="rxycode-queue-loop",
            )
            try:
                thread.start()
            except BaseException:
                loop.close()       # never leak a loop whose thread failed
                _fallback_loop = None
                _fallback_thread = None
                raise
            ready.wait(timeout=_FALLBACK_READY_TIMEOUT_S)
            if not ready.is_set() or not thread.is_alive():
                # The thread failed to bring the loop up: ask it to exit,
                # join it, and only then close the loop and clear the cache
                # so a broken loop is never cached and no close-vs-running
                # race exists.  If the thread is STILL alive after the join
                # timeout, the loop is left open (closing a loop whose
                # thread is running would race); this leaves a residual
                # daemon thread and an open loop object that are released
                # only when the process exits — an accepted, documented
                # boundary of this extremely rare failure path.  Either way
                # the cache is cleared so the next call builds a fresh loop,
                # and run_task records the task as failed.
                loop.call_soon_threadsafe(loop.stop)
                thread.join(timeout=_FALLBACK_JOIN_TIMEOUT_S)
                if not thread.is_alive():
                    loop.close()
                _fallback_loop = None
                _fallback_thread = None
                raise RuntimeError(
                    "failed to start the queue event loop thread"
                )
            _fallback_loop = loop
            _fallback_thread = thread
        return _fallback_loop


def _resolve_execution_loop() -> asyncio.AbstractEventLoop:
    """C6: choose the loop for a synchronous queue submission.

    Prefer the registered shared loop; if none is registered, or the shared
    loop stops between the check and the submit (TOCTOU), fall back to the
    process-wide queue loop.  ``asyncio.run_coroutine_threadsafe`` raises
    ``RuntimeError`` when the target loop is closed, which is how the race
    is caught.
    """
    loop = get_shared_loop()
    if loop is None:
        return _get_fallback_loop()
    return loop


class QueueManager:
    """Persistent JSON-backed queue whose state transitions are atomic."""

    def __init__(self, storage_path: Path | None = None):
        self._path = Path(storage_path) if storage_path else _queue_path()
        self._lock = threading.RLock()

    def _load_unlocked(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"tasks": [], "next_id": 1}

    def _save_unlocked(self, data: dict) -> None:
        atomic_write_text(
            self._path,
            json.dumps(data, ensure_ascii=False, indent=2),
        )

    def _claim(self, task_id: int) -> dict | None:
        with self._lock:
            data = self._load_unlocked()
            for task in data.get("tasks", []):
                if task.get("id") != task_id or task.get("status") != "pending":
                    continue
                task["status"] = "running"
                task["started"] = datetime.now().isoformat()
                task["finished"] = ""
                task["result"] = None
                self._save_unlocked(data)
                return dict(task)
        return None

    def _complete(self, task_id: int, status: str, result: str) -> dict | None:
        with self._lock:
            data = self._load_unlocked()
            for task in data.get("tasks", []):
                if task.get("id") != task_id:
                    continue
                task["status"] = status
                task["result"] = result
                task["finished"] = datetime.now().isoformat()
                self._save_unlocked(data)
                return dict(task)
        return None

    @staticmethod
    def _terminal_status(result: str) -> str:
        from ..log.log_helpers import classify_agent_result

        status, _ = classify_agent_result(result)
        return status

    def add_task(self, prompt: str) -> dict:
        """Add a task to the queue and return its persisted record."""
        with self._lock:
            data = self._load_unlocked()
            task_id = data.get("next_id", 1)
            task = {
                "id": task_id,
                "prompt": prompt,
                "status": "pending",
                "created": datetime.now().isoformat(),
                "started": "",
                "finished": "",
                "result": None,
            }
            data.setdefault("tasks", []).append(task)
            data["next_id"] = task_id + 1
            self._save_unlocked(data)
            return dict(task)

    async def run_task_async(
        self,
        task_id: int,
        runner: Callable[[str], Awaitable[object]],
    ) -> dict | None:
        """Claim and execute one task without moving work to another loop."""
        claimed = self._claim(task_id)
        if claimed is None:
            return None
        try:
            result = str(await runner(claimed["prompt"]))
        except asyncio.CancelledError:
            self._complete(task_id, "cancelled", "[cancelled: queue task]")
            raise
        except Exception as exc:
            return self._complete(task_id, "failed", f"Error: {exc}")
        return self._complete(task_id, self._terminal_status(result), result)

    async def run_all_async(
        self,
        runner: Callable[[str], Awaitable[object]],
    ) -> list[dict]:
        """Run every task that was pending when this call began."""
        pending_ids = [
            task["id"]
            for task in self.list_tasks()
            if task.get("status") == "pending"
        ]
        results = []
        for task_id in pending_ids:
            result = await self.run_task_async(task_id, runner)
            if result is not None:
                results.append(result)
        return results

    def run_task(self, task_id: int, agent) -> Optional[str]:
        """Synchronous compatibility wrapper used by the CLI.

        C6: the agent run is submitted to the process's shared loop (or, in
        a standalone CLI without a registered loop, to the process-wide
        queue loop) via ``run_coroutine_threadsafe`` — no event loop is
        created per task.  ``.result()`` blocks the calling thread until the
        run finishes and propagates the run's exception, like the pre-C6
        ``asyncio.run`` behaviour (a cancelled run surfaces as
        ``CancelledError``, which this wrapper does not swallow).

        Failure handling: a submit against a loop that closed between the
        check and the submit (TOCTOU) closes the unused coroutine and
        retries on the process-wide queue loop.  If the target loop stops
        while the run is in flight (lifespan-shutdown race), the wait polls
        the loop and aborts with a clear error instead of hanging forever.
        """
        claimed = self._claim(task_id)
        if claimed is None:
            return None
        try:
            future, loop = self._submit_to_loop(agent, claimed["prompt"])
            result = str(self._wait_for_result(future, loop))
        except concurrent.futures.CancelledError:
            # A cancelled run surfaces as asyncio.CancelledError (matching
            # the pre-C6 asyncio.run behaviour) so it propagates as
            # BaseException instead of being recorded as a task failure.
            raise asyncio.CancelledError from None
        except Exception as exc:
            completed = self._complete(task_id, "failed", f"Error: {exc}")
        else:
            completed = self._complete(
                task_id, self._terminal_status(result), result
            )
        return completed.get("result") if completed else None

    @staticmethod
    def _submit_to_loop(
        agent, prompt: str
    ) -> tuple["asyncio.Future[object]", asyncio.AbstractEventLoop]:
        """Submit agent.run to the execution loop with TOCTOU recovery."""
        loop = _resolve_execution_loop()
        coro = agent.run(prompt, mode="build")
        try:
            return (
                asyncio.run_coroutine_threadsafe(coro, loop),
                loop,
            )
        except RuntimeError:
            # The resolved loop closed between the check and the submit:
            # close the unused coroutine explicitly (no "coroutine was never
            # awaited" warning) and retry on the process-wide queue loop.
            coro.close()
            loop = _get_fallback_loop()
            retry_coro = agent.run(prompt, mode="build")
            try:
                return (
                    asyncio.run_coroutine_threadsafe(retry_coro, loop),
                    loop,
                )
            except RuntimeError:
                retry_coro.close()
                raise

    @staticmethod
    def _wait_for_result(
        future: "asyncio.Future[object]", loop: asyncio.AbstractEventLoop
    ) -> object:
        """Block for the future; abort instead of hanging if the target
        event loop stops mid-run (lifespan-shutdown race).

        A transient ``is_running()`` false reading is tolerated: the loop
        must be observed stopped for three consecutive polls (>= ~30 ms)
        before the wait aborts, so a momentarily-paused loop is not
        misjudged.
        """
        stale_polls = 0
        while True:
            if future.done():
                return future.result()
            if not loop.is_running():
                stale_polls += 1
                if stale_polls >= 3:
                    future.cancel()
                    raise RuntimeError(
                        "event loop stopped during the queue task"
                    )
            else:
                stale_polls = 0
            time.sleep(0.01)

    def run_all(self, agent) -> list[dict]:
        """Synchronous compatibility wrapper used by the CLI."""
        pending_ids = [
            task["id"]
            for task in self.list_tasks()
            if task.get("status") == "pending"
        ]
        results = []
        for task_id in pending_ids:
            self.run_task(task_id, agent)
            task = next(
                (item for item in self.list_tasks() if item.get("id") == task_id),
                None,
            )
            if task is not None:
                results.append(
                    {
                        "id": task_id,
                        "status": task.get("status"),
                        "result": task.get("result"),
                    }
                )
        return results

    def list_tasks(self) -> list[dict]:
        with self._lock:
            return [dict(task) for task in self._load_unlocked().get("tasks", [])]

    def clear(self) -> None:
        with self._lock:
            self._save_unlocked({"tasks": [], "next_id": 1})

    def remove(self, task_id: int) -> bool:
        with self._lock:
            data = self._load_unlocked()
            tasks = data.get("tasks", [])
            remaining = [task for task in tasks if task.get("id") != task_id]
            if len(remaining) == len(tasks):
                return False
            data["tasks"] = remaining
            self._save_unlocked(data)
            return True
