"""MIMO（小米 MiMo）provider（A16）。

端点与全部字段以 A0 批 6 调研报告（§7.6，2026-08-02 三方审计通过）为准。
主路径 = Chat Completions（https://api.xiaomimimo.com/v1）。

双主力（都须覆盖）：
  - mimo-v2.5-pro：万亿参数文本旗舰（vision=False，官方 X13 输入模态文本）
  - mimo-v2.5：原生全模态（文本+图像+视频+音频，vision=True，官方 X14）
共用：context 1M / max_output 128K（项目侧启发式，官方精确整数未找到）；
FC / reasoning / thinking_default_on=True / prompt_cache=True；
tokenizer "chars:1.5"（非官方启发式）。

已知公开线索（2026-08-01，mimo.xiaomi.com）：
  - MiMo-V2.5-Pro-UltraSpeed：1T 参数模型生成速度 1000 TPS（加速档位，独立 model id）
  - HySparse：KV Cache Sharing（缓存主题）
  - Hybrid SWA 推理优化（上下文窗口主题）

数值来源（A0 §7.6）：
  - https://mimo.mi.com/docs/zh-CN/quick-start/summary/model
  - https://mimo.mi.com/docs/zh-CN/api/chat/openai-api
  - https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/text-generation/deep-thinking
  - https://mimo.mi.com/docs/zh-CN/api/guidance/model-hyperparameters
  - https://mimo.mi.com/docs/zh-CN/price/pay-as-you-go
"""

from __future__ import annotations

from dataclasses import replace

try:
    from ...config.model_capabilities import (
        DEFAULT_CAPABILITIES,
        ModelCapabilities,
        ModelPricing,
        UsageFieldMap,
    )
except ImportError:  # pragma: no cover - repo-root layout (tests)
    from config.model_capabilities import (
        DEFAULT_CAPABILITIES,
        ModelCapabilities,
        ModelPricing,
        UsageFieldMap,
    )
from .base import BaseProvider

_MIMO_USAGE = UsageFieldMap(
    # §7.6 问 4：OpenAPI schema usage.prompt_tokens_details.cached_tokens（嵌套）
    cache_read_flat=(),
    cache_read_nested=(("prompt_tokens_details", "cached_tokens"),),
    # §7.6 问 4：缓存写入限时免费（无单价）→ cache_write_nested 清空
    cache_write_nested=(),
    # §7.6 问 5：usage 另有 completion_tokens_details.reasoning_tokens（§7.6 ③ 原文）
    reasoning_nested=(("completion_tokens_details", "reasoning_tokens"),),
    # reasoning_content 在 message/delta，不在 usage 内容字段
    reasoning=(),
)

# §7.6 问 2：官方表述「1M / 128K」，精确整数未找到 → 项目侧启发式（须注释）
_CONTEXT_WINDOW = 1_048_576
_MAX_OUTPUT = 131_072
# RxyCode 项目约定：compaction_threshold ≈ context 的 90%（同 A3 §7.1；非厂商文档数值）
_COMPACTION_RATIO = 0.9

# §7.6 问 7：定价按型号分条（CNY / 1M，国内按量；as_of=2026-08-02；source_url=X8）。
# cache_write 限时免费（精确单价未找到）→ None。
_MIMO_PRICING: dict[str, ModelPricing] = {
    "mimo-v2.5-pro": ModelPricing(
        input_per_mtok=3.00,
        output_per_mtok=6.00,
        cached_input_per_mtok=0.025,
        cache_write_per_mtok=None,
        as_of="2026-08-02",
        source_url="https://mimo.mi.com/docs/zh-CN/price/pay-as-you-go",
    ),
    "mimo-v2.5": ModelPricing(
        input_per_mtok=1.00,
        output_per_mtok=2.00,
        cached_input_per_mtok=0.02,
        cache_write_per_mtok=None,
        as_of="2026-08-02",
        source_url="https://mimo.mi.com/docs/zh-CN/price/pay-as-you-go",
    ),
    "mimo-v2.5-pro-ultraspeed": ModelPricing(
        input_per_mtok=9.0,
        output_per_mtok=18.0,
        cached_input_per_mtok=0.075,
        cache_write_per_mtok=None,
        as_of="2026-08-02",
        source_url="https://mimo.mi.com/docs/zh-CN/price/pay-as-you-go",
    ),
}

#: 未调研型号 → 价格显式 None（来源 URL 仍在），不得静默当 0。
_DEFAULT_MIMO_PRICING = ModelPricing(
    input_per_mtok=None,
    output_per_mtok=None,
    cached_input_per_mtok=None,
    cache_write_per_mtok=None,
    as_of="2026-08-02",
    source_url="https://mimo.mi.com/docs/zh-CN/price/pay-as-you-go",
)

#: 调研覆盖的型号（§7.6 问 1/③）。mimo-v2.5 为全模态主力 B，不得省略。
_MIMO_FAMILY = {
    "mimo-v2.5-pro",
    "mimo-v2.5",
    "mimo-v2.5-pro-ultraspeed",
}


def _family(model_name: str) -> str | None:
    """返回调研覆盖的型号规范名；未覆盖返回 None。"""
    name = model_name.lower().replace(" ", "")
    if name in _MIMO_FAMILY:
        return name
    return None


def _is_v25_multimodal(family: str) -> bool:
    return family == "mimo-v2.5"


def _pricing_for(family: str | None) -> ModelPricing:
    if family is None:
        return _DEFAULT_MIMO_PRICING
    return _MIMO_PRICING[family]


def _prompt_variant(model_name: str) -> str:
    # 未调研变体保持 DEFAULT_CAPABILITIES.prompt_variant（"default"），与 A12–A15 一致
    family = _family(model_name)
    return family if family is not None else "default"


class MIMOProvider(BaseProvider):
    name = "mimo"

    def matches(self, base_url: str, model_name: str) -> bool:
        url = base_url.lower()
        name = model_name.lower()
        # §7.6 ③：xiaomimimo / mimo.mi.com url，或模型名以 mimo- 开头 → 命中。
        # 勿用宽泛 "mimo" in url——第三方网关路径含 mimo 字样会误伤（A16 卡常见坑）。
        # §7.6 ③ 仅认 mimo- 前缀（不含 mimo_v）。
        if "xiaomimimo" in url or "mimo.mi.com" in url:
            return True
        return name.startswith("mimo-")

    def capabilities(self, model_config: dict) -> ModelCapabilities:
        model_name = str(model_config.get("model_name") or "").lower()
        family = _family(model_name)

        caps = replace(
            DEFAULT_CAPABILITIES,
            provider=self.name,
            usage_fields=_MIMO_USAGE,
            pricing=_pricing_for(family),
            prompt_variant=_prompt_variant(model_name),
        )
        if family is not None:
            caps = replace(
                caps,
                # §7.6 问 2：1M/128K 项目侧启发式（官方精确整数未找到）
                context_window=_CONTEXT_WINDOW,
                compaction_threshold=int(_CONTEXT_WINDOW * _COMPACTION_RATIO),
                max_output_tokens=_MAX_OUTPUT,
                supports_function_calling=True,
                # §7.6 ③：v2.5-pro 文本（X13）；v2.5 原生全模态（X14）
                supports_vision=_is_v25_multimodal(family),
                supports_reasoning=True,
                # §7.6 问 5：Chat 两型号深度思考默认开启（X5）
                thinking_default_on=True,
                supports_prompt_cache=True,
                # §7.6 ③ 骨架未列 structured_output 专属值；按 A12–A15 裁决保留
                # function_calling（StructuredOutputMode 仅支持该值与 json_in_text）
                structured_output="function_calling",
                prompt_variant=_prompt_variant(model_name),
                # §7.6 问 5：思考模式 temperature/top_p 强制 1.0/0.95（X5/X6），
                # 不接受自定义采样参数 → 不传 temperature
                accepts_temperature=False,
                # §7.6 问 6：官方 tokenizer 未找到 → chars:1.5 非官方启发式
                tokenizer="chars:1.5",
                # §7.6 ③：Chat 路径无 reasoning.effort → 不设 effort_presets
                effort_presets={},
                # §7.6 问 4：隐式 Prompt Cache，最小块/TTL 未找到 → None；无显式断点
                cache_min_block_tokens=None,
                cache_ttl_s=None,
                cache_breakpoints=(),
            )
        return caps.merged_with_overrides(model_config)

    def llm_kwargs(self, model_config: dict, caps: ModelCapabilities) -> dict:
        kwargs = super().llm_kwargs(model_config, caps)
        # §7.6 ③：Chat thinking 经 extra_body={"thinking": {"type": "enabled"|"disabled"}}。
        # A16 仅接线 Chat 路径；Responses 的 reasoning.effort 差异由 A21 处理。
        if caps.supports_reasoning and caps.thinking_default_on:
            body = kwargs.setdefault("extra_body", {})
            body.setdefault("thinking", {"type": "enabled"})
        return kwargs
