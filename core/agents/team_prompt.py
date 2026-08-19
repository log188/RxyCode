"""F17 team system prompt: cached public prefix + uncached role suffix."""

from __future__ import annotations

TEAM_CHARTER = (
    "协作规则：成员不得直连，所有跨成员通信经团长；产出写文件；"
    "机械验证先于 LLM 审计；不得创建子团队。"
)

CACHE_BREAK_MARK = "\n<CACHE_BREAK>\n"


def assemble_member_prompt(
    *,
    tools_block: str,
    task_context: str,
    role_prompt: str,
    private_history: str = "",
    charter: str = TEAM_CHARTER,
) -> tuple[str, str]:
    """Return (cached_prefix, uncached_suffix). Prefix must be byte-stable."""
    cached = "\n".join(
        (
            tools_block.strip(),
            charter,
            task_context.strip(),
        )
    )
    uncached = "\n".join(part for part in (role_prompt.strip(), private_history.strip()) if part)
    return cached, uncached


def render_member_prompt(cached: str, uncached: str) -> str:
    return f"{cached}{CACHE_BREAK_MARK}{uncached}"


def compact_summary(text: str, *, limit: int = 400) -> str:
    """TaskResult.summary / board entries stay short; artifacts hold the rest."""
    if len(text) <= limit:
        return text
    return text[:limit] + "…"
