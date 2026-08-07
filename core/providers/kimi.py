"""Kimi / Moonshot provider（A13）。

与 OpenAI 默认行为的差异以 A0 批 3 调研报告（§7.3，2026-08-02 三方审计通过）为准：
  - 缓存命中字段：顶层 ``usage.cached_tokens``（非 prompt_cache_hit_tokens，不嵌套）
  - reasoning 内容在 message/delta 层（非 usage 嵌套字段）
  - kimi-k3：1M 上下文 / 始终推理；k2.7 系与 k2.6：262k / 始终思考（K2.x 不支持 reasoning_effort）
  - 采样参数固定（temperature 1.0 等），勿显式传；改值报错
  - 无官方 tiktoken → 用 ``chars:1.75`` 估算（§7.3 问 6 启发式）

数值来源（A0 §7.3）：
  - https://platform.kimi.com/docs/models
  - https://platform.kimi.com/docs/api/chat
  - https://platform.kimi.com/docs/guide/use-thinking-models
  - https://platform.kimi.com/docs/guide/use-reasoning-effort
  - https://platform.kimi.com/docs/pricing/chat-k3
  - https://platform.kimi.com/docs/pricing/chat-k26
  - https://platform.kimi.com/docs/pricing/chat-k27-code
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

_KIMI_USAGE = UsageFieldMap(
    # §7.3 问 4：官方 OpenAPI 用顶层 cached_tokens（不嵌套）
    cache_read_flat=("cached_tokens",),
    cache_read_nested=(),
    reasoning=(),  # reasoning 在 message.reasoning_content，非 usage 嵌套字段
)

# §7.3 问 2：定价页精确 context（非营销「1M / 256k」近似）
_K3_CONTEXT = 1_048_576
_K2X_CONTEXT = 262_144
# RxyCode 项目约定：compaction_threshold ≈ context 的 90%（同 A3 §7.1；非厂商文档数值）
_K3_COMPACTION = 943_000
_K2X_COMPACTION = 236_000

# §7.3 问 7：定价按型号分条（CNY / 1M，中国区；as_of=2026-08-02；勿填国际站 USD）。
# cache_write 单价官方未找到 → None（不得静默当 0）。
_KIMI_PRICING: dict[str, ModelPricing] = {
    "kimi-k3": ModelPricing(
        input_per_mtok=20.00,
        output_per_mtok=100.00,
        cached_input_per_mtok=2.00,
        cache_write_per_mtok=None,
        as_of="2026-08-02",
        source_url="https://platform.kimi.com/docs/pricing/chat-k3",
    ),
    "kimi-k2.7-code": ModelPricing(
        input_per_mtok=6.50,
        output_per_mtok=27.00,
        cached_input_per_mtok=1.30,
        cache_write_per_mtok=None,
        as_of="2026-08-02",
        source_url="https://platform.kimi.com/docs/pricing/chat-k27-code",
    ),
    "kimi-k2.7-code-highspeed": ModelPricing(
        input_per_mtok=13.00,
        output_per_mtok=54.00,
        cached_input_per_mtok=2.60,
        cache_write_per_mtok=None,
        as_of="2026-08-02",
        source_url="https://platform.kimi.com/docs/pricing/chat-k27-code",
    ),
    "kimi-k2.6": ModelPricing(
        input_per_mtok=6.50,
        output_per_mtok=27.00,
        cached_input_per_mtok=1.10,
        cache_write_per_mtok=None,
        as_of="2026-08-02",
        source_url="https://platform.kimi.com/docs/pricing/chat-k26",
    ),
}

#: 未调研型号（kimi-k2.5 / moonshot-v1-*）→ 价格显式 None（来源 URL 仍在），不得静默当 0。
_DEFAULT_KIMI_PRICING = ModelPricing(
    input_per_mtok=None,
    output_per_mtok=None,
    cached_input_per_mtok=None,
    cache_write_per_mtok=None,
    as_of="2026-08-02",
    source_url="https://platform.kimi.com/docs/pricing/chat",
)

#: 调研覆盖的型号（§7.3 问 1：RxyCode 主写 k3 / k2.7-code / k2.7-code-highspeed / k2.6）。
_KIMI_FAMILY: dict[str, str] = {
    "kimi-k3": "kimi-k3",
    "kimi-k2.7-code": "kimi-k2.7-code",
    "kimi-k2.7-code-highspeed": "kimi-k2.7-code-highspeed",
    "kimi-k2.6": "kimi-k2.6",
}


def _family(model_name: str) -> str | None:
    """返回调研覆盖的型号规范名；未覆盖返回 None（k2.5/moonshot-v1/未知变体）。"""
    return _KIMI_FAMILY.get(model_name.lower())


def _prompt_variant(model_name: str) -> str:
    family = _family(model_name)
    return family if family is not None else "kimi"


def _pricing_for(model_name: str) -> ModelPricing:
    family = _family(model_name)
    if family is not None:
        return _KIMI_PRICING[family]
    return _DEFAULT_KIMI_PRICING


class KimiProvider(BaseProvider):
    name = "kimi"

    def matches(self, base_url: str, model_name: str) -> bool:
        url = base_url.lower()
        name = model_name.lower()
        # §7.3 问 3：api.moonshot.cn / api.moonshot.ai 均可；kimi 模型名任意端点命中。
        # 勿写成 endswith("moonshot.com") 之类把 .cn 漏掉。
        return "moonshot" in url or "kimi" in name

    def capabilities(self, model_config: dict) -> ModelCapabilities:
        model_name = str(model_config.get("model_name") or "").lower()
        family = _family(model_name)

        caps = replace(
            DEFAULT_CAPABILITIES,
            provider=self.name,
            usage_fields=_KIMI_USAGE,
            pricing=_pricing_for(model_name),
            prompt_variant=_prompt_variant(model_name),
        )
        if family is not None:
            context_window = _K3_CONTEXT if family == "kimi-k3" else _K2X_CONTEXT
            caps = replace(
                caps,
                context_window=context_window,
                compaction_threshold=(
                    _K3_COMPACTION if family == "kimi-k3" else _K2X_COMPACTION
                ),
                # §7.3 问 2：k3 max_completion_tokens 默认 131072（上限可至 1M）
                max_output_tokens=(131_072 if family == "kimi-k3" else None),
                supports_function_calling=True,
                # §7.3 问 1：k3 原生视觉 + video；k2.x 未声明（不臆造）
                supports_vision=(family == "kimi-k3"),
                supports_reasoning=True,
                thinking_default_on=True,  # k3 始终推理；k2.x 始终/默认思考
                supports_prompt_cache=True,
                structured_output="function_calling",
                prompt_variant=_prompt_variant(model_name),
                # §7.3 问 5：采样参数固定，勿显式传（改值报错）
                accepts_temperature=False,
                # §7.3 问 6：官方无 tiktoken → chars:1.75 启发式（精确走 estimate-token-count / usage）
                tokenizer="chars:1.75",
                # §7.3 问 5：仅 k3 支持 reasoning_effort（low/high/max，无 medium）
                effort_presets=(
                    {"fast": "low", "balanced": "high", "deep": "max"}
                    if family == "kimi-k3"
                    else {}
                ),
            )
        return caps.merged_with_overrides(model_config)
