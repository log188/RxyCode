"""Phase E · E1 — append-only EventBus for the multi-agent runtime.

Every session worker process owns one EventBus (process-local singleton;
sessions stay isolated per the PHASE-C worker model).  Agents publish
``BusEvent`` records; subscribers match by ``pattern``; the event log is
append-only with a rolling retention window; ``replay`` is a paged iterator
over the log (OpenHands ``resend`` semantics).

Routing metadata: events may carry ``send_to`` (exact agent delivery) and
``cause_by`` (origin) tags; a routed event with no matching subscriber is
dead-lettered (telemetry only, the publisher is never blocked).  See
PHASE-E §4.1 / §5 E1.
"""

from __future__ import annotations

import asyncio
import copy
import itertools
import logging
import os
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

#: Hard contract: events must never carry large payloads (PHASE-E EB8).
MAX_PAYLOAD_BYTES = 64 * 1024

#: Append-only log defaults (PHASE-E §7): roll by count or bytes, first hit.
DEFAULT_LOG_MAX_ENTRIES = 100_000
DEFAULT_LOG_MAX_BYTES = 64 * 1024 * 1024


class ReplayUnavailableError(RuntimeError):
    """Raised when ``replay`` cannot serve the requested window.

    Either the log is disabled (``RXYCODE_EVENTBUS_LOG=0``) or the requested
    ``after_seq`` predates the log rollover point.
    """


@dataclass
class BusEvent:
    """Minimal runtime event carried by the bus.

    The protocol-layer ``BusEvent`` (Phase E4, ``protocol/``) will carry the
    ten frozen ``event/agent_*`` methods; this runtime object exposes the
    fields the bus itself needs.  ``seq`` is assigned by the bus on publish
    (append-only order credential).
    """

    method: str
    session_id: str
    agent_id: str
    payload: dict[str, Any]
    run_id: str | None = None
    send_to: str | None = None
    cause_by: str | None = None
    seq: int = 0


@dataclass
class Sub:
    """A single subscription (subscriber label, pattern, delivery queue)."""

    subscriber: str
    pattern: str
    queue: asyncio.Queue[BusEvent] = field(
        default_factory=lambda: asyncio.Queue(1024)
    )
    dropped: bool = False


def eventbus_log_enabled() -> bool:
    """``RXYCODE_EVENTBUS_LOG``: 0 disables the event log (debug, no replay)."""
    return os.environ.get("RXYCODE_EVENTBUS_LOG", "1") != "0"


class AppendOnlyLog:
    """In-memory append-only event log with a rolling retention window.

    Events are appended in arrival order and never mutated (PHASE-E EB6).
    The window rolls by entry count (default 100k) or approximate byte size
    (default 64MB), whichever hits first; ``seq`` values never rewind — old
    entries are dropped, never renumbered.  When ``persist`` is False
    (``RXYCODE_EVENTBUS_LOG=0``) nothing is retained and ``iter_from`` is
    unavailable.
    """

    def __init__(
        self,
        max_entries: int = DEFAULT_LOG_MAX_ENTRIES,
        max_bytes: int = DEFAULT_LOG_MAX_BYTES,
        persist: bool | None = None,
    ) -> None:
        self._max_entries = max(1, int(max_entries))
        self._max_bytes = max(1, int(max_bytes))
        if persist is None:
            persist = eventbus_log_enabled()
        self._persist = persist
        self._entries: deque[BusEvent] = deque()
        self._bytes = 0

    @property
    def persist(self) -> bool:
        return self._persist

    @property
    def earliest_seq(self) -> int:
        """Seq of the oldest retained entry; 0 when the log is empty."""
        if not self._entries:
            return 0
        return self._entries[0].seq

    async def append(self, event: BusEvent) -> None:
        """Persist the event (retaining the rollover window).

        EB6: the stored record is a deep copy — the publisher may keep
        mutating its own object afterwards, the log fact never changes.
        """
        if not self._persist:
            return
        snapshot = copy.deepcopy(event)
        self._entries.append(snapshot)
        self._bytes += _approx_size(snapshot)
        while self._should_roll():
            removed = self._entries.popleft()
            self._bytes = max(0, self._bytes - _approx_size(removed))

    def _should_roll(self) -> bool:
        if len(self._entries) > self._max_entries:
            return True
        return self._bytes > self._max_bytes and len(self._entries) > 1

    async def iter_from(
        self, after_seq: int, page_size: int = 200
    ) -> AsyncIterator[BusEvent]:
        """Yield retained events with ``seq > after_seq`` in paged batches.

        Raises ``ReplayUnavailableError`` when the log is disabled or
        ``after_seq`` predates the rollover point.
        """
        if not self._persist:
            raise ReplayUnavailableError(
                "event log disabled (RXYCODE_EVENTBUS_LOG=0); replay unavailable"
            )
        if not self._entries:
            return
        first = self._entries[0].seq
        if after_seq < first - 1:
            raise ReplayUnavailableError(
                f"seq {after_seq} predates log rollover point (earliest {first})"
            )
        page: list[BusEvent] = []
        for event in self._entries:
            if event.seq <= after_seq:
                continue
            page.append(event)
            if len(page) >= page_size:
                for item in page:
                    yield item
                page = []
        if page:
            for item in page:
                yield item


def _approx_size(event: BusEvent) -> int:
    """Cheap byte estimate for rollover budgeting (not exact serialization)."""
    return (
        len(event.method)
        + len(event.session_id)
        + len(event.agent_id)
        + len(str(event.payload))
        + 64
    )


class EventBus:
    """Process-local append-only event bus (PHASE-E §4.1).

    Single subscriber list, lock-serialized publish (seq → log → notify stays
    atomic), slow subscribers are dropped with telemetry (never block the
    publisher), replay is a paged iterator.
    """

    def __init__(self, log: AppendOnlyLog) -> None:
        self._log = log
        self._seq = itertools.count(1)
        self._subs: list[Sub] = []
        self._publish_lock = asyncio.Lock()

    @property
    def log(self) -> AppendOnlyLog:
        return self._log

    @staticmethod
    def _match(pattern: str, agent_id: str, method: str) -> bool:
        """Three-segment pattern matching (PHASE-E §4.1).

        ``event/*`` matches everything; ``agent/<id>/*`` matches one agent;
        ``agent/<id>/<name>`` matches one agent and the exact method tail
        (``*`` is only allowed as the last segment).
        """
        if pattern == "event/*":
            return True
        if pattern.startswith("agent/"):
            parts = pattern.split("/")
            if len(parts) != 3 or parts[1] != agent_id:
                return False
            if parts[2] == "*":
                return True
            return method.split("/")[-1] == parts[2]
        return False

    async def subscribe(self, subscriber: str, pattern: str) -> Sub:
        sub = Sub(subscriber=subscriber, pattern=pattern)
        self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Sub) -> None:
        if sub in self._subs:
            self._subs.remove(sub)

    async def publish(self, event: BusEvent) -> None:
        """Serialized publish: seq → log → notify inside one lock (EB6).

        Routing: ``send_to`` set and not ``*`` delivers only to subscriptions
        that match the target agent; a routed event with no matching
        subscription is dead-lettered with telemetry, never blocking.

        EB8: the event bus is a control plane — oversized payloads are
        rejected (data plane must go through explicit delegation), so a
        contract breach fails loudly instead of growing the log silently.
        """
        if len(str(event.payload)) > MAX_PAYLOAD_BYTES:
            raise ValueError(
                f"event payload exceeds {MAX_PAYLOAD_BYTES} bytes (EB8: "
                "data plane must use explicit delegation, not bus events)"
            )
        async with self._publish_lock:
            event.seq = next(self._seq)
            await self._log.append(event)
            self._deliver(event)
            if (
                event.send_to is not None
                and event.send_to != "*"
                and not self._has_target_subscriber(event.send_to)
            ):
                _logger.warning(
                    "eventbus dead-letter: %s -> %s has no target subscriber (seq=%d)",
                    event.method,
                    event.send_to,
                    event.seq,
                )

    def _has_target_subscriber(self, target_id: str) -> bool:
        """Whether any subscription targets *target_id* (agent/<id>/*).

        A routed event with no target subscriber is dead-lettered even when
        a monitor holds an ``event/*`` subscription: the monitor is not a
        receiver, it only observes (PHASE-E §5 E1 routing metadata).
        """
        return any(
            sub.pattern == f"agent/{target_id}/*"
            or (
                sub.pattern.startswith(f"agent/{target_id}/")
                and len(sub.pattern.split("/")) == 3
            )
            for sub in self._subs
        )

    def _deliver(self, event: BusEvent) -> bool:
        """Fan out to matching subscriptions; returns whether anyone matched.

        Routed events (``send_to`` set and not ``*``) are delivered against
        the *target* agent id; broadcast events match by the event's own
        ``agent_id``.
        """
        routed = event.send_to is not None and event.send_to != "*"
        target_id = event.send_to if routed else event.agent_id
        matched_any = False
        for sub in list(self._subs):
            if not self._match(sub.pattern, target_id, event.method):
                continue
            matched_any = True
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                sub.dropped = True
                _logger.warning(
                    "eventbus drop: subscriber %r (pattern=%r) queue full, "
                    "seq=%d",
                    sub.subscriber,
                    sub.pattern,
                    event.seq,
                )
            except Exception as exc:  # noqa: BLE001 - subscriber bug never kills publisher
                _logger.error("eventbus subscriber error: %r", exc)
        return matched_any

    async def replay(
        self, after_seq: int, page_size: int = 200
    ) -> AsyncIterator[BusEvent]:
        """Replay retained events by seq (paged; OpenHands resend semantics)."""
        async for event in self._log.iter_from(after_seq, page_size):
            yield event
