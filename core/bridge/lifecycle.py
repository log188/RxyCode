"""B10: 桥接生命周期编排 —— run_official_agent（工具入口）。

spawn → 任务注入 → 流式接收 → 超时/预算控制 → kill。
- 时间预算：asyncio.timeout 兜底（超时即 kill）；
- token 预算：事件流中累计 usage（B9 归一化），超限即 kill；
- 结果截断：回流主 harness 的摘要 ≤ max_result_chars（1-2K token）。
"""

from __future__ import annotations

import asyncio

from .base import AgentBridge

#: 结果摘要硬上限（luna R1-5：调用方传任意大值也不突破 1-2K token 语义）。
MAX_RESULT_CHARS_HARD_LIMIT = 4000

def _event_token_cost(ev: dict) -> int:
    """从事件里提取 token 消耗（ACP 格式 usage 在 content.params 内）。

    B10 限制性规范 6 + luna R1: usage 按 B9 usage_fields 语义归一化——
    优先单一权威字段（input_tokens/output_tokens），避免同义字段
    （input 与 input_tokens 并存）重复计数。
    """
    usage = ev.get("usage")
    if not isinstance(usage, dict):
        content = ev.get("content")
        if isinstance(content, dict):
            usage = content.get("usage")
    if isinstance(usage, dict):
        # 单一权威字段优先（OpenAI 系 input_tokens/output_tokens）
        for key in ("input_tokens", "output_tokens", "prompt_tokens",
                    "completion_tokens"):
            value = usage.get(key)
            if isinstance(value, int) and value >= 0:
                return value
        # 无权威字段时用 total（不与其他字段叠加）
        total = usage.get("total")
        if isinstance(total, int) and total >= 0:
            return total
        # 兜底：input 或 output 单取其一（不叠加，luna R1-4 防重复计数）
        for key in ("input", "output"):
            value = usage.get(key)
            if isinstance(value, int) and value >= 0:
                return value
    content = ev.get("content")
    if isinstance(content, dict):
        content = content.get("text") or ""
    if isinstance(content, str):
        return max(1, len(content) // 4)  # 粗略字符/token 估算
    return 1


async def run_official_agent(bridge: AgentBridge, task: str) -> str:
    """工具注册入口：run_official_agent（白名单默认禁用，由调用方门控）。

    返回结果摘要（≤ cfg.max_result_chars）；超时/超预算返回明确提示。
    """
    await bridge.start()
    chunks: list[str] = []
    total_tokens = 0
    try:
        async with asyncio.timeout(bridge.cfg.time_budget_s):
            async for ev in bridge.invoke(task):
                ev_type = ev.get("type") or ""
                # token 预算监控（B9 usage 归一化路径）
                total_tokens += _event_token_cost(ev)
                if total_tokens > bridge.cfg.token_budget:
                    return "[bridge] token budget exceeded; process killed"
                if ev_type == "result":
                    content = ev.get("content") or ""
                    if isinstance(content, str):
                        chunks.append(content)
                    break
                elif ev_type in ("agent_message_chunk", "agent_thought_chunk"):
                    content = ev.get("content")
                    if isinstance(content, dict):
                        content = content.get("text") or ""
                    if isinstance(content, str) and content:
                        chunks.append(content)
    except TimeoutError:
        return "[bridge] time budget exceeded; process killed"
    finally:
        await bridge.stop()
    summary = "\n".join(chunks)
    # luna R1-5: 结果摘要硬上限（调用方 max_result_chars 可调小，不可放大）。
    return summary[: min(bridge.cfg.max_result_chars, MAX_RESULT_CHARS_HARD_LIMIT)]
