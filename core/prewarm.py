"""FX4 · isomorphic prewarm archives (PHASE-FIX §5 FX4).

Two archive slots per session_id: a chat Profile (no tools, thinking off)
and an agent Profile (core tools, thinking on). Prewarm must write the
same tools/thinking/system bytes as the real turn of that slot so a
greeting no longer misses a tools-on warmup prefix.
"""

from __future__ import annotations

import asyncio
from typing import Any

from RxyCode.RxyCode1_1_0.core.cache_policy import build_prewarm_signature
from RxyCode.RxyCode1_1_0.core.prefix_profile import digest_tools

PrewarmKind = str  # "chat" | "agent"

#: Serializes the temporary _capabilities swap so the chat slot (thinking
#: off) and the agent slot (thinking on) never race on the shared agent.
_PREWARM_CAPS_LOCK = asyncio.Lock()


def _mcp_signature(agent: Any) -> str:
    import json

    try:
        cfg = getattr(agent, "_cfg", None) or {}
        servers = cfg.get("mcpServers") or {}
        if not servers:
            return ""
        return json.dumps(
            servers,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except Exception:  # pragma: no cover - config shape varies
        return ""


def core_tools_for(agent: Any, kind: PrewarmKind):
    """Tools bound to the prewarm request: core tools for agent slot, None
    for chat slot (matches the real turn of each archive)."""
    if kind != "agent":
        return None
    fn = getattr(agent, "_get_core_tools", None)
    if fn is None:
        return None
    return fn()


def prewarm_signature(agent: Any, kind: PrewarmKind = "agent") -> str:
    """Signature for one archive slot: model/cwd/mcp/kind/thinking/tools."""
    model = str((getattr(agent, "model_config", {}) or {}).get("model_name") or "")
    cwd = str(getattr(agent, "_workspace_root", "") or "")
    tools = core_tools_for(agent, kind)
    return build_prewarm_signature(
        model=model,
        cwd=cwd,
        mcp=_mcp_signature(agent),
        kind=kind,
        thinking_enabled=kind == "agent",
        tools_digest=digest_tools(tools),
    )


def session_prewarm_messages(agent: Any, kind: PrewarmKind = "agent") -> list:
    """Prewarm messages for one slot: system matches the real turn's
    tools/thinking shape; user text is fixed to ``warm``."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from RxyCode.RxyCode1_1_0.core.prompts.registry import get_system_prompt

    variant = "default"
    fn = getattr(agent, "_prompt_variant", None)
    if fn is not None:
        try:
            variant = fn()
        except Exception:  # pragma: no cover
            variant = "default"
    system = ""
    try:
        system = get_system_prompt(variant=variant, tools=kind == "agent")
    except Exception:  # pragma: no cover
        system = ""
    msgs: list = []
    if system:
        msgs.append(SystemMessage(content=system))
    msgs.append(HumanMessage(content="warm"))
    return msgs


def keepalive_messages(agent: Any) -> list:
    """FX5: keep-alive rides the frozen agent archive — same system + core
    tools as the agent prewarm slot, user text ``keep-alive``. Never a
    bare HumanMessage body (that would be a third prefix)."""
    from langchain_core.messages import HumanMessage

    msgs = session_prewarm_messages(agent, "agent")
    out: list = []
    for m in msgs:
        if m.__class__.__name__ == "HumanMessage":
            out.append(HumanMessage(content="keep-alive"))
        else:
            out.append(m)
    return out


async def prewarm_archive(agent: Any, kind: PrewarmKind) -> None:
    """Send one max_tokens=1 prewarm request for one slot and consume the
    stream fully (provider writes the prefix); confirm via the agent.

    Thinking is applied exactly like the real turn: the chat slot sets
    ``_thinking_disabled_this_turn`` (the same switch the greeting path
    uses, so extended thinking is turned off at the payload layer), the
    agent slot leaves it on. Both slots share one agent, so the swap is
    serialized by a lock.
    """
    raw_stream = getattr(agent, "_raw_stream", None)
    if raw_stream is None:
        return
    msgs = session_prewarm_messages(agent, kind)
    tools = core_tools_for(agent, kind)
    was_disabled = bool(getattr(agent, "_thinking_disabled_this_turn", False))
    async with _PREWARM_CAPS_LOCK:
        agent._thinking_disabled_this_turn = kind != "agent"
        try:
            async for _chunk in raw_stream(
                msgs,
                tools=tools,
                max_tokens=1,
            ):
                pass  # full consumption (do not break early)
        finally:
            agent._thinking_disabled_this_turn = was_disabled
    confirm = getattr(agent, "_confirm_prewarm", None)
    if confirm is not None:
        confirm(kind)


async def prewarm_all(agent: Any) -> None:
    """Warm both archive slots in parallel (chat + agent)."""
    await asyncio.gather(
        prewarm_archive(agent, "chat"),
        prewarm_archive(agent, "agent"),
    )
