"""E2 contract tests: AgentTask lifecycle state machine.

Coverage per PHASE-E §4.2 / §5 E2 acceptance criteria:
- legal transitions all walkable (spawn/ready/run/pause/resume/interrupt)
- illegal transitions raise InvalidTransition
- pause/interrupt write a checkpoint first (write failure refuses pause)
- interrupt really cancels the main task (gather waits) with no observable
  side effect afterwards
- resume double-run guard: concurrent resumes, only one wins; running task
  raises ResumeError
- state/event ordering: started -> paused -> done/cancelled via the bus
"""

from __future__ import annotations

import asyncio

import pytest

from appserver.agent_task import (
    AgentTask,
    InvalidTransition,
    LifecycleState,
    ResumeError,
)
from appserver.eventbus import AgentEvent, AppendOnlyLog, EventBus


class FakeRuntime:
    """Minimal runtime contract: save/load checkpoint + process-tree cancel."""

    def __init__(self, *, fail_save: bool = False) -> None:
        self.checkpoints: dict[str, object] = {}
        self.save_calls = 0
        self.load_calls = 0
        self.cancel_calls = 0
        self.fail_save = fail_save

    async def save_checkpoint(self, agent_id: str) -> object | None:
        self.save_calls += 1
        if self.fail_save:
            return None
        marker = {"n": self.save_calls}
        self.checkpoints[agent_id] = marker
        return marker

    async def load_checkpoint(self, agent_id: str) -> object | None:
        self.load_calls += 1
        return self.checkpoints.get(agent_id)

    async def cancel_process_trees(self, agent_id: str) -> None:
        self.cancel_calls += 1


def _make_bus() -> EventBus:
    return EventBus(AppendOnlyLog())


def _make_task(
    runtime: FakeRuntime | None = None,
    *,
    run_target=None,
    run_delay: float = 0.0,
) -> AgentTask:
    bus = _make_bus()
    rt = runtime if runtime is not None else FakeRuntime()

    async def default_run(task: str) -> str:
        if run_delay:
            await asyncio.sleep(run_delay)
        return f"done:{task}"

    target = run_target or default_run
    return AgentTask(
        agent_id="A",
        bus=bus,
        runtime=rt,
        run_target=target,
    )


async def _drain(sub, count: int, timeout: float = 2.0) -> list[AgentEvent]:
    got: list[AgentEvent] = []
    for _ in range(count):
        try:
            got.append(await asyncio.wait_for(sub.queue.get(), timeout=timeout))
        except asyncio.TimeoutError:
            break
    return got


async def _events(bus: EventBus, count: int, timeout: float = 2.0) -> list[AgentEvent]:
    sub = await bus.subscribe("test", "event/*")
    return await _drain(sub, count, timeout)


@pytest.mark.asyncio
async def test_spawn_walks_to_running_and_done():
    task = _make_task()
    await task.spawn("t1")

    assert task.state == LifecycleState.RUNNING
    await task.wait_state(LifecycleState.DONE)
    assert task.state == LifecycleState.DONE


@pytest.mark.asyncio
async def test_spawn_emits_started_then_done_events():
    bus = _make_bus()
    sub = await bus.subscribe("test", "event/*")
    rt = FakeRuntime()
    task = AgentTask(agent_id="A", bus=bus, runtime=rt, run_target=lambda t: _noop(t))

    await task.spawn("t1")
    await task.wait_state(LifecycleState.DONE)

    evs = await _drain(sub, 2)
    assert [e.method for e in evs] == ["event/agent_started", "event/agent_done"]
    assert evs[0].agent_id == "A"


async def _noop(task: str) -> str:
    return task


@pytest.mark.asyncio
async def test_initial_state_is_idle():
    task = _make_task()
    assert task.state == LifecycleState.IDLE


@pytest.mark.asyncio
async def test_illegal_transition_raises_invalid_transition():
    task = _make_task()
    await task.spawn("t1")
    await task.wait_state(LifecycleState.DONE)

    with pytest.raises(InvalidTransition):
        await task._set_state(LifecycleState.RUNNING)  # DONE -> RUNNING illegal
    with pytest.raises(InvalidTransition):
        await task._set_state(LifecycleState.IDLE)  # DONE -> IDLE illegal


@pytest.mark.asyncio
async def test_spawn_failure_moves_to_failed():
    async def boom(task: str) -> str:
        raise RuntimeError("init exploded")

    task = _make_task(run_target=boom)
    await task.spawn("t1")
    await task.wait_state(LifecycleState.FAILED)
    assert task.state == LifecycleState.FAILED


@pytest.mark.asyncio
async def test_pause_writes_checkpoint_before_transition():
    rt = FakeRuntime()
    task = _make_task(runtime=rt, run_delay=0.05)

    await task.spawn("t1")
    await asyncio.sleep(0.01)
    await task.pause()

    assert rt.save_calls == 1
    assert task.state == LifecycleState.PAUSED
    await task.resume()
    await task.wait_state(LifecycleState.DONE)
    assert rt.load_calls == 1


@pytest.mark.asyncio
async def test_pause_with_failed_checkpoint_refuses_to_pause():
    rt = FakeRuntime(fail_save=True)
    task = _make_task(runtime=rt, run_delay=0.05)

    await task.spawn("t1")
    with pytest.raises(RuntimeError, match="checkpoint"):
        await task.pause()
    assert task.state == LifecycleState.RUNNING


@pytest.mark.asyncio
async def test_pause_emits_paused_event():
    bus = _make_bus()
    sub = await bus.subscribe("test", "event/*")
    rt = FakeRuntime()
    task = AgentTask(
        agent_id="A",
        bus=bus,
        runtime=rt,
        run_target=lambda t: asyncio.sleep(0.05) or t,
    )

    await task.spawn("t1")
    await asyncio.sleep(0.01)
    await task.pause()
    await task.resume()
    await task.wait_state(LifecycleState.DONE)

    evs = await _drain(sub, 3)
    assert [e.method for e in evs] == [
        "event/agent_started",
        "event/agent_paused",
        "event/agent_done",
    ]


@pytest.mark.asyncio
async def test_interrupt_cancels_main_task_and_cascades_tools():
    rt = FakeRuntime()
    started = asyncio.Event()

    async def slow(task: str) -> str:
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            raise

    task = _make_task(runtime=rt, run_target=slow)
    await task.spawn("t1")
    await started.wait()

    await task.interrupt(cascade_tools=True)

    assert task.state == LifecycleState.CANCELLED
    assert rt.cancel_calls == 1
    assert task._main_task is None or task._main_task.done()


@pytest.mark.asyncio
async def test_interrupt_emits_cancelled_event():
    bus = _make_bus()
    sub = await bus.subscribe("test", "event/*")
    rt = FakeRuntime()
    started = asyncio.Event()

    async def slow(task: str) -> str:
        started.set()
        await asyncio.Event().wait()

    task = AgentTask(agent_id="A", bus=bus, runtime=rt, run_target=slow)
    await task.spawn("t1")
    await started.wait()
    await task.interrupt()

    evs = await _drain(sub, 2)
    assert [e.method for e in evs] == ["event/agent_started", "event/agent_cancelled"]


@pytest.mark.asyncio
async def test_interrupt_can_skip_process_tree_cascade():
    rt = FakeRuntime()
    started = asyncio.Event()

    async def slow(task: str) -> str:
        started.set()
        await asyncio.Event().wait()

    task = _make_task(runtime=rt, run_target=slow)
    await task.spawn("t1")
    await started.wait()

    await task.interrupt(cascade_tools=False)
    assert task.state == LifecycleState.CANCELLED
    assert rt.cancel_calls == 0


@pytest.mark.asyncio
async def test_resume_from_failed_state():
    rt = FakeRuntime()
    attempts = {"n": 0}

    async def flaky(task: str) -> str:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("first try fails")
        return "recovered"

    task = _make_task(runtime=rt, run_target=flaky)
    await task.spawn("t1")
    await task.wait_state(LifecycleState.FAILED)
    assert task.state == LifecycleState.FAILED

    # a checkpoint was written earlier (pause semantics); resume restores
    checkpoint = await rt.save_checkpoint("A")
    assert checkpoint is not None
    await task.resume()
    await task.wait_state(LifecycleState.DONE)
    assert task.state == LifecycleState.DONE


@pytest.mark.asyncio
async def test_resume_without_checkpoint_raises():
    rt = FakeRuntime()  # never saved
    async def boom(task: str) -> str:
        raise RuntimeError("boom")
    task = _make_task(runtime=rt, run_target=boom)
    await task.spawn("t1")
    await task.wait_state(LifecycleState.FAILED)
    with pytest.raises(ResumeError, match="no checkpoint"):
        await task.resume()


@pytest.mark.asyncio
async def test_resume_double_run_guard():
    rt = FakeRuntime()
    started = asyncio.Event()

    async def slow(task: str) -> str:
        started.set()
        await asyncio.sleep(0.05)

    task = _make_task(runtime=rt, run_target=slow)
    await task.spawn("t1")
    await started.wait()
    await task.pause()
    # the paused main task is finished (pause cancels it); both resumes race
    results = await asyncio.gather(task.resume(), task.resume(), return_exceptions=True)
    assert len([r for r in results if r is None]) == 1
    assert any(isinstance(r, ResumeError) for r in results)
    await task.wait_state(LifecycleState.DONE)


@pytest.mark.asyncio
async def test_resume_while_running_raises():
    rt = FakeRuntime()
    started = asyncio.Event()

    async def slow(task: str) -> str:
        started.set()
        await asyncio.sleep(0.05)

    task = _make_task(runtime=rt, run_target=slow)
    await task.spawn("t1")
    await started.wait()

    with pytest.raises(ResumeError, match="still running"):
        await task.resume()
    await task.wait_state(LifecycleState.DONE)


@pytest.mark.asyncio
async def test_cancelled_is_terminal_no_resume():
    rt = FakeRuntime()
    started = asyncio.Event()

    async def slow(task: str) -> str:
        started.set()
        await asyncio.Event().wait()

    task = _make_task(runtime=rt, run_target=slow)
    await task.spawn("t1")
    await started.wait()
    await task.interrupt()

    with pytest.raises(ResumeError):
        await task.resume()


@pytest.mark.asyncio
async def test_wait_state_timeout_raises():
    task = _make_task(run_delay=10)
    await task.spawn("t1")
    with pytest.raises(TimeoutError):
        await task.wait_state(LifecycleState.DONE, timeout=0.05)
    # cleanup: cancel the running task so the test suite does not leak
    await task.interrupt(cascade_tools=False)


@pytest.mark.asyncio
async def test_wait_state_returns_target_state():
    task = _make_task(run_delay=0.02)
    await task.spawn("t1")
    assert await task.wait_state(LifecycleState.DONE, timeout=2.0) == LifecycleState.DONE


@pytest.mark.asyncio
async def test_interrupt_on_idle_task_raises_invalid_transition():
    task = _make_task()
    with pytest.raises(InvalidTransition):
        await task.interrupt()


@pytest.mark.asyncio
async def test_pause_on_idle_task_raises_invalid_transition():
    task = _make_task()
    with pytest.raises(InvalidTransition):
        await task.pause()
