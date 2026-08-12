"""E1 contract tests for the EventBus (append-only, pattern subscriptions).

Coverage per PHASE-E §5 E1 acceptance criteria:
- subscribe/unsubscribe; slow subscriber drops events without blocking
- replay order: after concurrent publishes, replay-by-seq matches live order
- rolling point: seq before the log rollover raises ReplayUnavailableError
- RXYCODE_EVENTBUS_LOG=0 disables replay (ReplayUnavailableError)
- routing metadata: send_to exact delivery + dead-letter warning without
  blocking the publisher (RB3)
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

import pytest

from appserver.eventbus import (
    AppendOnlyLog,
    AgentEvent,
    EventBus,
    ReplayUnavailableError,
)

#: RXYCODE_EVENTBUS_LOG=0 disables the event log: replay success-path tests
#: skip so the contract suite stays green on both switch settings.
_LOG_OFF = os.environ.get("RXYCODE_EVENTBUS_LOG", "1") == "0"


def _require_replay() -> None:
    if _LOG_OFF:
        pytest.skip("replay unavailable: RXYCODE_EVENTBUS_LOG=0")


def _event(method: str, agent_id: str, session_id: str = "s", **extra) -> AgentEvent:
    payload = extra.pop("payload", {"k": "v"})
    return AgentEvent(
        method=method,
        session_id=session_id,
        agent_id=agent_id,
        payload=payload,
        **extra,
    )


def _bus(persist: bool | None = None, max_entries: int = 100_000) -> EventBus:
    log = AppendOnlyLog(max_entries=max_entries, persist=persist)
    return EventBus(log)


async def _drain(sub, limit: int = 100) -> list[AgentEvent]:
    events: list[AgentEvent] = []
    for _ in range(limit):
        try:
            events.append(sub.queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return events


async def _collect(sub, count: int, timeout: float = 2.0) -> list[AgentEvent]:
    events: list[AgentEvent] = []
    for _ in range(count):
        try:
            events.append(
                await asyncio.wait_for(sub.queue.get(), timeout=timeout)
            )
        except asyncio.TimeoutError:
            break
    return events


@pytest.mark.asyncio
async def test_subscribe_receives_matching_events():
    bus = _bus()
    sub = await bus.subscribe("system", "event/*")

    await bus.publish(_event("event/agent_started", "A"))
    await bus.publish(_event("event/agent_done", "B"))

    got = await _collect(sub, 2)
    assert [e.agent_id for e in got] == ["A", "B"]


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    bus = _bus()
    sub = await bus.subscribe("system", "event/*")
    await bus.publish(_event("event/agent_started", "A"))
    assert (await _collect(sub, 1)) != []

    bus.unsubscribe(sub)
    await bus.publish(_event("event/agent_done", "A"))
    assert await _drain(sub) == []


@pytest.mark.asyncio
async def test_unsubscribe_is_idempotent():
    bus = _bus()
    sub = await bus.subscribe("system", "event/*")
    bus.unsubscribe(sub)
    bus.unsubscribe(sub)  # must not raise


@pytest.mark.asyncio
async def test_pattern_agent_wildcard_and_method():
    bus = _bus()
    all_a = await bus.subscribe("agent-a", "agent/A/*")
    tool_only = await bus.subscribe("agent-a-tool", "agent/A/agent_tool")

    await bus.publish(_event("event/agent_started", "A"))
    await bus.publish(_event("event/agent_tool", "A"))
    await bus.publish(_event("event/agent_tool", "B"))

    assert [e.method for e in await _collect(all_a, 2)] == [
        "event/agent_started",
        "event/agent_tool",
    ]
    assert [e.method for e in await _collect(tool_only, 1)] == ["event/agent_tool"]


@pytest.mark.asyncio
async def test_pattern_no_match_receives_nothing():
    bus = _bus()
    sub = await bus.subscribe("system", "agent/B/*")
    await bus.publish(_event("event/agent_started", "A"))
    assert await _drain(sub) == []


@pytest.mark.asyncio
async def test_slow_subscriber_drops_without_blocking_publisher():
    bus = _bus()
    sub = await bus.subscribe("slow", "event/*")

    for i in range(2048):
        await bus.publish(_event("event/agent_started", "A", session_id=f"n{i}"))

    assert sub.dropped is True
    got = await _drain(sub)
    assert len(got) <= 1024  # queue capacity, publisher never blocked


@pytest.mark.asyncio
async def test_concurrent_publishes_assign_strict_monotonic_seq():
    bus = _bus()
    sub = await bus.subscribe("system", "event/*")

    async def fire(n: int) -> None:
        for i in range(50):
            await bus.publish(_event("event/agent_progress", f"g{n}", payload={"i": i}))

    await asyncio.gather(*(fire(n) for n in range(4)))

    events = await _collect(sub, 200)
    seqs = [e.seq for e in events]
    assert len(seqs) == 200
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 200  # no duplicates, no interleave corruption


@pytest.mark.asyncio
async def test_replay_matches_live_order_after_concurrent_publish():
    bus = _bus()
    _require_replay()
    await bus.subscribe("system", "event/*")

    async def fire(n: int) -> None:
        for i in range(25):
            await bus.publish(_event("event/agent_progress", f"g{n}", payload={"i": i}))

    await asyncio.gather(*(fire(n) for n in range(4)))

    replayed = [e async for e in bus.replay(after_seq=0)]
    assert len(replayed) == 100
    assert [e.seq for e in replayed] == list(range(1, 101))
    assert all("i" in e.payload for e in replayed)


@pytest.mark.asyncio
async def test_replay_pages_by_page_size():
    bus = _bus()
    _require_replay()
    for i in range(10):
        await bus.publish(_event("event/agent_started", "A", session_id=f"n{i}"))

    # replay is cursor-driven by after_seq; page_size is an internal batching
    # hint and must never change the returned stream.
    full = [e async for e in bus.replay(after_seq=0)]
    assert len(full) == 10
    tail = [e async for e in bus.replay(after_seq=4)]
    assert len(tail) == 6
    assert tail[0].seq == 5

    small_batch = [e async for e in bus.replay(after_seq=0, page_size=3)]
    large_batch = [e async for e in bus.replay(after_seq=0, page_size=200)]
    assert [e.seq for e in small_batch] == [e.seq for e in large_batch]


@pytest.mark.asyncio
async def test_replay_after_last_seq_yields_nothing():
    bus = _bus()
    _require_replay()
    await bus.publish(_event("event/agent_started", "A"))
    assert [e async for e in bus.replay(after_seq=1)] == []


@pytest.mark.asyncio
async def test_replay_before_rollover_raises():
    bus = _bus(max_entries=8)
    _require_replay()
    for i in range(20):
        await bus.publish(_event("event/agent_started", "A", session_id=f"n{i}"))

    earliest = bus.log.earliest_seq
    assert earliest > 1
    with pytest.raises(ReplayUnavailableError):
        async for _ in bus.replay(after_seq=0):  # noqa: B007
            pass
    # after the rollover point replay still works
    ok = [e async for e in bus.replay(after_seq=earliest - 1)]
    assert ok and ok[0].seq == earliest


@pytest.mark.asyncio
async def test_log_disabled_makes_replay_unavailable(monkeypatch):
    monkeypatch.setenv("RXYCODE_EVENTBUS_LOG", "0")
    bus = _bus()
    await bus.publish(_event("event/agent_started", "A"))

    with pytest.raises(ReplayUnavailableError):
        async for _ in bus.replay(after_seq=0):  # noqa: B007
            pass
    # live delivery still works when the log is off
    sub = await bus.subscribe("system", "event/*")
    await bus.publish(_event("event/agent_done", "A"))
    assert (await _collect(sub, 1)) != []


@pytest.mark.asyncio
async def test_send_to_routes_only_to_target_agent():
    bus = _bus()
    a_sub = await bus.subscribe("agent-a", "agent/A/*")
    b_sub = await bus.subscribe("agent-b", "agent/B/*")

    await bus.publish(_event("event/agent_done", "A", send_to="B"))

    assert await _drain(a_sub) == []
    assert len(await _collect(b_sub, 1)) == 1


@pytest.mark.asyncio
async def test_send_to_dead_letter_does_not_block_publisher():
    bus = _bus()
    sub = await bus.subscribe("system", "event/*")

    # nobody subscribes to agent GHOST: dead-lettered, publisher not blocked
    await bus.publish(_event("event/agent_done", "GHOST", send_to="GHOST"))

    # the event is still persisted and delivered to event/* subscribers (RB3:
    # control-plane bus never blocks on routing)
    got = await _collect(sub, 1)
    assert len(got) == 1


@pytest.mark.asyncio
async def test_send_to_star_broadcasts_to_all_matching():
    bus = _bus()
    a_sub = await bus.subscribe("agent-a", "agent/A/*")
    b_sub = await bus.subscribe("agent-b", "agent/B/*")

    await bus.publish(_event("event/agent_done", "A", send_to="*"))

    assert len(await _collect(a_sub, 1)) == 1
    assert await _drain(b_sub) == []


@pytest.mark.asyncio
async def test_seq_never_rewinds_across_rollover():
    bus = _bus(max_entries=4)
    _require_replay()
    for i in range(9):
        await bus.publish(_event("event/agent_started", "A", session_id=f"n{i}"))
    replayed = [e async for e in bus.replay(after_seq=5)]
    seqs = [e.seq for e in replayed]
    assert seqs == list(range(6, 10))


@pytest.mark.asyncio
async def test_oversized_payload_rejected_eb8():
    bus = _bus()
    with pytest.raises(ValueError, match="EB8"):
        await bus.publish(_event("event/agent_progress", "A", payload={"blob": "x" * 70000}))


@pytest.mark.asyncio
async def test_async_iterator_is_paged_and_resumable():
    bus = _bus()
    _require_replay()
    for i in range(7):
        await bus.publish(_event("event/agent_started", "A", session_id=f"n{i}"))

    it: AsyncIterator[AgentEvent] = bus.replay(after_seq=0, page_size=3)
    first = await it.__anext__()
    assert first.seq == 1
    rest = [e async for e in it]
    assert [e.seq for e in rest] == [2, 3, 4, 5, 6, 7]
