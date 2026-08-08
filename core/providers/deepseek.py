"""DeepSeek provider.

与 OpenAI 默认行为的差异：
  - 前缀缓存命中数在顶层 usage.prompt_cache_hit_tokens（OpenAI 是嵌套在
    prompt_tokens_details.cached_tokens 里）
  - V4 系默认 thinking enabled，thinking 模式下 temperature 等采样参数无效
  - 上下文窗口 1M（非全局默认 256k）

数值来源（A0 §7.1，2026-08-02 三方审计通过）：
  - https://api-docs.deepseek.com/
  - https://api-docs.deepseek.com/quick_start/pricing
  - https://api-docs.deepseek.com/guides/thinking_mode
  - https://api-docs.deepseek.com/guides/kv_cache
  - https://api-docs.deepseek.com/api/create-chat-completion/
  - https://api-docs.deepseek.com/quick_start/token_usage
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

_DEEPSEEK_USAGE = UsageFieldMap(
    cache_read_flat=("prompt_cache_hit_tokens",),
    cache_read_nested=(),  # Chat Completions 主路径不用嵌套形式
    reasoning=("reasoning_content",),
)

# §7.1：v4-flash / v4-pro 均为 1M context；max output 384K；compaction ≈90%
_CONTEXT_WINDOW = 1_048_576
_MAX_OUTPUT = 384_000
_COMPACTION_THRESHOLD = 943_718

# §7.1 问 7：定价分条（USD / 1M；as_of=2026-08-02；source_url=S2）。
# 缓存写入价：无单独写入价（自动磁盘缓存）→ None。
_DEEPSEEK_PRICING: dict[str, ModelPricing] = {
    "deepseek-v4-flash": ModelPricing(
        input_per_mtok=0.14,
        output_per_mtok=0.28,
        cached_input_per_mtok=0.0028,
        cache_write_per_mtok=None,
        as_of="2026-08-02",
        source_url="https://api-docs.deepseek.com/quick_start/pricing",
    ),
    "deepseek-v4-pro": ModelPricing(
        input_per_mtok=0.435,
        output_per_mtok=0.87,
        cached_input_per_mtok=0.003625,
        cache_write_per_mtok=None,
        as_of="2026-08-02",
        source_url="https://api-docs.deepseek.com/quick_start/pricing",
    ),
}

#: 未调研/旧型号 → 价格显式 None（来源 URL 仍在），不得静默当 0。
_DEFAULT_DEEPSEEK_PRICING = ModelPricing(
    input_per_mtok=None,
    output_per_mtok=None,
    cached_input_per_mtok=None,
    cache_write_per_mtok=None,
    as_of="2026-08-02",
    source_url="https://api-docs.deepseek.com/quick_start/pricing",
)


def _pricing_for(model_name: str) -> ModelPricing:
    name = model_name.lower()
    if "v4-pro" in name or name == "deepseek-v4-pro":
        return _DEEPSEEK_PRICING["deepseek-v4-pro"]
    if "v4-flash" in name or name == "deepseek-v4-flash":
        return _DEEPSEEK_PRICING["deepseek-v4-flash"]
    return _DEFAULT_DEEPSEEK_PRICING


def _thinking_default_on(model_name: str) -> bool:
    """Whether this model id runs with thinking enabled by default (§7.1)."""
    name = model_name.lower()
    if name in ("deepseek-chat",) or (
        name.endswith("-chat") and "reasoner" not in name
    ):
        return False
    return True


def _prompt_variant(model_name: str) -> str:
    name = model_name.lower()
    if "v4-pro" in name or name == "deepseek-v4-pro":
        return "deepseek-v4-pro"
    return "deepseek-v4-flash"


class DeepSeekProvider(BaseProvider):
    name = "deepseek"

    def matches(self, base_url: str, model_name: str) -> bool:
        return "deepseek" in base_url.lower() or "deepseek" in model_name.lower()

    def capabilities(self, model_config: dict) -> ModelCapabilities:
        model_name = str(model_config.get("model_name") or "").lower()
        thinking_on = _thinking_default_on(model_name)
        is_v4 = "v4" in model_name or model_name in ("deepseek-v4-flash", "deepseek-v4-pro")

        caps = replace(
            DEFAULT_CAPABILITIES,
            provider=self.name,
            context_window=_CONTEXT_WINDOW,
            compaction_threshold=_COMPACTION_THRESHOLD,
            # §7.1 问 2：仅 v4 系 max output 384K；旧型号/未知变体保持 None（DC1）
            max_output_tokens=(_MAX_OUTPUT if is_v4 else None),
            usage_fields=_DEEPSEEK_USAGE,
            pricing=_pricing_for(model_name),
            supports_reasoning=thinking_on,
            # §7.1：thinking 模式下 temperature 不报错但无效
            accepts_temperature=not thinking_on,
            # §7.1：flash/pro 均支持 Tool Calls（含 thinking 模式）
            supports_function_calling=True,
            structured_output="function_calling",
            prompt_variant=_prompt_variant(model_name),
            # §7.1 问 5/③：v4 系 thinking 默认开启；effort 档位 low/high/max（默认 high）
            thinking_default_on=thinking_on,
            effort_presets=(
                {"fast": "low", "balanced": "high", "deep": "max"}
                if thinking_on
                else {}
            ),
            # §7.1 问 4：自动 disk 缓存，最小 64-token prefix unit；无显式断点/TTL
            cache_min_block_tokens=64,
            cache_ttl_s=None,
            cache_breakpoints=(),
            # §7.1 启发式估算（非官方 tiktoken）；精确数以 API usage 为准
            tokenizer="chars:2.0",
        )
        return caps.merged_with_overrides(model_config)
