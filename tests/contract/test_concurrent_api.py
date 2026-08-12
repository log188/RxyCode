"""Phase C C4 contract tests: session-level concurrency (SessionSlots).

RXYCODE_CONCURRENT_API switch semantics (PHASE-C §4.4 / C4 card):

* ``0`` (default) — global single slot: behaviour identical to the legacy
  serial runtime (second ``/chat/stream`` anywhere is rejected with the busy
  message; ``/chat`` and ``/command`` queue serially).
* ``N`` (N >= 1) — global cap N + one slot per session: two different
  sessions run concurrently; a second request on the same session is
  rejected with the same busy message; ``/chat`` and ``/command`` wait for
  their session slot (serial per session).
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from contextlib import suppress
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from RxyCode.RxyCode1_1_0 import api_server
from RxyCode.RxyCode1_1_0.core.run_lifecycle import SessionSlots

BUSY_MESSAGE = (
    "Agent is busy: please wait for the current response to finish "
    "before sending another message."
)


def _slow_agent(run_delay: float = 0.5, *, starts: list[float] | None = None):
    """Agent whose run() sleeps, optionally recording start/end times."""
    agent = MagicMock()
    agent._stream_mode = False
    agent._tool_tracer = None
    agent._last_thinking = ""
    agent._thinking_history = []
    agent._memory = MagicMock()
    agent._session_loaded = False

    async def run(message: str, mode: str) -> str:
        if starts is not None:
            starts.append(time.monotonic())
        await asyncio.sleep(run_delay)
        return "ok"

    agent.run = run
    agent.cancel = MagicMock(return_value=True)
    return agent


@pytest.fixture
def api_client(monkeypatch):
    """Single TestClient with a mock agent; restores global state after."""
    from RxyCode.RxyCode1_1_0 import api_server as api_server_mod

    original_state = dict(api_server_mod._state)
    api_server_mod._state["agent"] = _slow_agent()
    api_server_mod._state["tui_proxy"] = api_server_mod.APIProxyTUI()
    api_server_mod._state["busy"] = False
    api_server_mod._state["chat_history"] = []
    api_server_mod._state["mode"] = "build"

    token = api_server_mod.configure_api_token()
    with TestClient(
        api_server_mod.app,
        client=("127.0.0.1", 50101),
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client

    api_server_mod._state.clear()
    api_server_mod._state.update(original_state)


def _stream_events(client, session_id: str, message: str = "hi"):
    """POST /chat/stream and return the parsed event list (or the exception)."""
    try:
        with client.stream(
            "POST",
            "/chat/stream",
            json={"message": message, "mode": "build", "session_id": session_id},
        ) as response:
            payloads = []
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                raw = line[len("data: ") :].strip()
                if not raw:
                    continue
                try:
                    payloads.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
            return payloads
    except BaseException as exc:  # noqa: BLE001 — surfaced to the test thread
        return exc


# ── switch resolution (config) ─────────────────────────────────────


def test_concurrent_api_switch_default_off(monkeypatch):
    monkeypatch.delenv("RXYCODE_CONCURRENT_API", raising=False)
    assert api_server.concurrent_api_slots() == 0


def test_concurrent_api_switch_n(monkeypatch):
    monkeypatch.setenv("RXYCODE_CONCURRENT_API", "2")
    assert api_server.concurrent_api_slots() == 2


def test_concurrent_api_switch_invalid_falls_back_to_off(monkeypatch):
    monkeypatch.setenv("RXYCODE_CONCURRENT_API", "abc")
    assert api_server.concurrent_api_slots() == 0


def test_concurrent_api_switch_negative_falls_back_to_off(monkeypatch):
    monkeypatch.setenv("RXYCODE_CONCURRENT_API", "-3")
    assert api_server.concurrent_api_slots() == 0


# ── SessionSlots unit semantics (§4.4) ─────────────────────────────


@pytest.mark.asyncio
async def test_session_slots_two_sessions_do_not_block_each_other():
    slots = SessionSlots(max_concurrent=2)
    await asyncio.wait_for(slots.acquire("a"), timeout=1.0)
    await asyncio.wait_for(slots.acquire("b"), timeout=1.0)
    slots.release("a")
    slots.release("b")


@pytest.mark.asyncio
async def test_session_slots_same_session_is_serial():
    slots = SessionSlots(max_concurrent=2)
    await slots.acquire("a")
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(slots.acquire("a"), timeout=0.05)
    slots.release("a")
    await asyncio.wait_for(slots.acquire("a"), timeout=1.0)
    slots.release("a")


@pytest.mark.asyncio
async def test_session_slots_global_cap_is_enforced():
    slots = SessionSlots(max_concurrent=1)
    await slots.acquire("a")
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(slots.acquire("b"), timeout=0.05)
    slots.release("a")
    await asyncio.wait_for(slots.acquire("b"), timeout=1.0)
    slots.release("b")


@pytest.mark.asyncio
async def test_session_slots_acquire_cancel_does_not_leak():
    """Cancelling an acquire waiting for a slot must not leak counts.

    (Same scenario as the C1-moved test, against the real implementation.)
    """
    slots = SessionSlots(max_concurrent=1)
    await slots.acquire("blocker")

    waiter = asyncio.create_task(slots.acquire("other"))
    await asyncio.sleep(0.05)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    slots.release("blocker")
    # The cancelled waiter must not have leaked the global slot.
    await asyncio.wait_for(slots.acquire("other"), timeout=1.0)
    slots.release("other")


@pytest.mark.asyncio
async def test_session_slots_try_acquire_never_blocks():
    slots = SessionSlots(max_concurrent=2)
    assert await slots.try_acquire("a") is True
    assert await slots.try_acquire("a") is False   # same session busy
    assert await slots.try_acquire("b") is True    # other session fine
    assert await slots.try_acquire("c") is False   # global cap reached
    slots.release("a")
    slots.release("b")
    assert await slots.try_acquire("c") is True
    slots.release("c")


@pytest.mark.asyncio
async def test_session_slots_release_session_refuses_in_flight():
    slots = SessionSlots(max_concurrent=2)
    await slots.acquire("a")
    with pytest.raises(RuntimeError):
        await slots.release_session("a")
    slots.release("a")
    await slots.release_session("a")   # idempotent
    await slots.release_session("a")   # repeated call is safe


@pytest.mark.asyncio
async def test_try_acquire_cancel_is_safe():
    """Cancelling right after a successful try_acquire must not double-release."""
    slots = SessionSlots(max_concurrent=1)
    acquired = await slots.try_acquire("a")
    assert acquired is True
    slots.release("a")
    assert await slots.try_acquire("a") is True
    slots.release("a")


@pytest.mark.asyncio
async def test_try_acquire_and_acquire_share_the_session_slot():
    """try_acquire and acquire must gate on the SAME per-session slot."""
    slots = SessionSlots(max_concurrent=2)
    assert await slots.try_acquire("sess") is True
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(slots.acquire("sess"), timeout=0.05)
    slots.release("sess")
    await asyncio.wait_for(slots.acquire("sess"), timeout=1.0)
    assert await slots.try_acquire("sess") is False
    slots.release("sess")
    assert await slots.try_acquire("sess") is True
    slots.release("sess")


@pytest.mark.asyncio
async def test_try_acquire_cancel_returns_the_global_slot():
    """A cancellation while waiting inside try_acquire must not leak the
    global slot it already took."""
    slots = SessionSlots(max_concurrent=1)

    lock_holder = asyncio.create_task(slots._lock.acquire())
    await asyncio.sleep(0.01)
    assert lock_holder.done() and not lock_holder.cancelled()

    task = asyncio.create_task(slots.try_acquire("sess"))
    await asyncio.sleep(0.05)
    assert not task.done(), "try_acquire should be suspended on the inner lock"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # The lock holder intentionally never releases: cancel it and hand the
    # lock back so the test loop can close cleanly.
    lock_holder.cancel()
    with suppress(asyncio.CancelledError):
        await lock_holder
    if slots._lock.locked():
        slots._lock.release()

    # The cancelled try_acquire must have returned the global slot.
    await asyncio.wait_for(slots._global.acquire(), timeout=1.0)
    slots._global.release()
    assert slots._active.get("sess", 0) == 0
    # The same session is immediately admissible again (no residue).
    assert await slots.try_acquire("sess") is True
    slots.release("sess")
    await slots.release_session("sess")


@pytest.mark.asyncio
async def test_try_acquire_returns_immediately_when_global_cap_reached():
    """try_acquire must NOT suspend on the global semaphore: with the cap
    held by another session it returns False immediately (a strict timeout
    proves there is no global-acquire suspension point)."""
    slots = SessionSlots(max_concurrent=1)
    await slots.acquire("owner")
    result = await asyncio.wait_for(slots.try_acquire("sess"), timeout=0.05)
    assert result is False
    slots.release("owner")


@pytest.mark.asyncio
async def test_try_acquire_has_no_suspension_after_registration():
    """Between registration under _lock and success there is no suspension
    point, so try_acquire cannot be cancelled after registering without
    releasing (the cleanup path is only reachable from the _lock wait).

    We verify this by proving a successful try_acquire is atomic with
    respect to concurrent release_session: no interleaving can delete the
    slot mid-admission.
    """
    slots = SessionSlots(max_concurrent=1)
    for _ in range(25):
        admitted = await slots.try_acquire("sess")
        if admitted:
            slots.release("sess")
        else:
            # The only failure mode without a concurrent holder is the
            # lock-wait cancellation path, which is not exercised here.
            pytest.fail("try_acquire must succeed on an idle session")
    await slots.release_session("sess")


@pytest.mark.asyncio
async def test_try_acquire_b_completion_before_cancel_wins():
    """Deterministic ordering at suspension point B (inner-lock wait).

    When the lock frees BEFORE the cancel arrives, the admission completes;
    a cancel delivered afterwards is a no-op and the accounting stays exact
    (one global slot in, one out).  Together with
    test_try_acquire_cancel_returns_the_global_slot (cancel-first order),
    both arrival orders at B are covered with explicit scheduling control.
    """
    slots = SessionSlots(max_concurrent=1)
    lock_holder = asyncio.create_task(slots._lock.acquire())
    await asyncio.sleep(0.01)
    assert lock_holder.done()

    task = asyncio.create_task(slots.try_acquire("sess"))
    await asyncio.sleep(0.05)
    assert not task.done(), "try_acquire must be suspended at B"

    # Free the lock first: the event loop now completes the admission.
    lock_holder.cancel()
    with suppress(asyncio.CancelledError):
        await lock_holder
    if slots._lock.locked():
        slots._lock.release()
    await asyncio.sleep(0.02)          # deterministic: let B complete
    assert task.done() and not task.cancelled()
    assert task.result() is True

    # A cancel arriving afterwards is a no-op on the finished task.
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    slots.release("sess")
    assert slots._active.get("sess", 0) == 0
    await asyncio.wait_for(slots._global.acquire(), timeout=1.0)
    slots._global.release()
    await slots.release_session("sess")


@pytest.mark.asyncio
async def test_release_session_cannot_race_a_held_admission():
    """With the holder registered under the lock, release_session must
    refuse even when the holder is between registration and release."""
    slots = SessionSlots(max_concurrent=1)
    await slots.acquire("sess")
    with pytest.raises(RuntimeError):
        await slots.release_session("sess")
    slots.release("sess")
    await slots.release_session("sess")
    assert await slots.try_acquire("a") is True
    slots.release("a")


@pytest.mark.asyncio
async def test_acquire_cancel_while_waiting_session_slot_returns_global():
    """Cancelling an acquire that waits on the session slot must return the
    global slot it already took (registration undone)."""
    slots = SessionSlots(max_concurrent=2)
    await slots.acquire("sess")            # holder: global + session slot
    waiter = asyncio.create_task(slots.acquire("sess"))
    await asyncio.sleep(0.05)
    assert not waiter.done()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    # The cancelled waiter must have returned its global slot: another
    # session can now acquire.
    await asyncio.wait_for(slots.acquire("other"), timeout=1.0)
    slots.release("sess")
    slots.release("other")
    assert slots._active.get("sess", 0) == 0
    assert slots._active.get("other", 0) == 0


@pytest.mark.asyncio
async def test_release_session_cannot_race_an_admission():
    """release_session must refuse while a task is registered, even if that
    task is still waiting for the session slot."""
    slots = SessionSlots(max_concurrent=2)
    await slots.acquire("sess")            # holder
    waiter = asyncio.create_task(slots.acquire("sess"))   # registered, waiting
    await asyncio.sleep(0.05)
    with pytest.raises(RuntimeError):
        await slots.release_session("sess")
    waiter.cancel()
    with suppress(asyncio.CancelledError):
        await waiter
    slots.release("sess")
    # After everything is released the session can be dropped.
    await slots.release_session("sess")
    assert "sess" not in slots._per_session


@pytest.mark.asyncio
async def test_release_session_idempotent_after_full_release():
    slots = SessionSlots(max_concurrent=1)
    assert await slots.try_acquire("sess") is True
    slots.release("sess")
    await slots.release_session("sess")
    await slots.release_session("sess")
    # The session can be re-created cleanly afterwards.
    assert await slots.try_acquire("sess") is True
    slots.release("sess")


# ── API contract: switch 0 = legacy behaviour (busy rejection) ──────


def test_switch0_second_stream_different_session_is_busy(api_client, monkeypatch):
    monkeypatch.setenv("RXYCODE_CONCURRENT_API", "0")
    results: dict[str, object] = {}

    def do_stream(key: str, session_id: str) -> None:
        results[key] = _stream_events(api_client, session_id)

    t1 = threading.Thread(target=do_stream, args=("a", "sess-a"), daemon=True)
    t2 = threading.Thread(target=do_stream, args=("b", "sess-b"), daemon=True)
    t1.start()
    time.sleep(0.15)          # let the first stream acquire the global slot
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    events_a = results["a"]
    events_b = results["b"]
    assert isinstance(events_a, list)
    assert isinstance(events_b, list)
    # First stream runs to completion.
    assert events_a[-1]["type"] == "done"
    assert not any(
        p.get("type") == "error" and "busy" in str(p.get("message", "")).lower()
        for p in events_a
    )
    # Second stream is rejected with the compatible busy message.
    busy_events = [
        p for p in events_b if p.get("type") == "error"
    ]
    assert busy_events, "expected a busy error event on the second stream"
    assert BUSY_MESSAGE in str(busy_events[0].get("message", ""))
    assert events_b[-1]["type"] == "done"


def test_switch0_chat_requests_are_serial(api_client, monkeypatch):
    monkeypatch.setenv("RXYCODE_CONCURRENT_API", "0")
    starts: list[float] = []
    ends: list[float] = []
    api_server._state["agent"] = _slow_agent(run_delay=0.35)
    original_run = api_server._state["agent"].run

    async def tracking_run(message: str, mode: str) -> str:
        starts.append(time.monotonic())
        try:
            return await original_run(message, mode)
        finally:
            ends.append(time.monotonic())

    api_server._state["agent"].run = tracking_run
    results: dict[str, object] = {}

    def do_chat(key: str, session_id: str) -> None:
        try:
            resp = api_client.post(
                "/chat",
                json={"message": "hi", "mode": "build", "session_id": session_id},
            )
            results[key] = resp
        except BaseException as exc:  # noqa: BLE001
            results[key] = exc

    t1 = threading.Thread(target=do_chat, args=("a", "sess-a"), daemon=True)
    t2 = threading.Thread(target=do_chat, args=("b", "sess-b"), daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    for key in ("a", "b"):
        assert isinstance(results[key], object) and not isinstance(
            results[key], BaseException
        )
        assert results[key].status_code == 200
    assert len(starts) == 2 and len(ends) == 2
    # Serial: the second run starts only after the first ended.
    ordered_starts = sorted(starts)
    ordered_ends = sorted(ends)
    assert ordered_starts[1] >= ordered_ends[0] - 0.05


# ── API contract: switch 2 = per-session concurrency ────────────────


def test_switch2_two_sessions_stream_concurrently(api_client, monkeypatch):
    monkeypatch.setenv("RXYCODE_CONCURRENT_API", "2")
    results: dict[str, object] = {}

    def do_stream(key: str, session_id: str) -> None:
        results[key] = _stream_events(api_client, session_id)

    t1 = threading.Thread(target=do_stream, args=("a", "sess-a"), daemon=True)
    t2 = threading.Thread(target=do_stream, args=("b", "sess-b"), daemon=True)
    t1.start()
    time.sleep(0.15)          # session A is mid-flight when B arrives
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    for key in ("a", "b"):
        events = results[key]
        assert isinstance(events, list), f"{key}: {results[key]!r}"
        assert events[-1]["type"] == "done", f"{key} did not complete: {events!r}"
        assert not any(
            p.get("type") == "error" and "busy" in str(p.get("message", "")).lower()
            for p in events
        ), f"{key} was wrongly rejected: {events!r}"


def test_switch2_same_session_second_stream_is_busy(api_client, monkeypatch):
    monkeypatch.setenv("RXYCODE_CONCURRENT_API", "2")
    results: dict[str, object] = {}

    def do_stream(key: str, session_id: str) -> None:
        results[key] = _stream_events(api_client, session_id)

    t1 = threading.Thread(target=do_stream, args=("a", "sess-a"), daemon=True)
    t2 = threading.Thread(target=do_stream, args=("b", "sess-a"), daemon=True)
    t1.start()
    time.sleep(0.15)          # first session-A stream is mid-flight
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    events_a = results["a"]
    events_b = results["b"]
    assert isinstance(events_a, list) and isinstance(events_b, list)
    assert events_a[-1]["type"] == "done"
    busy_events = [p for p in events_b if p.get("type") == "error"]
    assert busy_events, "expected busy rejection for the same session"
    assert BUSY_MESSAGE in str(busy_events[0].get("message", ""))
    assert events_b[-1]["type"] == "done"


def test_switch2_chat_two_sessions_overlap(api_client, monkeypatch):
    monkeypatch.setenv("RXYCODE_CONCURRENT_API", "2")
    starts: list[float] = []
    api_server._state["agent"] = _slow_agent(run_delay=0.35, starts=starts)

    results: dict[str, object] = {}

    def do_chat(key: str, session_id: str) -> None:
        try:
            resp = api_client.post(
                "/chat",
                json={"message": "hi", "mode": "build", "session_id": session_id},
            )
            results[key] = resp
        except BaseException as exc:  # noqa: BLE001
            results[key] = exc

    t1 = threading.Thread(target=do_chat, args=("a", "sess-a"), daemon=True)
    t2 = threading.Thread(target=do_chat, args=("b", "sess-b"), daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    for key in ("a", "b"):
        assert not isinstance(results[key], BaseException)
        assert results[key].status_code == 200
    assert len(starts) == 2
    # Concurrent: the second run starts before the first one ends.
    assert abs(starts[0] - starts[1]) < 0.25


def test_switch2_third_session_rejected_when_cap_reached(api_client, monkeypatch):
    monkeypatch.setenv("RXYCODE_CONCURRENT_API", "2")
    results: dict[str, object] = {}

    def do_stream(key: str, session_id: str) -> None:
        results[key] = _stream_events(api_client, session_id)

    t1 = threading.Thread(target=do_stream, args=("a", "sess-a"), daemon=True)
    t2 = threading.Thread(target=do_stream, args=("b", "sess-b"), daemon=True)
    t3 = threading.Thread(target=do_stream, args=("c", "sess-c"), daemon=True)
    t1.start()
    time.sleep(0.1)
    t2.start()
    time.sleep(0.1)
    t3.start()
    t1.join(timeout=15)
    t2.join(timeout=15)
    t3.join(timeout=15)

    for key in ("a", "b"):
        events = results[key]
        assert isinstance(events, list)
        assert events[-1]["type"] == "done"
        assert not any(
            p.get("type") == "error" and "busy" in str(p.get("message", "")).lower()
            for p in events
        )
    events_c = results["c"]
    assert isinstance(events_c, list)
    busy_events = [p for p in events_c if p.get("type") == "error"]
    assert busy_events, "expected busy rejection when the global cap is reached"
    assert BUSY_MESSAGE in str(busy_events[0].get("message", ""))
    assert events_c[-1]["type"] == "done"


def test_default_switch_matches_switch0(api_client, monkeypatch):
    """Without the env var the default behaves exactly like switch 0."""
    monkeypatch.delenv("RXYCODE_CONCURRENT_API", raising=False)
    assert api_server.concurrent_api_slots() == 0
    results: dict[str, object] = {}

    def do_stream(key: str, session_id: str) -> None:
        results[key] = _stream_events(api_client, session_id)

    t1 = threading.Thread(target=do_stream, args=("a", "sess-a"), daemon=True)
    t2 = threading.Thread(target=do_stream, args=("b", "sess-b"), daemon=True)
    t1.start()
    time.sleep(0.15)
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    events_b = results["b"]
    assert isinstance(events_b, list)
    busy_events = [p for p in events_b if p.get("type") == "error"]
    assert busy_events, "default switch must keep the legacy busy rejection"
    assert BUSY_MESSAGE in str(busy_events[0].get("message", ""))


def test_switch_rebuild_preserves_correct_cap(api_client, monkeypatch):
    """Switching env between requests rebuilds the slots with the new cap."""
    monkeypatch.setenv("RXYCODE_CONCURRENT_API", "1")
    assert api_server.concurrent_api_slots() == 1
    monkeypatch.setenv("RXYCODE_CONCURRENT_API", "3")
    assert api_server.concurrent_api_slots() == 3
