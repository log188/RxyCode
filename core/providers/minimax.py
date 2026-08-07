"""MiniMax provider（A15，M2.x 系列 + M3）。

与 OpenAI 默认行为的差异以 A0 批 5 调研报告（§7.5，2026-08-02 三方审计通过）为准：
  - 缓存命中字段：``usage.prompt_tokens_details.cached_tokens``（嵌套路径，非平铺）
  - reasoning 内容在 message/delta 层（reasoning_split=true 时含 reasoning_details；
    非 usage 嵌套字段）
  - MiniMax-M3：context 1,000,000（精确整数，输入+输出合计）；M2.x：204,800
  - thinking：Chat Completions 省略 thinking → adaptive 开启（thinking_default_on=True）；
    M2.x 思考关不掉；Responses API 默认 effort=none 关闭（A15 主路径为 Chat，注释差异）
  - 采样参数：temperature ∈ [0,2] 默认 1；未找到「thinking 拒绝 temperature」明文
  - 无官方 tiktoken → 用 ``chars:1.6`` 估算（§7.5 问 6 启发式）

数值来源（A0 §7.5）：
  - https://platform.minimaxi.com/docs/api-reference/api-overview
  - https://platform.minimaxi.com/docs/api-reference/text-chat-openai
  - https://platform.minimaxi.com/docs/api-reference/text-prompt-caching
  - https://platform.minimaxi.com/docs/guides/pricing-paygo
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

_MINIMAX_USAGE = UsageFieldMap(
    # §7.5 问 4：官方 OpenAI 路径 usage.prompt_tokens_details.cached_tokens（嵌套）
    cache_read_flat=(),
    cache_read_nested=(("prompt_tokens_details", "cached_tokens"),),
    # §7.5 问 4/5：缓存写入价仅 M2.x 有；reasoning 在 message/delta（reasoning_content /
    # reasoning_details），非 usage 嵌套字段——显式清空 A12 承载的全局默认嵌套路径。
    # 注：`reasoning=()` 是 §7.5 ③ 的 UsageFieldMap 原文（「reasoning_content /
    # reasoning_details 在 message/delta，不在 usage」），与 A13/A14 同裁决一致；
    # 内容抽取由 A8 的 delta/message 路径处理（reasoning_split=true 时含 reasoning_details）。
    cache_write_nested=(),
    reasoning_nested=(),
    reasoning=(),
)

# §7.5 问 2：MM1 概览表可核验精确整数（输入+输出合计）
_M3_CONTEXT = 1_000_000
_M2X_CONTEXT = 204_800
# §7.5 ③：max_completion_tokens 上限（M3 524288 / M2.x 204800）
_M3_MAX_OUTPUT = 524_288
_M2X_MAX_OUTPUT = 204_800
# compaction ≈90% of context（与 DeepSeek 943_718 / OpenAI 945_000 同惯例）。
# 关键：M2.x 若沿用默认 232_000 会**高于**其 context_window 204_800（阈值>窗口，
# 压缩永不触发），必须按型号设置。
_M3_COMPACTION = 900_000
_M2X_COMPACTION = 184_320

# §7.5 问 7：定价按型号分条（CNY / 1M，中国区按量；as_of=2026-08-02；source_url=MM8）。
# M3 被动写入无额外价 → cache_write=None；highspeed 独立定价（不得与普通版共用）。
_MINIMAX_PRICING: dict[str, ModelPricing] = {
    "minimax-m3": ModelPricing(
        input_per_mtok=2.10,
        output_per_mtok=8.40,
        cached_input_per_mtok=0.42,
        cache_write_per_mtok=None,
        as_of="2026-08-02",
        source_url="https://platform.minimaxi.com/docs/guides/pricing-paygo",
    ),
    "minimax-m2.7": ModelPricing(
        input_per_mtok=2.1,
        output_per_mtok=8.4,
        cached_input_per_mtok=0.42,
        cache_write_per_mtok=2.625,
        as_of="2026-08-02",
        source_url="https://platform.minimaxi.com/docs/guides/pricing-paygo",
    ),
    "minimax-m2.7-highspeed": ModelPricing(
        input_per_mtok=4.2,
        output_per_mtok=16.8,
        cached_input_per_mtok=0.42,
        cache_write_per_mtok=2.625,
        as_of="2026-08-02",
        source_url="https://platform.minimaxi.com/docs/guides/pricing-paygo",
    ),
    "minimax-m2.5": ModelPricing(
        input_per_mtok=2.1,
        output_per_mtok=8.4,
        cached_input_per_mtok=0.21,
        cache_write_per_mtok=2.625,
        as_of="2026-08-02",
        source_url="https://platform.minimaxi.com/docs/guides/pricing-paygo",
    ),
    "minimax-m2.1": ModelPricing(
        input_per_mtok=2.1,
        output_per_mtok=8.4,
        cached_input_per_mtok=0.21,
        cache_write_per_mtok=2.625,
        as_of="2026-08-02",
        source_url="https://platform.minimaxi.com/docs/guides/pricing-paygo",
    ),
    "minimax-m2": ModelPricing(
        input_per_mtok=2.1,
        output_per_mtok=8.4,
        cached_input_per_mtok=0.21,
        cache_write_per_mtok=2.625,
        as_of="2026-08-02",
        source_url="https://platform.minimaxi.com/docs/guides/pricing-paygo",
    ),
}

#: 未调研型号 → 价格显式 None（来源 URL 仍在），不得静默当 0。
_DEFAULT_MINIMAX_PRICING = ModelPricing(
    input_per_mtok=None,
    output_per_mtok=None,
    cached_input_per_mtok=None,
    cache_write_per_mtok=None,
    as_of="2026-08-02",
    source_url="https://platform.minimaxi.com/docs/guides/pricing-paygo",
)

#: 调研覆盖的型号（§7.5 问 1，小写规范化；含 M2 系的 legacy highspeed 变体，
#: 见问 7「上述对应 -highspeed（历史）4.2/16.8/0.21/2.625」）。
_MINIMAX_FAMILY = {
    "minimax-m3",
    "minimax-m2.7",
    "minimax-m2.7-highspeed",
    "minimax-m2.5",
    "minimax-m2.5-highspeed",
    "minimax-m2.1",
    "minimax-m2.1-highspeed",
    "minimax-m2",
    "minimax-m2-highspeed",
}


def _family(model_name: str) -> str | None:
    """返回调研覆盖的型号规范名；未覆盖返回 None。"""
    name = model_name.lower().replace(" ", "")
    if name in _MINIMAX_FAMILY:
        return name
    return None


def _is_m3(family: str) -> bool:
    return family == "minimax-m3"


def _is_highspeed(family: str) -> bool:
    return family.endswith("-highspeed")


def _pricing_for(family: str | None) -> ModelPricing:
    if family is None:
        return _DEFAULT_MINIMAX_PRICING
    # 精确型号优先（M2.7-highspeed 在表内有独立条目 cache_read 0.42）
    if family in _MINIMAX_PRICING:
        return _MINIMAX_PRICING[family]
    # 历史 highspeed（M2.5-highspeed / M2.1-highspeed / M2-highspeed）未在表内单独列
    # 主条目，§7.5 问 7 末行给出 highspeed 档：4.2/16.8/cache_read 0.21/2.625。
    if _is_highspeed(family):
        return ModelPricing(
            input_per_mtok=4.2,
            output_per_mtok=16.8,
            cached_input_per_mtok=0.21,
            cache_write_per_mtok=2.625,
            as_of="2026-08-02",
            source_url="https://platform.minimaxi.com/docs/guides/pricing-paygo",
        )
    return _DEFAULT_MINIMAX_PRICING


def _prompt_variant(model_name: str) -> str:
    # 未调研变体保持 DEFAULT_CAPABILITIES.prompt_variant（"default"），与 A12/A13/A14 一致
    family = _family(model_name)
    if family is None:
        return "default"
    return "minimax-m3" if _is_m3(family) else "minimax-m2x"


class MiniMaxProvider(BaseProvider):
    name = "minimax"

    def matches(self, base_url: str, model_name: str) -> bool:
        url = base_url.lower()
        name = model_name.lower()
        # §7.5 ③：minimax/minimaxi 在 url 或模型名 → 命中
        # （国内 api.minimaxi.com / 国际 api.minimax.io；模型名 MiniMax-M3 等）
        return (
            "minimax" in url
            or "minimaxi" in url
            or "minimax" in name
        )

    def capabilities(self, model_config: dict) -> ModelCapabilities:
        model_name = str(model_config.get("model_name") or "").lower()
        family = _family(model_name)

        caps = replace(
            DEFAULT_CAPABILITIES,
            provider=self.name,
            usage_fields=_MINIMAX_USAGE,
            pricing=_pricing_for(family),
            prompt_variant=_prompt_variant(model_name),
        )
        if family is not None:
            context_window = _M3_CONTEXT if _is_m3(family) else _M2X_CONTEXT
            caps = replace(
                caps,
                context_window=context_window,
                compaction_threshold=(
                    _M3_COMPACTION if _is_m3(family) else _M2X_COMPACTION
                ),
                # §7.5 ③：M3 max_completion_tokens 上限 524288；M2.x 204800
                max_output_tokens=(
                    _M3_MAX_OUTPUT if _is_m3(family) else _M2X_MAX_OUTPUT
                ),
                supports_function_calling=True,
                # §7.5 问 1/③：M3 OpenAI 路径支持 image/video content parts（音频未支持）；
                # M2.x 未见多模态证据（MM4 仅述 M3），保守不声明（不臆造）。
                # 注：§7.5 ③「M2.x 改 window / 定价」指继承骨架默认的窗口/定价调整，
                # 但 vision 行注释明确为 M3 专属能力，M2.x 无对应官方证据 → False。
                supports_vision=_is_m3(family),
                supports_reasoning=True,
                # §7.5 问 5：Chat Completions 省略 thinking → adaptive 开启（主路径）
                thinking_default_on=True,
                supports_prompt_cache=True,
                # §7.5 ③ 列 json_schema，但 StructuredOutputMode 仅支持 function_calling /
                # json_in_text（A12/A13/A14 同裁决；Literal 类型约束；无运行时消费点）
                structured_output="function_calling",
                prompt_variant=_prompt_variant(model_name),
                # §7.5 问 5：未找到「thinking 拒绝 temperature」明文 → 保留采样参数
                accepts_temperature=True,
                # §7.5 问 6：官方无 tiktoken → chars:1.6 启发式（精确走 usage / input_tokens）
                tokenizer="chars:1.6",
                # §7.5 ③：Chat 路径无 reasoning.effort → 不设 effort_presets
                # （勿把 DeepSeek/Kimi effort_presets 套到 Chat）
                effort_presets={},
            )
        return caps.merged_with_overrides(model_config)

    def llm_kwargs(self, model_config: dict, caps: ModelCapabilities) -> dict:
        kwargs = super().llm_kwargs(model_config, caps)
        # §7.5 ③：Chat thinking 契约——
        #   M3：extra_body={"thinking": {"type": "adaptive"|"disabled"}, "reasoning_split": True}
        #   M2.x：thinking 关不掉（不臆造 adaptive 参数）；仍建议 reasoning_split=True 便于回传
        # A15 仅接线 Chat 路径；Responses 的 reasoning.effort 差异由 A21 处理。
        if caps.supports_reasoning and caps.thinking_default_on:
            family = _family(str(model_config.get("model_name") or ""))
            body = kwargs.setdefault("extra_body", {})
            if family is not None and _is_m3(family):
                body.setdefault("thinking", {"type": "adaptive"})
            body.setdefault("reasoning_split", True)
        return kwargs
