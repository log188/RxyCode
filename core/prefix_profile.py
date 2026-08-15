"""FX1 · frozen prefix identity (PHASE-FIX §5 FX1).

Type-only card: a chat/agent prefix archive gets a stable identity string so
prewarm, keepalive and real turns can be checked for isomorphism before we
touch AgentV2 routing. No network, no AgentV2 behaviour change.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, Optional


PrefixKind = Literal["chat", "agent"]


def digest_tools(tools: Optional[list[Any]]) -> str:
    """Canonical sha256 of tool schemas. Order-insensitive by name then json."""
    items = list(tools or [])
    normalized = []
    for item in items:
        if hasattr(item, "name") and hasattr(item, "args_schema"):
            name = str(item.name)
            schema = item.args_schema or {}
            if hasattr(schema, "model_json_schema"):
                schema = schema.model_json_schema()
            normalized.append({"name": name, "parameters": schema})
        elif isinstance(item, dict):
            normalized.append(
                {
                    "name": str(
                        item.get("name")
                        or item.get("function", {}).get("name")
                        or ""
                    ),
                    "parameters": item.get("parameters")
                    or item.get("function", {}).get("parameters")
                    or {},
                }
            )
        else:
            normalized.append({"name": str(item), "parameters": {}})
    normalized.sort(key=lambda x: x["name"])
    blob = json.dumps(
        normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PrefixProfile:
    kind: PrefixKind
    session_id: str
    provider: str
    model: str
    thinking_enabled: bool
    thinking_effort: Optional[str]
    tools_digest: str
    s1_digest: str
    system_template_version: str
    prompt_variant: str
    agent_id: Optional[str] = None
    cache_mode: Optional[str] = None

    def identity(self) -> str:
        """Stable identity string; different identity = different prefix.

        Field order is fixed:
        provider|model|kind|thinking|effort|tools_digest|s1_digest|
        session_id|agent_id|prompt_variant.  ``agent_id`` None renders ``-``.
        """
        effort = self.thinking_effort or "-"
        agent = self.agent_id or "-"
        thinking = "on" if self.thinking_enabled else "off"
        return "|".join(
            [
                self.provider,
                self.model,
                self.kind,
                thinking,
                effort,
                self.tools_digest,
                self.s1_digest,
                self.session_id,
                agent,
                self.prompt_variant,
            ]
        )


def profiles_compatible(left: PrefixProfile, right: PrefixProfile) -> bool:
    """Two profiles are the same prefix iff their identities are identical."""
    return left.identity() == right.identity()
