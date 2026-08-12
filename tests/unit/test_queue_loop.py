"""Phase C C6 contract tests: one shared event loop per process.

The queue's synchronous ``run_task`` used to create a fresh event loop per
task (``asyncio.run``).  C6 replaces that with the process's shared loop
(``run_coroutine_threadsafe``), registered by the API lifespan; without a
registered running loop the process-wide queue loop (created once, run
forever on a daemon thread, reused across tasks) is used, so no per-task
event loop is ever created.
"""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import MagicMock

import pytest

from RxyCode.RxyCode1_1_0.utils import queue as queue_mod
from RxyCode.RxyCode1_1_0.utils.queue import QueueManager


@pytest.fixture
def shared_loop_state(monkeypatch):
    """Point the module globals at fresh state and restore them after."""
    monkeypatch.setattr(queue_mod, "_shared_loop", None)
    monkeypatch.setattr(queue_mod, "_shared_loop_lock", threading.Lock())
    monkeypatch.setattr(queue_mod, "_fallback_loop", None)
    monkeypatch.setattr(queue_mod, "_fallback_thread", None)
    monkeypatch.setattr(queue_mod, "_fallback_ready", threading.Event())
    yield
    queue_mod._shared_loop = None


def _agent_with_loop_recorder():
    agent = MagicMock()
    recorded: list[asyncio.AbstractEventLoop] = []

    async def run(prompt: str, mode: str) -> str:
        recorded.append(asyncio.get_running_loop())
        return "ok"

    agent.run = run
    return agent, recorded


async def _run_task_in_thread(q, task_id, agent) -> dict:
    """Run the blocking q.run_task in a worker thread while keeping the
    shared event loop alive (the loop must be free to process the submitted
    coroutine, so we poll with await asyncio.sleep instead of join())."""
    holder: dict = {}

    def worker() -> None:
        try:
            holder["result"] = q.run_task(task_id, agent)
            holder["error"] = None
        except BaseException as exc:  # noqa: BLE001 — surface to the caller
            holder["result"] = None
            holder["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while thread.is_alive():
        if time.monotonic() > deadline:
            raise AssertionError("run_task did not return in time")
        await asyncio.sleep(0.01)
    return holder


# ── shared-loop registration ────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_and_get_shared_loop(shared_loop_state):
    loop = asyncio.get_running_loop()
    queue_mod.register_shared_loop(loop)
    assert queue_mod.get_shared_loop() is loop
    queue_mod.register_shared_loop(None)
    assert queue_mod.get_shared_loop() is None


@pytest.mark.asyncio
async def test_closed_shared_loop_is_ignored(shared_loop_state):
    closed = asyncio.new_event_loop()
    closed.close()
    queue_mod.register_shared_loop(closed)
    assert queue_mod.get_shared_loop() is None


# ── run_task uses the shared loop ───────────────────────────────────


@pytest.mark.asyncio
async def test_run_task_executes_on_the_shared_loop(tmp_path, shared_loop_state):
    shared = asyncio.get_running_loop()
    queue_mod.register_shared_loop(shared)
    q = QueueManager(storage_path=tmp_path / "queue.json")
    task = q.add_task("hello")
    agent, recorded = _agent_with_loop_recorder()

    holder = await _run_task_in_thread(q, task["id"], agent)

    assert holder["error"] is None
    assert holder["result"] == "ok"
    assert recorded == [shared], "agent.run must run on the shared loop"


@pytest.mark.asyncio
async def test_run_task_falls_back_to_queue_loop_without_shared_loop(
    tmp_path, shared_loop_state
):
    """Without a shared loop the task runs on the process-wide queue loop
    (a long-lived daemon loop), NOT on a fresh per-task loop."""
    main_loop = asyncio.get_running_loop()
    q = QueueManager(storage_path=tmp_path / "queue.json")
    task = q.add_task("hello")
    agent, recorded = _agent_with_loop_recorder()

    holder = await _run_task_in_thread(q, task["id"], agent)

    assert holder["error"] is None
    assert holder["result"] == "ok"
    assert len(recorded) == 1
    assert recorded[0] is not main_loop
    assert recorded[0].is_running(), "the queue loop must stay alive"
    # The queue loop must be reused, not rebuilt per task.
    loop_used = recorded[0]
    agent2, recorded2 = _agent_with_loop_recorder()
    task2 = q.add_task("again")
    holder2 = await _run_task_in_thread(q, task2["id"], agent2)
    assert holder2["error"] is None
    assert recorded2 == [loop_used], "no per-task loop may be created"


@pytest.mark.asyncio
async def test_run_task_falls_back_when_shared_loop_is_closed(
    tmp_path, shared_loop_state
):
    closed = asyncio.new_event_loop()
    closed.close()
    queue_mod.register_shared_loop(closed)
    q = QueueManager(storage_path=tmp_path / "queue.json")
    task = q.add_task("hello")
    agent, recorded = _agent_with_loop_recorder()

    holder = await _run_task_in_thread(q, task["id"], agent)

    assert holder["error"] is None
    assert holder["result"] == "ok"
    assert len(recorded) == 1
    assert recorded[0].is_running(), "queue loop is used and stays alive"


@pytest.mark.asyncio
async def test_run_task_cancellation_propagates(tmp_path, shared_loop_state):
    """A cancelled agent.run surfaces as CancelledError (BaseException) and
    is NOT swallowed by the wrapper - identical to the pre-C6 asyncio.run
    behaviour; the task stays claimed (running)."""
    shared = asyncio.get_running_loop()
    queue_mod.register_shared_loop(shared)
    q = QueueManager(storage_path=tmp_path / "queue.json")
    task = q.add_task("cancel-me")
    agent = MagicMock()

    async def run(prompt: str, mode: str) -> str:
        raise asyncio.CancelledError

    agent.run = run

    holder = await _run_task_in_thread(q, task["id"], agent)

    assert isinstance(holder["error"], asyncio.CancelledError)
    updated = next(t for t in q.list_tasks() if t["id"] == task["id"])
    assert updated["status"] == "running", "cancellation must not complete the task"


@pytest.mark.asyncio
async def test_submit_failure_closes_coroutine_and_retries(
    tmp_path, shared_loop_state, monkeypatch
):
    """When the first submit raises RuntimeError (loop closed mid-check), the
    unused coroutine is closed (no 'never awaited' warning) and the run is
    retried on the queue loop."""
    from RxyCode.RxyCode1_1_0.utils.queue import (
        _get_fallback_loop,
        _resolve_execution_loop,
    )

    closed = asyncio.new_event_loop()
    closed.close()
    original_resolve = _resolve_execution_loop
    monkeypatch.setattr(queue_mod, "_resolve_execution_loop", lambda: closed)
    q = QueueManager(storage_path=tmp_path / "queue.json")
    task = q.add_task("hello")
    agent, recorded = _agent_with_loop_recorder()

    holder = await _run_task_in_thread(q, task["id"], agent)

    assert holder["error"] is None
    assert holder["result"] == "ok"
    assert len(recorded) == 1
    assert recorded[0] is _get_fallback_loop()
    monkeypatch.setattr(queue_mod, "_resolve_execution_loop", original_resolve)


@pytest.mark.asyncio
async def test_concurrent_fallback_creation_yields_single_loop(
    tmp_path, shared_loop_state, monkeypatch
):
    """Concurrent first use of the fallback loop must not create duplicate
    loops/threads (the ready event waits for the loop to be schedulable)."""
    from RxyCode.RxyCode1_1_0.utils.queue import _get_fallback_loop

    monkeypatch.setattr(queue_mod, "_fallback_loop", None)
    monkeypatch.setattr(queue_mod, "_fallback_thread", None)
    results: dict = {}

    def worker(key: str) -> None:
        results[key] = _get_fallback_loop()

    threads = [
        threading.Thread(target=worker, args=(f"t{i}",), daemon=True)
        for i in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    loops = {results[f"t{i}"] for i in range(4)}
    assert len(loops) == 1, "all concurrent callers must share one loop"
    # The cached module state points at the same loop.
    assert queue_mod._fallback_loop is next(iter(loops))


@pytest.mark.asyncio
async def test_loop_stop_mid_run_aborts_instead_of_hanging(
    tmp_path, shared_loop_state
):
    """If the shared loop stops AFTER a successful submit (lifespan-shutdown
    race), the sync wrapper aborts with a clear error instead of blocking
    forever."""
    loop_b = asyncio.new_event_loop()
    thread_b = threading.Thread(target=loop_b.run_forever, daemon=True)
    thread_b.start()
    queue_mod.register_shared_loop(loop_b)
    q = QueueManager(storage_path=tmp_path / "queue.json")
    task = q.add_task("slow")
    agent = MagicMock()
    started = threading.Event()

    async def run(prompt: str, mode: str) -> str:
        started.set()
        await asyncio.sleep(5)
        return "late"

    agent.run = run
    holder: dict = {}

    def worker() -> None:
        try:
            holder["result"] = q.run_task(task["id"], agent)
            holder["error"] = None
        except BaseException as exc:  # noqa: BLE001
            holder["result"] = None
            holder["error"] = repr(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    # Deterministic: wait until the run has actually STARTED on loop_b, then
    # stop the loop mid-run (a plain sleep would race the worker's submit).
    deadline = time.monotonic() + 5
    while not started.is_set() and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert started.is_set(), "agent.run never started on the shared loop"
    loop_b.call_soon_threadsafe(loop_b.stop)   # stop the loop mid-run
    thread_b.join(timeout=5)

    deadline = time.monotonic() + 5
    while thread.is_alive() and time.monotonic() < deadline:
        await asyncio.sleep(0.02)
    assert not thread.is_alive(), "run_task must not hang on a stopped loop"
    assert "stopped during the queue task" in str(holder["result"])
    updated = next(t for t in q.list_tasks() if t["id"] == task["id"])
    assert updated["status"] == "failed"
    queue_mod.register_shared_loop(None)


@pytest.mark.asyncio
async def test_fallback_creation_failure_is_not_cached(
    tmp_path, shared_loop_state, monkeypatch
):
    """If the queue-loop thread fails to start, the failure surfaces (the
    task is recorded failed) and a broken loop is NOT cached."""
    import RxyCode.RxyCode1_1_0.utils.queue as queue_mod  # noqa: F811

    real_start = threading.Thread.start

    def broken_start(self, *a, **k):
        if getattr(self, "name", "") == "rxycode-queue-loop":
            raise RuntimeError("thread start refused")
        return real_start(self, *a, **k)

    monkeypatch.setattr(threading.Thread, "start", broken_start)
    q = QueueManager(storage_path=tmp_path / "queue.json")
    task = q.add_task("hello")
    agent, recorded = _agent_with_loop_recorder()

    holder = await _run_task_in_thread(q, task["id"], agent)

    monkeypatch.setattr(threading.Thread, "start", real_start)
    assert "refused" in str(holder["result"])
    updated = next(t for t in q.list_tasks() if t["id"] == task["id"])
    assert updated["status"] == "failed"


@pytest.mark.asyncio
async def test_submit_failure_leaves_no_never_awaited_warning(
    tmp_path, shared_loop_state, monkeypatch
):
    """The failed submit's coroutine is explicitly closed: no 'coroutine was
    never awaited' warning surfaces (warnings promoted to errors)."""
    import warnings

    from RxyCode.RxyCode1_1_0.utils.queue import _get_fallback_loop

    closed = asyncio.new_event_loop()
    closed.close()
    monkeypatch.setattr(queue_mod, "_resolve_execution_loop", lambda: closed)
    q = QueueManager(storage_path=tmp_path / "queue.json")
    task = q.add_task("hello")
    agent, recorded = _agent_with_loop_recorder()

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        holder = await _run_task_in_thread(q, task["id"], agent)

    assert holder["error"] is None
    assert holder["result"] == "ok"
    assert len(recorded) == 1
    assert recorded[0] is _get_fallback_loop()


class _NeverSetReady:
    """Event stand-in whose wait() returns False immediately and whose set()
    is a no-op — used to deterministically exercise the ready-timeout path."""

    def clear(self) -> None:
        pass

    def set(self) -> None:
        pass

    def is_set(self) -> bool:
        return False

    def wait(self, timeout: float | None = None) -> bool:
        return False


@pytest.mark.asyncio
async def test_ready_timeout_is_not_cached(tmp_path, shared_loop_state, monkeypatch):
    """If the loop never signals ready, the failure surfaces (task failed),
    the cache is cleared and no broken loop is retained."""
    import RxyCode.RxyCode1_1_0.utils.queue as queue_mod  # noqa: F811

    monkeypatch.setattr(
        queue_mod, "_FALLBACK_READY_TIMEOUT_S", 0.2
    )
    monkeypatch.setattr(queue_mod, "_fallback_ready", _NeverSetReady())
    q = QueueManager(storage_path=tmp_path / "queue.json")
    task = q.add_task("hello")
    agent, _ = _agent_with_loop_recorder()

    holder = await _run_task_in_thread(q, task["id"], agent)

    assert "failed to start the queue event loop thread" in str(
        holder["result"]
    )
    updated = next(t for t in q.list_tasks() if t["id"] == task["id"])
    assert updated["status"] == "failed"
    assert queue_mod._fallback_loop is None, "broken loop must not be cached"


@pytest.mark.asyncio
async def test_join_timeout_does_not_close_running_loop(
    tmp_path, shared_loop_state, monkeypatch
):
    """If the queue-loop thread refuses to exit within the join timeout, the
    loop must NOT be closed underneath the running thread; the failure
    surfaces and the cache is cleared."""
    import RxyCode.RxyCode1_1_0.utils.queue as queue_mod  # noqa: F811

    monkeypatch.setattr(queue_mod, "_FALLBACK_READY_TIMEOUT_S", 0.2)
    monkeypatch.setattr(queue_mod, "_FALLBACK_JOIN_TIMEOUT_S", 0.1)
    monkeypatch.setattr(queue_mod, "_fallback_ready", _NeverSetReady())
    # Pretend the queue-loop thread is still alive even after join.
    real_is_alive = threading.Thread.is_alive

    def fake_is_alive(self):
        if getattr(self, "name", "") == "rxycode-queue-loop":
            return True
        return real_is_alive(self)

    monkeypatch.setattr(threading.Thread, "is_alive", fake_is_alive)
    q = QueueManager(storage_path=tmp_path / "queue.json")
    task = q.add_task("hello")
    agent, _ = _agent_with_loop_recorder()

    holder = await _run_task_in_thread(q, task["id"], agent)

    monkeypatch.setattr(threading.Thread, "is_alive", real_is_alive)
    assert "failed to start the queue event loop thread" in str(
        holder["result"]
    )
    assert queue_mod._fallback_loop is None


@pytest.mark.asyncio
async def test_double_submit_failure_leaves_no_warning(
    tmp_path, shared_loop_state, monkeypatch
):
    """When BOTH the primary and the retry submit fail, the second coroutine
    is also closed (no 'never awaited' warning) and the failure is recorded."""
    import warnings

    closed = asyncio.new_event_loop()
    closed.close()
    monkeypatch.setattr(queue_mod, "_resolve_execution_loop", lambda: closed)
    monkeypatch.setattr(queue_mod, "_get_fallback_loop", lambda: closed)
    q = QueueManager(storage_path=tmp_path / "queue.json")
    task = q.add_task("hello")
    agent, _ = _agent_with_loop_recorder()

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        holder = await _run_task_in_thread(q, task["id"], agent)

    assert "Error: Event loop is closed" in str(holder["result"])
    updated = next(t for t in q.list_tasks() if t["id"] == task["id"])
    assert updated["status"] == "failed"


@pytest.mark.asyncio
async def test_run_task_recovers_when_resolved_loop_is_closed(
    tmp_path, shared_loop_state, monkeypatch
):
    """TOCTOU: if the resolved loop is closed between the check and the
    submit, run_coroutine_threadsafe raises RuntimeError and the task falls
    back to the process-wide queue loop."""
    closed = asyncio.new_event_loop()
    closed.close()
    monkeypatch.setattr(queue_mod, "_resolve_execution_loop", lambda: closed)
    q = QueueManager(storage_path=tmp_path / "queue.json")
    task = q.add_task("hello")
    agent, recorded = _agent_with_loop_recorder()

    holder = await _run_task_in_thread(q, task["id"], agent)

    assert holder["error"] is None
    assert holder["result"] == "ok"
    assert len(recorded) == 1
    assert recorded[0].is_running()


@pytest.mark.asyncio
async def test_overlapping_lifespan_registration_survives_old_shutdown(
    tmp_path, shared_loop_state
):
    """A later lifespan's registration must not be cleared by an earlier
    lifespan's shutdown (ownership check on the clear)."""
    from RxyCode.RxyCode1_1_0 import api_server

    loop_a = asyncio.get_running_loop()
    loop_b = asyncio.new_event_loop()
    thread_b = threading.Thread(target=loop_b.run_forever, daemon=True)
    thread_b.start()
    try:
        queue_mod.register_shared_loop(loop_a)
        queue_mod.register_shared_loop(loop_b)   # later lifespan wins
        # Simulate lifespan A's shutdown: it must NOT clear B's registration.
        if queue_mod.get_shared_loop() is loop_a:
            queue_mod.register_shared_loop(None)
        assert queue_mod.get_shared_loop() is loop_b
        # Lifespan B's own shutdown clears it.
        if queue_mod.get_shared_loop() is loop_b:
            queue_mod.register_shared_loop(None)
        assert queue_mod.get_shared_loop() is None
    finally:
        loop_b.call_soon_threadsafe(loop_b.stop)
        thread_b.join(timeout=5)
        queue_mod.register_shared_loop(None)


@pytest.mark.asyncio
async def test_api_server_shutdown_clears_only_its_own_loop(tmp_path, shared_loop_state):
    """api_server.shutdown must leave a later registration intact."""
    from RxyCode.RxyCode1_1_0 import api_server

    own = asyncio.get_running_loop()
    later = asyncio.new_event_loop()
    thread_later = threading.Thread(target=later.run_forever, daemon=True)
    thread_later.start()
    original_state = dict(api_server._state)
    try:
        api_server._state["service_loop"] = own
        api_server._state.update(
            {
                "queue_manager": None,
                "scheduler": None,
                "service_futures": set(),
                "service_tasks": set(),
                "init_task": None,
            }
        )
        queue_mod.register_shared_loop(later)   # an overlapping later lifespan
        await api_server.shutdown()
        assert queue_mod.get_shared_loop() is later, (
            "shutdown must not clear a loop it does not own"
        )
        # Now the later lifespan shuts down for real.
        api_server._state["service_loop"] = later
        await api_server.shutdown()
        assert queue_mod.get_shared_loop() is None
    finally:
        later.call_soon_threadsafe(later.stop)
        thread_later.join(timeout=5)
        api_server._state.clear()
        api_server._state.update(original_state)
        queue_mod.register_shared_loop(None)


@pytest.mark.asyncio
async def test_run_task_failure_is_recorded_on_shared_loop(
    tmp_path, shared_loop_state
):
    shared = asyncio.get_running_loop()
    queue_mod.register_shared_loop(shared)
    q = QueueManager(storage_path=tmp_path / "queue.json")
    task = q.add_task("boom")
    agent = MagicMock()

    async def run(prompt: str, mode: str) -> str:
        raise RuntimeError("scripted failure")

    agent.run = run

    holder = await _run_task_in_thread(q, task["id"], agent)

    assert holder["error"] is None  # exceptions are captured by run_task
    assert "scripted failure" in str(holder["result"])
    updated = next(t for t in q.list_tasks() if t["id"] == task["id"])
    assert updated["status"] == "failed"
    assert "scripted failure" in str(updated["result"])


# ── scheduler callback runs on the shared loop ──────────────────────


@pytest.mark.asyncio
async def test_scheduler_callback_dispatches_to_the_shared_loop(
    tmp_path, shared_loop_state
):
    """The API's scheduler callback (_run_scheduled_prompt) submits to the
    shared service loop via run_coroutine_threadsafe; a synchronous
    scheduler.run_task must therefore execute the prompt on that loop."""
    from RxyCode.RxyCode1_1_0 import api_server
    from RxyCode.RxyCode1_1_0.scheduler.manager import TaskScheduler

    shared = asyncio.get_running_loop()
    queue_mod.register_shared_loop(shared)

    executed_loops: list[asyncio.AbstractEventLoop] = []
    original_state = dict(api_server._state)
    try:
        api_server._state["service_loop"] = shared
        api_server._state["task_deadline_seconds"] = 0.0

        async def run(prompt: str, mode: str) -> str:
            executed_loops.append(asyncio.get_running_loop())
            return f"answer-{prompt}"

        api_server._state["agent"] = MagicMock()
        api_server._state["agent"].run = run

        scheduler = TaskScheduler(storage_path=tmp_path / "scheduler.json")
        scheduler.set_callback(api_server._run_scheduled_prompt)
        scheduler.add_task("* * * * *", "scheduled-prompt", task_id="c6test")

        holder: dict = {}

        def worker() -> None:
            try:
                holder["ok"] = scheduler.run_task("c6test")
                holder["error"] = None
            except BaseException as exc:  # noqa: BLE001
                holder["ok"] = False
                holder["error"] = exc

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while thread.is_alive():
            if time.monotonic() > deadline:
                raise AssertionError("scheduler.run_task did not return")
            await asyncio.sleep(0.01)
        assert holder["error"] is None
        assert holder["ok"] is True
        assert executed_loops == [shared], "prompt must run on the shared loop"
        task = scheduler.get_task("c6test")
        assert task is not None and task.last_status == "succeeded"
    finally:
        api_server._state.clear()
        api_server._state.update(original_state)
