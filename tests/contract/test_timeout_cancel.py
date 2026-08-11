"""Phase C C7 contract tests: unified timeout/cancel semantics.

Two execution paths are locked down (PHASE-C §4.3 / C7 card):

* coroutine path (tools carrying ``coroutine=``): an outer ``wait_for``
  timeout cancels the tool task; ``CancelledError`` penetrates into the
  tool's coroutine, so process-class tools reach the controlled shell
  executor's process-tree termination (no residual process).
* sync fallback path (tools without ``coroutine``): a timeout only stops
  WAITING - the sync call keeps occupying its worker thread until it
  returns (§4.3 stop-waiting boundary; nothing is killed).

Plus: cancellation latency < 2s, and the PHASE-B B4/B7 compression LLM
calls are async (ainvoke), never blocking the event loop from a sync path.
"""

from __future__ import annotations

import asyncio
import ast
import inspect
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from RxyCode.RxyCode1_1_0.execution.tool_orchestrator import ToolOrchestrator


def _make_orchestrator(tool=None, *, name: str | None = None) -> ToolOrchestrator:
    orch = ToolOrchestrator()
    if tool is not None:
        orch.register(name or tool.name, tool, risk="write")
    return orch


class _SyncProcessTool:
    """A process tool with NO ``coroutine`` attribute at all (sync path).

    A plain class - unlike a MagicMock it genuinely lacks the attribute, so
    the orchestrator's `getattr(tool, "coroutine", None)` probe returns
    None exactly as it does for a legacy sync-only tool.
    """

    name = "sync-process-slow"

    def __init__(self, argv: list[str]) -> None:
        self._argv = argv

    def invoke(self, args) -> str:
        import subprocess

        subprocess.run(self._argv, timeout=600)
        return "sync-process-done"


def _coro_tool(name: str, *, cancelled_events: list[str] | None = None) -> MagicMock:
    """A tool WITH coroutine= whose async body records cancellation."""
    tool = MagicMock()
    tool.name = name
    events = cancelled_events if cancelled_events is not None else []

    async def ainvoke(args) -> str:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            events.append(name)
            raise
        return f"{name}-done"

    tool.ainvoke = ainvoke
    tool.coroutine = ainvoke
    return tool


def _invoke(orchestrator: ToolOrchestrator, tool, args="x", timeout: float = 30):
    """Drive the orchestrator's public choke point with a short timeout."""
    return orchestrator.execute_tool(
        tool.name, args, {"execution": {"tool_timeout_seconds": timeout}}
    )


def _marker_pids(marker: str) -> set[int]:
    """Cross-platform PID collection for processes whose command line
    contains *marker*; the query cannot self-match (Windows base64-encoded,
    POSIX pgrep never matches itself)."""
    import base64
    import subprocess
    import sys

    if sys.platform == "win32":
        ps = (
            "Get-CimInstance Win32_Process | "
            f"Where-Object {{ $_.CommandLine -like '*{marker}*' }} | "
            "ForEach-Object { $_.ProcessId }"
        )
        encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
        out = subprocess.run(
            ["powershell", "-NoProfile", "-EncodedCommand", encoded],
            capture_output=True, text=True, timeout=10,
        ).stdout
    else:
        out = subprocess.run(
            ["pgrep", "-f", marker], capture_output=True, text=True, timeout=10
        ).stdout
    return {int(line) for line in out.split() if line.strip().isdigit()}


# ── coroutine path: timeout cancels the tool task ────────────────────


@pytest.mark.asyncio
async def test_coroutine_tool_timeout_cancels_the_task():
    """wait_for timeout must CANCEL the tool's coroutine task (not just stop
    waiting): the tool observes CancelledError."""
    events: list[str] = []
    tool = _coro_tool("slow-coro", cancelled_events=events)
    orchestrator = _make_orchestrator(tool)

    result = await _invoke(orchestrator, tool, timeout=0.1)

    assert "[error: tool 'slow-coro' timed out after 0.1s]" in result
    assert events == ["slow-coro"], "the tool must observe the cancellation"


@pytest.mark.asyncio
async def test_coroutine_tool_cancelled_error_is_not_swallowed():
    """An explicit external cancellation propagates (CancelledError is
    re-raised by the orchestrator, not converted to an error string)."""
    events: list[str] = []
    tool = _coro_tool("cancel-me", cancelled_events=events)
    orchestrator = _make_orchestrator(tool)

    task = asyncio.create_task(_invoke(orchestrator, tool, timeout=30))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert events == ["cancel-me"]


# ── sync fallback path: timeout stops waiting only ────────────────────


@pytest.mark.asyncio
async def test_sync_fallback_timeout_stops_waiting_only():
    """A PROCESS tool without a coroutine attribute follows the stop-waiting
    boundary: the timeout returns the error, the spawned subprocess keeps
    running (nothing is killed), and the test reaps it afterwards."""
    import signal
    import subprocess
    import sys as _sys
    import uuid as _uuid

    marker = f"rxycode-c7-sync-{_uuid.uuid4().hex}"
    tool = _SyncProcessTool(
        [_sys.executable, "-c", f"import time; time.sleep(600)  # {marker}"]
    )
    orchestrator = _make_orchestrator(tool)
    assert not hasattr(tool, "coroutine"), "the tool must truly lack coroutine"

    before = _marker_pids(marker)
    started = time.monotonic()
    result = await _invoke(orchestrator, tool, timeout=0.2)
    elapsed = time.monotonic() - started

    assert "[error: tool 'sync-process-slow' timed out after 0.2s]" in result
    assert elapsed < 1.0, "the call must return before the sync call finishes"
    # The spawned subprocess is still alive (stop-waiting, nothing killed).
    new_pids = _marker_pids(marker) - before
    assert new_pids, "the sync subprocess must still be running (stop-waiting)"
    # Drain: terminate the leftover process so the test tears down cleanly.
    for pid in new_pids:
        try:
            __import__("os").kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _marker_pids(marker) - before:
        await asyncio.sleep(0.1)
    assert not (_marker_pids(marker) - before), "cleanup must reap the test process"


# ── process-class tool: orchestrator timeout reaches the process tree ──


@pytest.mark.asyncio
async def test_process_class_tool_timeout_leaves_no_residual_process():
    """End-to-end: a tool whose coroutine runs a hanging process through the
    controlled shell executor must be terminated on orchestrator timeout —
    no residual process survives (C7 criterion 1; complements C2's
    executor-level PID test at the orchestrator layer)."""
    import subprocess
    import sys as _sys
    import uuid as _uuid

    from RxyCode.RxyCode1_1_0.utils.shell import shell_executor

    marker = f"rxycode-c7-timeout-{_uuid.uuid4().hex}"
    script = f"import time; time.sleep(600)  # {marker}"
    blocker = _sys.executable

    before = _marker_pids(marker)

    async def ainvoke(args) -> str:
        result = await shell_executor.execute_argv_async(
            [blocker, "-c", script], timeout=600
        )
        return str(result)

    tool = MagicMock()
    tool.name = "process-slow"
    tool.ainvoke = ainvoke
    tool.coroutine = ainvoke
    orchestrator = _make_orchestrator(tool)

    result = await _invoke(orchestrator, tool, timeout=0.4)

    assert "timed out after 0.4s" in result
    # The process-tree cleanup is asynchronous (taskkill / killpg); poll
    # until no residual process survives (bounded wait, then fail).
    deadline = time.monotonic() + 10
    new_pids: set[int] = set()
    while time.monotonic() < deadline:
        new_pids = _marker_pids(marker) - before
        if not new_pids:
            break
        await asyncio.sleep(0.25)
    assert not new_pids, f"residual process(es) after timeout: {new_pids}"


# ── cancellation latency ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_path_latency_includes_process_cleanup():
    """The timeout path (wait_for -> cancel -> process-tree cleanup) must
    complete in < 2s per round, measured over 3 rounds (worst-case). The
    measured window ends when _invoke returns, which is only after the
    cancellation has propagated and the shell cleanup has run."""
    import sys as _sys
    import uuid as _uuid

    from RxyCode.RxyCode1_1_0.utils.shell import shell_executor

    latencies: list[float] = []
    for _ in range(3):
        marker = f"rxycode-c7-latency-{_uuid.uuid4().hex}"
        script = f"import time; time.sleep(600)  # {marker}"

        async def ainvoke(args, _script=script) -> str:
            result = await shell_executor.execute_argv_async(
                [_sys.executable, "-c", _script], timeout=600
            )
            return str(result)

        tool = MagicMock()
        tool.name = "latency-process"
        tool.ainvoke = ainvoke
        tool.coroutine = ainvoke
        orchestrator = _make_orchestrator(tool)

        before = _marker_pids(marker)
        started = time.monotonic()
        result = await _invoke(orchestrator, tool, timeout=0.3)
        latencies.append(time.monotonic() - started)
        # The "timed out" result itself proves the process WAS spawned and
        # still running at the deadline: a spawn failure would surface as a
        # spawn_error result, never as a timeout (the shell spawn-error
        # path is covered by C2's contract tests).
        assert "timed out after 0.3s" in result
        # The process tree must already be gone at return (cleanup ran
        # inside the cancellation window).
        assert not (_marker_pids(marker) - before)
    worst = max(latencies)
    assert worst < 2.0, f"worst timeout-path latency {worst:.3f}s >= 2s"


@pytest.mark.asyncio
async def test_cancellation_latency_is_below_2s():
    """Cancellation latency (external cancel -> task completion) measured
    over 3 rounds must stay below 2s on every round (C7 criterion)."""
    latencies: list[float] = []
    for _ in range(3):
        tool = _coro_tool("latency")
        orchestrator = _make_orchestrator(tool)
        task = asyncio.create_task(_invoke(orchestrator, tool, timeout=30))
        await asyncio.sleep(0.05)
        started = time.monotonic()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        latencies.append(time.monotonic() - started)
    worst = max(latencies)
    assert worst < 2.0, f"worst cancellation latency {worst:.3f}s >= 2s"


# ── PHASE-B B4/B7 linkage: compression LLM calls are async ───────────


def test_compression_llm_calls_are_async_not_sync_blocking():
    """The whole memory/compression package (PHASE-B B4/B7), scanned
    recursively with AST: every .invoke( call on an LLM attribute is a
    violation (a sync LLM call would block the event loop), and at least
    one await self._llm.ainvoke( must exist (the Tier-3 path)."""
    from RxyCode.RxyCode1_1_0.memory import compressor

    package_root = Path(compressor.__file__).parent
    sync_calls: list[str] = []
    async_calls = 0
    for source_path in sorted(package_root.rglob("*.py")):
        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(
                node.func, ast.Attribute
            ):
                continue
            attr = node.func.attr
            if attr == "invoke":
                sync_calls.append(f"{source_path.name}:{node.lineno}")
            if attr == "ainvoke":
                async_calls += 1
    assert not sync_calls, (
        f"sync LLM invocation(s) in memory/compression: {sync_calls}"
    )
    assert async_calls >= 1, (
        "the compression path must use ainvoke somewhere"
    )
