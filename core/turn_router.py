"""单回合决策单元。禁止在 AgentV2._run_impl 里书写第二层 if。

FX2：把 _run_impl 的 ~8 层 if 瀑布等价抽成一张路由表，后续卡（FX3
skip_await、FX6 ChatPrefix 扩展）只改这一处。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from RxyCode.RxyCode1_1_0.core.prefix_profile import PrefixKind
from RxyCode.RxyCode1_1_0.core.request_routing import (
    PURE_SOCIAL_GREETING_RE,
    RoutingDirective,
    declines_tools,
    is_social_chat,
)

TurnPath = Literal["chat", "agent", "graph", "plan", "compose", "file_op", "download"]


@dataclass(frozen=True, slots=True)
class TurnDecision:
    path: TurnPath
    profile_kind: PrefixKind
    skip_await: frozenset[str]
    thinking_enabled: bool
    role_instruction: str = ""
    social: bool = False


def route(
    user_text: str,
    mode: str,
    directive: RoutingDirective,
    *,
    file_op: Optional[dict[str, Any]] = None,
    download: Optional[tuple] = None,
) -> TurnDecision:
    """Decide the fast path for one turn. Order matters: it mirrors the
    original ``AgentV2._run_impl`` waterfall 1:1 so outcomes are identical."""
    text = (user_text or "").strip()
    empty_skip: frozenset[str] = frozenset()
    chat_skip: frozenset[str] = frozenset(
        {"memory.initialize", "session.load", "mcp.refresh"}
    )

    if mode == "plan":
        return TurnDecision("plan", "agent", empty_skip, True)

    if file_op:
        return TurnDecision("file_op", "agent", empty_skip, True)

    if download:
        return TurnDecision("download", "agent", empty_skip, True)

    force_full = directive == RoutingDirective.FORCE_FULL
    social = is_social_chat(text)

    if mode in ("build", "plan") and not force_full and declines_tools(text):
        return TurnDecision("chat", "chat", chat_skip, False, social=social)

    if (
        mode in ("build", "plan")
        and not force_full
        and social
        and PURE_SOCIAL_GREETING_RE.match(text)
    ):
        return TurnDecision("chat", "chat", chat_skip, False, social=True)

    if mode == "compose" and social:
        return TurnDecision("agent", "agent", empty_skip, True, social=True)

    if mode in ("build", "plan") and not force_full:
        return TurnDecision("agent", "agent", empty_skip, True, social=social)

    if mode == "compose":
        return TurnDecision("compose", "agent", empty_skip, True)

    return TurnDecision("graph", "agent", empty_skip, True)
