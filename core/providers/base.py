"""Provider 策略层基类。

一个 Provider 描述"这一族模型和 OpenAI 默认行为有什么不同"，它**不持有
状态**——所有 provider 实例都是无状态单例，会被多个 Agent 并发使用。

新增 provider 的完整流程见
docs/plans/opus5-plan/PHASE-A-MODEL-ADAPTATION-LAYER.md §5。
"""

from __future__ import annotations

from typing import Any

try:
    from ...config.model_capabilities import (
        DEFAULT_CAPABILITIES,
        ModelCapabilities,
    )
except ImportError:  # pragma: no cover - repo-root layout (tests)
    from config.model_capabilities import DEFAULT_CAPABILITIES, ModelCapabilities


class BaseProvider:
    """默认实现 == Phase A 之前的 OpenAI 行为。

    子类只覆写真正有差异的方法。任何未被识别的模型都会落到 OpenAIProvider
    （它直接继承本类且不覆写任何东西），因此行为与改造前逐字节一致。
    """

    #: provider 标识，必须与 ModelCapabilities.provider 一致
    name: str = "openai"

    # ---- 识别 ----------------------------------------------------------

    def matches(self, base_url: str, model_name: str) -> bool:
        """本 provider 是否负责该模型。

        注册表按注册顺序询问，第一个返回 True 的胜出；全部返回 False 时
        落到 OpenAIProvider。
        """
        return False

    # ---- 能力 ----------------------------------------------------------

    def capabilities(self, model_config: dict) -> ModelCapabilities:
        """推导该模型的能力。

        子类应基于 DEFAULT_CAPABILITIES 做 dataclasses.replace()，
        不要从零构造，否则新增字段时会漏。
        """
        return DEFAULT_CAPABILITIES

    # ---- usage / reasoning 提取 ----------------------------------------

    def extract_cache_read(self, usage: dict, caps: ModelCapabilities) -> int:
        """从 usage 里取"命中前缀缓存的 token 数"。

        取代 core/agent_v2.py::_extract_cache_read 原先盲试两个字段的写法。
        """
        for key in caps.usage_fields.cache_read_flat:
            value = usage.get(key)
            if isinstance(value, int) and value >= 0:
                return value
        for outer, inner in caps.usage_fields.cache_read_nested:
            nested = usage.get(outer)
            if isinstance(nested, dict):
                value = nested.get(inner)
                if isinstance(value, int) and value >= 0:
                    return value
        return 0

    def extract_reasoning(self, payload: Any, caps: ModelCapabilities) -> str:
        """从 delta / message 里取推理内容。取代 _extract_reasoning。"""
        if not caps.supports_reasoning:
            return ""
        for key in caps.usage_fields.reasoning:
            value = _get_attr_or_key(payload, key)
            if isinstance(value, str) and value:
                return value
        return ""

    # ---- 构造参数 ------------------------------------------------------

    def llm_kwargs(self, model_config: dict, caps: ModelCapabilities) -> dict:
        """返回传给 ChatOpenAI 的关键字参数。

        Phase 3（M4）：真实请求路径由 ``agent_v2`` 强制走 resolver——构造层
        把 ``OutputLimitResolution.resolved_max_tokens`` 写入 ``model_config``，
        此处优先读取它。直接构造 LLM 的单元测试 / evals 场景可能不带
        resolved，此时按以下优先级：
        - ``resolved_max_tokens``（正整数）→ 请求解析值；
        - ``max_tokens``（正整数）→ 用户显式覆盖（等价 explicit_config）；
        - 否则 → ``UNKNOWN_MODEL_FALLBACK``（与 resolver 的 unknown_fallback
          数值一致，非历史 8192）。

        注意：这不是绕过 resolver——请求路径（agent_v2._raw_stream）只接受
        resolver 产出值；本方法的宽松分支仅服务直接构造场景。
        """
        from RxyCode.RxyCode1_1_0.config.model_limits import UNKNOWN_MODEL_FALLBACK

        resolved = model_config.get("resolved_max_tokens")
        if isinstance(resolved, int) and resolved > 0:
            max_tokens = resolved
        else:
            raw = model_config.get("max_tokens")
            if isinstance(raw, int) and raw > 0:
                max_tokens = raw
            else:
                max_tokens = UNKNOWN_MODEL_FALLBACK
        kwargs: dict[str, Any] = {
            "model": model_config.get("model_name", "gpt-4o"),
            "api_key": model_config.get("api_key"),
            "base_url": model_config.get("base_url"),
            "max_tokens": max_tokens,
            "max_retries": 3,
            "streaming": True,
            "stream_usage": True,
        }
        if caps.accepts_temperature:
            kwargs["temperature"] = model_config.get("temperature", 0.7)
        if caps.extra_body:
            kwargs["extra_body"] = dict(caps.extra_body)
        return kwargs

    def supports_prompt_cache(self, caps: ModelCapabilities) -> bool:
        """是否往消息上注入 cache_control。对应 agent_v2.py:411-441。"""
        return caps.supports_prompt_cache


def _get_attr_or_key(obj: Any, key: str) -> Any:
    """OpenAI SDK 的 delta 有时是对象、有时是 dict，两种都要能取。"""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)
