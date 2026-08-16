"""FX10 · HandoffEnvelope reserved type (PHASE-FIX §5 FX10).

Future multi-model handoff cannot smuggle transcripts into another
prefix. The type rejects history/thinking keys at the boundary so a
child prefix can never be rebuilt from the primary's chat history.

This card only reserves the type — no translator, no Coordinator wiring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class HandoffEnvelope:
    summary: str
    artifact_paths: tuple[str, ...]
    attachment_ids: tuple[str, ...]
    source_model: str
    target_model: str
    # 禁止字段：messages / history / thinking / reasoning_content / tool_calls

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HandoffEnvelope":
        """Build from a dict, rejecting any transcript-shaped key that
        would splice chat history into another prefix."""
        forbidden = {
            "messages",
            "history",
            "thinking",
            "reasoning_content",
            "tool_calls",
        }
        overlap = forbidden.intersection(payload)
        if overlap:
            bad = ", ".join(sorted(overlap))
            raise TypeError(
                f"HandoffEnvelope rejects transcript fields: {bad}"
            )
        missing = [
            name
            for name in ("summary", "artifact_paths", "attachment_ids",
                         "source_model", "target_model")
            if name not in payload
        ]
        if missing:
            raise TypeError(
                f"HandoffEnvelope missing required fields: {', '.join(missing)}"
            )
        return cls(
            summary=str(payload["summary"]),
            artifact_paths=tuple(payload["artifact_paths"]),
            attachment_ids=tuple(payload["attachment_ids"]),
            source_model=str(payload["source_model"]),
            target_model=str(payload["target_model"]),
        )
