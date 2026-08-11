"""B10: 单 agent 桥接抽象基类与成本控制配置。

桥接 = 官方 agent CLI 作为旁路子进程运行（官方 prompt 原样运行，不重写）。
每个桥接 agent 独立 session / 独立前缀 / lineage-only（不复制主历史），
结果摘要 ≤1-2K token 回流主 harness（主链路前缀零污染）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class BridgeConfig:
    """成本控制：token 预算 + 时间预算 + 结果截断，全部可配。"""

    token_budget: int = 50_000      # 超出即 kill
    time_budget_s: float = 300.0    # 超时 kill（asyncio.timeout 兜底）
    max_result_chars: int = 2000    # 回流主 harness 的摘要上限（1-2K token）
    provider: str = ""              # 桥接 agent 的 provider（B9 契约查询）
    model: str = ""                 # 桥接 agent 的模型（B9 契约查询）


class AgentBridge(ABC):
    """单 agent 桥接抽象基类：spawn → 任务注入 → 流式事件 → kill。"""

    def __init__(self, cfg: BridgeConfig) -> None:
        self.cfg = cfg

    @abstractmethod
    async def start(self) -> None:
        """spawn 子进程并完成 ACP/CLI 握手。"""

    @abstractmethod
    def invoke(self, task: str) -> AsyncIterator[dict]:
        """流式产出 agent_message_chunk/agent_thought_chunk/tool_call/plan/result。"""

    @abstractmethod
    async def stop(self) -> None:
        """超时/预算超限时 kill 并回收审计输出。"""

    @abstractmethod
    def usage(self) -> dict:
        """本桥接的 usage；各家字段按 B9 契约归一化。"""
