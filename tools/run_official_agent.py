"""B10: run_official_agent 工具（官方 agent CLI 桥接，白名单默认禁用）。

作为旁路子进程运行官方 agent（官方 prompt 原样运行，不重写）。
独立 session / lineage-only / 结果摘要 ≤1-2K token 回流（主链路前缀零污染）。
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class _RunOfficialAgentInput(BaseModel):
    """工具参数 schema（pydantic）。"""

    agent: str = Field(description="agent 名：claude / grok")
    task: str = Field(description="委托给官方 agent 的任务描述")
    time_budget_s: float = Field(default=180.0, description="时间预算（秒），超时 kill")
    max_result_chars: int = Field(default=2000, description="结果摘要上限（字符）")


async def _run_official_agent_impl(
    agent: str,
    task: str,
    *,
    time_budget_s: float = 180.0,
    max_result_chars: int = 2000,
) -> str:
    """执行官方 agent 桥接（agent 名 → 适配器）。"""
    from RxyCode.RxyCode1_1_0.core.bridge.base import BridgeConfig
    from RxyCode.RxyCode1_1_0.core.bridge.lifecycle import run_official_agent

    cfg = BridgeConfig(
        time_budget_s=max(1.0, float(time_budget_s)),
        max_result_chars=min(
            max(100, int(max_result_chars)),
            4000,  # luna R1-5: 硬上限（1-2K token 语义）
        ),
    )
    agent_name = (agent or "").strip().lower()
    if agent_name in ("claude", "claude-code"):
        from RxyCode.RxyCode1_1_0.core.bridge.acp import ACPBridge

        bridge = ACPBridge(cfg=cfg)
    elif agent_name in ("grok", "grok-build"):
        from RxyCode.RxyCode1_1_0.core.bridge.cli import CLIBridge

        bridge = CLIBridge(cfg=cfg, cmd=["grok", "agent", "stdio"])
    else:
        return f"[bridge] unknown agent {agent!r}; supported: claude, grok"
    return await run_official_agent(bridge, task)


def run_official_agent_tool() -> StructuredTool:
    """构造 run_official_agent 工具（DANGER 风险：执行外部 CLI）。"""
    return StructuredTool(
        name="run_official_agent",
        description=(
            "在旁路子进程中运行官方 agent CLI（claude / grok-build）处理子任务。"
            "独立 session，lineage-only，结果摘要回流（≤2K token）。"
            "默认禁用，需显式配置开启。"
        ),
        func=_run_official_agent_impl,
        args_schema=_RunOfficialAgentInput,
        handle_tool_error=True,
    )
