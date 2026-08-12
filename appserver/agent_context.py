"""Phase E · E6 — AgentContext slicing and SharedReadonlySegment.

Each agent owns its context slice (messages / tool results / memory
references) keyed by ``agent_id`` (EB2: agents never read or write another
agent's slice).  Shared state is explicit and read-only: the session-wide
``SharedReadonlySegment`` (公共前缀, F17 dependency) and the read-only
memory index.  Per-agent tail retention (Pi-style) and session-level cache
counters (reasonix-style) live here.  See PHASE-E §4.4 / §5 E6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


class SegmentClosedError(RuntimeError):
    """Raised when a shared segment is read after the session teardown."""


class SegmentAlreadyMountedError(RuntimeError):
    """Raised when a session tries to mount a second shared segment."""


@dataclass(frozen=True)
class SharedReadonlySegment:
    """Session-wide read-only prefix (tool definitions + team convention).

    ``content`` is immutable ``bytes`` (mutable types rejected); every
    ``read()`` returns the same byte-string object (single construction,
    shared reference, byte-stable).  ``close()`` makes further reads raise
    ``SegmentClosedError`` (no reads after session teardown).  One instance
    may be shared by several AgentRuntimes (stateless read-only reference).
    """

    content: bytes
    _closed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise TypeError(
                f"SharedReadonlySegment.content must be bytes, got "
                f"{type(self.content).__name__}"
            )

    def read(self) -> bytes:
        if self._closed:
            raise SegmentClosedError("shared segment closed (session teardown)")
        return self.content

    def close(self) -> None:
        object.__setattr__(self, "_closed", True)


class SessionSharedSegment:
    """Mount point for the session's shared readonly segment.

    Mounting happens at session start, before any member spawn (F6/F17);
    a second mount is rejected; after ``close`` every read raises.
    """

    def __init__(self) -> None:
        self._segment: SharedReadonlySegment | None = None

    def mount(self, segment: SharedReadonlySegment) -> None:
        if self._segment is not None:
            raise SegmentAlreadyMountedError(
                "session already has a shared segment; mount only once"
            )
        self._segment = segment

    def read(self) -> bytes:
        if self._segment is None:
            raise SegmentClosedError("no shared segment mounted for this session")
        return self._segment.read()

    def close(self) -> None:
        if self._segment is not None:
            self._segment.close()
            self._segment = None


class SessionCacheCounter:
    """Session-level cache accounting (reasonix-style, PHASE-E §4.4).

    One counter object per session/runtime; every AgentContext in the
    session shares it, so counts never reset when the active agent
    switches (shared mutable state is explicit and confined to this
    accounting object).
    """

    def __init__(self) -> None:
        self.hits: int = 0
        self.misses: int = 0

    def record(self, hit: bool) -> None:
        if hit:
            self.hits += 1
        else:
            self.misses += 1


class ReadonlyMemoryIndex:
    """Read-only facade over the session memory index (EB2 no-write path).

    Only read methods are forwarded; write/management methods are never
    exposed through this view.  ``memory/`` files themselves are untouched
    (read-only reference surface).
    """

    def __init__(self, memory: Any) -> None:
        self._memory = memory

    def query(self, query: str, **kwargs) -> list[str]:
        """Read-only retrieval over the session memory index."""
        result = self._memory.get_retrieval_context(query, **kwargs)
        if result is None:
            return []
        return list(result)


@dataclass
class AgentContext:
    """One agent's context slice (PHASE-E §4.4).

    - ``messages`` / ``tool_results`` are the agent's own slice (EB2)
    - ``tail_limit`` applies Pi-style tail retention to the slice
    - ``session_cache_hits/misses`` are session-level counters that never
      reset when the active agent switches (reasonix-style)
    - shared read-only references are explicit (segment + memory index)
    """

    agent_id: str
    scope: Literal["session", "own"] = "own"
    tail_limit: int = 12
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_results: dict[str, Any] = field(default_factory=dict)
    memory_refs: list[str] = field(default_factory=list)
    shared_segment: SharedReadonlySegment | None = None
    memory_index: ReadonlyMemoryIndex | None = None
    session_cache: SessionCacheCounter | None = None

    def add_message(self, message: dict[str, Any]) -> None:
        """Append to this agent's slice, applying tail retention."""
        self.messages.append(message)
        overflow = len(self.messages) - self.tail_limit
        if overflow > 0:
            del self.messages[:overflow]

    def record_tool_result(self, tool: str, result: Any) -> None:
        """Record a tool result in this agent's own result domain."""
        self.tool_results[tool] = result

    def record_cache(self, hit: bool) -> None:
        """Session-level cache accounting via the shared counter.

        All agents of the session share the same SessionCacheCounter, so
        counts accumulate across agent switches (reasonix-style).
        """
        if self.session_cache is None:
            self.session_cache = SessionCacheCounter()
        self.session_cache.record(hit)
