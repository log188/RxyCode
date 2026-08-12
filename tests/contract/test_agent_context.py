"""E6 contract tests: AgentContext slicing + SharedReadonlySegment.

Coverage per PHASE-E §4.4 / §5 E6:
- agent A's messages can never be referenced by agent B (EB2 isolation)
- shared memory read-only path has no write surface
- per-agent tail retention (Pi-style) and session-level cache counting
  (reasonix-style)
- SharedReadonlySegment (F17 dependency): read-only + byte-stable +
  same-object view + duplicate-mount rejection + SegmentClosedError after
  session teardown; one instance may be shared across runtimes
"""

from __future__ import annotations

import pytest

from appserver.agent_context import (
    AgentContext,
    ReadonlyMemoryIndex,
    SegmentAlreadyMountedError,
    SegmentClosedError,
    SessionCacheCounter,
    SessionSharedSegment,
    SharedReadonlySegment,
)


# ---------------------------------------------------------------------------
# SharedReadonlySegment (公共前缀, F17 dependency)
# ---------------------------------------------------------------------------


def test_segment_read_returns_same_bytes_view():
    content = b"public prefix: tool definitions + team convention"
    seg = SharedReadonlySegment(content=content)
    assert seg.read() is content  # same byte-string view (no copy)
    assert seg.read() == content
    assert isinstance(seg.read(), bytes)


def test_segment_rejects_mutable_content_types():
    with pytest.raises(TypeError):
        SharedReadonlySegment(content=bytearray(b"mutable"))  # type: ignore[arg-type]


def test_segment_is_frozen_after_construction():
    seg = SharedReadonlySegment(content=b"abc")
    with pytest.raises(AttributeError):
        seg.content = b"changed"  # type: ignore[misc]


def test_segment_bytes_stable_across_reads():
    seg = SharedReadonlySegment(content=b"stable prefix")
    first = seg.read()
    second = seg.read()
    assert first is second
    assert first == b"stable prefix"


def test_segment_close_then_read_raises():
    seg = SharedReadonlySegment(content=b"abc")
    seg.close()
    with pytest.raises(SegmentClosedError):
        seg.read()


def test_segment_shared_across_runtimes():
    seg = SharedReadonlySegment(content=b"shared")
    rt1 = SessionSharedSegment()
    rt2 = SessionSharedSegment()
    rt1.mount(seg)
    rt2.mount(seg)  # read-only instance may be shared
    assert rt1.read() is rt2.read()


# ---------------------------------------------------------------------------
# SessionSharedSegment mounting semantics (F6/F17)
# ---------------------------------------------------------------------------


def test_duplicate_mount_rejected():
    holder = SessionSharedSegment()
    holder.mount(SharedReadonlySegment(content=b"first"))
    with pytest.raises(SegmentAlreadyMountedError):
        holder.mount(SharedReadonlySegment(content=b"second"))


def test_unmounted_read_raises_closed():
    holder = SessionSharedSegment()
    with pytest.raises(SegmentClosedError):
        holder.read()


def test_teardown_closes_segment():
    holder = SessionSharedSegment()
    holder.mount(SharedReadonlySegment(content=b"abc"))
    holder.close()
    with pytest.raises(SegmentClosedError):
        holder.read()


# ---------------------------------------------------------------------------
# AgentContext slicing (EB2)
# ---------------------------------------------------------------------------


def test_messages_isolated_between_agents():
    a = AgentContext(agent_id="A")
    b = AgentContext(agent_id="B")
    a.add_message({"role": "user", "content": "secret-of-A"})

    assert b.messages == []  # B cannot see A's slice
    assert a.messages is not b.messages  # distinct mutable state
    b.add_message({"role": "user", "content": "secret-of-B"})
    assert len(a.messages) == 1
    assert a.messages[0]["content"] == "secret-of-A"


def test_context_scope_label():
    own = AgentContext(agent_id="A")
    sess = AgentContext(agent_id="B", scope="session")
    assert own.scope == "own"
    assert sess.scope == "session"


def test_tool_results_scoped_to_owning_agent():
    a = AgentContext(agent_id="A")
    b = AgentContext(agent_id="B")
    a.record_tool_result("read", {"path": "/x"})
    assert "read" in a.tool_results
    assert b.tool_results == {}


# ---------------------------------------------------------------------------
# per-agent tail retention (Pi-style)
# ---------------------------------------------------------------------------


def test_tail_retention_keeps_last_n_messages():
    ctx = AgentContext(agent_id="A", tail_limit=3)
    for i in range(10):
        ctx.add_message({"role": "user", "content": f"m{i}"})
    assert len(ctx.messages) == 3
    assert ctx.messages[0]["content"] == "m7"
    assert ctx.messages[-1]["content"] == "m9"


def test_tail_retention_default_limit():
    ctx = AgentContext(agent_id="A")
    for i in range(30):
        ctx.add_message({"role": "user", "content": f"m{i}"})
    assert len(ctx.messages) <= 12


# ---------------------------------------------------------------------------
# session-level cache counting (reasonix-style)
# ---------------------------------------------------------------------------


def test_cache_counters_accumulate_across_agent_switches():
    counter = SessionCacheCounter()
    a = AgentContext(agent_id="A", session_cache=counter)
    b = AgentContext(agent_id="B", session_cache=counter)
    a.record_cache(hit=True)
    b.record_cache(hit=True)
    a.record_cache(hit=False)
    assert counter.hits == 2  # session-level, shared across agents
    assert counter.misses == 1
    assert a.session_cache is b.session_cache  # same session counter


def test_cache_counter_defaults_to_per_context_when_isolated():
    a = AgentContext(agent_id="A")
    b = AgentContext(agent_id="B")
    a.record_cache(hit=True)
    assert a.session_cache.hits == 1
    assert b.session_cache is None  # untouched agents have no counter


# ---------------------------------------------------------------------------
# read-only memory index (shared memory read path, EB2 no-write)
# ---------------------------------------------------------------------------


class _FakeMemory:
    """Minimal stand-in for memory.Manager's read surface."""

    def __init__(self):
        self.entries = ["entry-1", "entry-2"]
        self._writes = 0

    def get_retrieval_context(self, query, **kwargs):
        return [e for e in self.entries if query in e]

    def store_execution(self, *args, **kwargs):
        self._writes += 1
        return None


def test_readonly_memory_index_exposes_no_write_path():
    fake = _FakeMemory()
    index = ReadonlyMemoryIndex(fake)
    assert index.query("entry") == ["entry-1", "entry-2"]
    assert not hasattr(index, "store_execution")
    assert not hasattr(index, "add_interaction")
    with pytest.raises(AttributeError):
        index.__getattribute__("store_execution")
    assert fake._writes == 0  # nothing wrote through the readonly view
