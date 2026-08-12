"""Request-local, user-safe recovery lifecycle tracking.

The tracker deliberately stores only operational summaries.  It never carries
model chain-of-thought or raw secret-bearing tool arguments to the protocol
client.  ``ProtocolTui`` adapts the generic lifecycle records to the wire
notification models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Callable
from uuid import uuid4


class RecoveryState(StrEnum):
    IDLE = "idle"
    DETECTED = "detected"
    ANALYZING = "analyzing"
    RETRYING = "retrying"
    RECOVERED = "recovered"
    EXHAUSTED = "exhausted"


class RecoveryKind(StrEnum):
    TRANSPORT_RETRY = "transport_retry"
    MODEL_RECOVERY = "model_recovery"
    GRAPH_REPLAN = "graph_replan"


@dataclass
class RecoveryRecord:
    recovery_id: str
    source_call_id: str
    recovery_kind: RecoveryKind
    error_kind: str
    max_attempts: int
    attempts: int = 0
    state: RecoveryState = RecoveryState.DETECTED
    strategies: list[str] = field(default_factory=list)


class RecoveryTracker:
    """A small state machine scoped to one prompt request.

    ``on_event`` receives plain dictionaries to keep this layer independent of
    the protocol package.  Every emitted record contains a monotonic ``seq``
    and an event id so reconnecting clients can order and de-duplicate it.
    """

    def __init__(self, on_event: Callable[[dict[str, Any]], None] | None = None) -> None:
        self._on_event = on_event
        self._seq = 0
        self._active: RecoveryRecord | None = None
        self._state = RecoveryState.IDLE

    @property
    def state(self) -> RecoveryState:
        return self._state

    @property
    def active(self) -> RecoveryRecord | None:
        return self._active

    @property
    def sequence(self) -> int:
        return self._seq

    def _emit(self, kind: str, **payload: Any) -> dict[str, Any]:
        self._seq += 1
        event = {
            "kind": kind,
            "event_id": uuid4().hex,
            "seq": self._seq,
            "timestamp": datetime.now(UTC).isoformat(),
            **payload,
        }
        if self._on_event is not None:
            self._on_event(event)
        return event

    def detect(
        self,
        *,
        source_call_id: str,
        recovery_kind: RecoveryKind | str,
        error_kind: str,
        max_attempts: int,
        run_id: str | None = None,
    ) -> RecoveryRecord:
        """Start or reuse the recovery for the failed source call."""
        if self._active is not None:
            return self._active
        record = RecoveryRecord(
            recovery_id=uuid4().hex,
            source_call_id=str(source_call_id),
            recovery_kind=RecoveryKind(recovery_kind),
            error_kind=str(error_kind),
            max_attempts=max(1, int(max_attempts)),
        )
        self._active = record
        self._state = record.state
        self._emit(
            "started",
            recovery_id=record.recovery_id,
            source_call_id=record.source_call_id,
            recovery_kind=record.recovery_kind.value,
            error_kind=record.error_kind,
            max_attempts=record.max_attempts,
            run_id=run_id,
        )
        return record

    def analyze(self, recovery_id: str) -> None:
        record = self._require(recovery_id)
        record.state = RecoveryState.ANALYZING
        self._state = record.state
        self._emit("analyzing", recovery_id=record.recovery_id)

    def attempt(
        self,
        recovery_id: str,
        *,
        attempt: int | None = None,
        strategy: str,
        replacement_call_id: str | None = None,
        display_summary: str,
    ) -> None:
        record = self._require(recovery_id)
        record.attempts = max(record.attempts + 1, int(attempt or 0))
        record.strategies.append(str(strategy))
        record.state = RecoveryState.RETRYING
        self._state = record.state
        self._emit(
            "attempt",
            recovery_id=record.recovery_id,
            attempt=record.attempts,
            strategy=str(strategy),
            replacement_call_id=replacement_call_id,
            display_summary=str(display_summary),
        )

    def resolve(self, recovery_id: str, *, attempts: int | None = None, display_summary: str) -> None:
        record = self._require(recovery_id)
        if attempts is not None:
            record.attempts = max(record.attempts, int(attempts))
        record.state = RecoveryState.RECOVERED
        self._state = record.state
        self._emit(
            "resolved",
            recovery_id=record.recovery_id,
            attempts=record.attempts,
            display_summary=str(display_summary),
        )
        self._active = None

    def exhaust(self, recovery_id: str, *, attempts: int | None = None, final_error: str) -> None:
        record = self._require(recovery_id)
        if attempts is not None:
            record.attempts = max(record.attempts, int(attempts))
        record.state = RecoveryState.EXHAUSTED
        self._state = record.state
        self._emit(
            "exhausted",
            recovery_id=record.recovery_id,
            attempts=record.attempts,
            final_error=str(final_error),
        )
        self._active = None

    def _require(self, recovery_id: str) -> RecoveryRecord:
        record = self._active
        if record is None or record.recovery_id != recovery_id:
            raise KeyError(f"unknown recovery id: {recovery_id}")
        return record
