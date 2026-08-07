"""Anthropic Claude provider（A18 补全：OpenAI 兼容端点路径 + 五主力）。

与 OpenAI 默认行为的差异以 A0 批 8 调研报告（§7.8，2026-08-02 三方审计通过）为准：
  - prompt 缓存需显式 ``cache_control``（ephemeral / automatic），与 OpenAI 的
    自动隐式缓存不同；usage 命中字段为顶层 ``cache_read_input_tokens``、
    写入字段为顶层 ``cache_creation_input_tokens``
  - thinking 在 ``content[]`` 的 ``type: "thinking"`` 块（含 signature），
    非 ``reasoning_content``
  - Claude 5（Opus/Sonnet/Fable）默认开 adaptive thinking；**Opus 4.8** 默认关、
    须显式 ``thinking:{type:"adaptive"}``（type:enabled → 400）；**Haiku 4.5** 仅
    extended（显式 enabled + budget_tokens）
  - 无官方 tiktoken → 用 ``chars:3.0`` 启发式（精确走 messages.count_tokens；A5 前）

限制说明：本项目走 OpenAI 兼容端点（MA4 禁止引入 anthropic SDK），因此
cache_control 断点与 thinking block 的原生语义在兼容端点上可能不完整透传；
capabilities 按原生 Messages 能力声明（生产主路径），兼容端点的能力边界
（无 prompt caching / thinking 细节不完整）由 A19 的缓存卡按真实端点行为处理，
OpenAI 兼容层仅作评测用。

数值来源（A0 §7.8）：
  - https://docs.anthropic.com/en/docs/about-claude/models/overview
  - https://docs.anthropic.com/en/docs/about-claude/pricing
  - https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
  - https://docs.anthropic.com/en/docs/build-with-claude/thinking
  - https://docs.anthropic.com/en/docs/build-with-claude/token-counting
  - https://docs.anthropic.com/en/api/messages
  - https://docs.anthropic.com/en/api/openai-sdk
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

_ANTHROPIC_USAGE = UsageFieldMap(
    # §7.8 ③：顶层 usage 字段（非嵌套）
    cache_read_flat=("cache_read_input_tokens",),
    cache_read_nested=(),
    cache_write_flat=("cache_creation_input_tokens",),
    reasoning=(),  # thinking 在 content blocks，非 delta.reasoning_content
)

# §7.8 A1：Opus/Sonnet/Fable/Opus 4.8 为 1M；Haiku 4.5 为 200k
_CONTEXT_WINDOW_DEFAULT = 1_000_000
_CONTEXT_WINDOW_HAIKU = 200_000
# §7.8 A1：输出 128k（Haiku 64k）
_MAX_OUTPUT_DEFAULT = 128_000
_MAX_OUTPUT_HAIKU = 64_000
# RxyCode 项目约定：compaction_threshold ≈ context 的 90%（同 A3 §7.1 / DeepSeek 卡；
# 非 Anthropic 官方文档数值）
_COMPACTION_RATIO = 0.9

# §7.8 问 7：定价按型号分条（USD / 1M；as_of=2026-08-02；source_url=A2）。
# 5m / 1h cache write 单价（写入价 = 1.25×/2× base input）经 ModelPricing 的
# cache_write_per_mtok 承载（填 5m 档）；cache_creation 由 usage 字段采集。
# Sonnet 5 取至 2026-08-31 入门价（§7.8 问 7）。
_ANTHROPIC_PRICING: dict[str, ModelPricing] = {
    "claude-opus-5": ModelPricing(
        input_per_mtok=5.0,
        output_per_mtok=25.0,
        cached_input_per_mtok=0.50,
        cache_write_per_mtok=6.25,  # 5m cache write（1.25×）
        as_of="2026-08-02",
        source_url="https://docs.anthropic.com/en/docs/about-claude/pricing",
    ),
    "claude-sonnet-5": ModelPricing(
        input_per_mtok=2.0,
        output_per_mtok=10.0,
        cached_input_per_mtok=0.20,
        cache_write_per_mtok=2.50,  # 5m cache write（1.25×）
        as_of="2026-08-02",
        source_url="https://docs.anthropic.com/en/docs/about-claude/pricing",
    ),
    "claude-fable-5": ModelPricing(
        input_per_mtok=10.0,
        output_per_mtok=50.0,
        cached_input_per_mtok=1.00,
        cache_write_per_mtok=12.50,  # 5m cache write（1.25×）
        as_of="2026-08-02",
        source_url="https://docs.anthropic.com/en/docs/about-claude/pricing",
    ),
    "claude-opus-4-8": ModelPricing(
        input_per_mtok=5.0,
        output_per_mtok=25.0,
        cached_input_per_mtok=0.50,
        cache_write_per_mtok=6.25,  # 5m cache write（1.25×）
        as_of="2026-08-02",
        source_url="https://docs.anthropic.com/en/docs/about-claude/pricing",
    ),
    "claude-haiku-4-5": ModelPricing(
        input_per_mtok=1.0,
        output_per_mtok=5.0,
        cached_input_per_mtok=0.10,
        cache_write_per_mtok=1.25,  # 5m cache write（1.25×）
        as_of="2026-08-02",
        source_url="https://docs.anthropic.com/en/docs/about-claude/pricing",
    ),
}

#: 未调研型号 → 价格显式 None（来源 URL 仍在），不得静默当 0。
_DEFAULT_ANTHROPIC_PRICING = ModelPricing(
    input_per_mtok=None,
    output_per_mtok=None,
    cached_input_per_mtok=None,
    cache_write_per_mtok=None,
    as_of="2026-08-02",
    source_url="https://docs.anthropic.com/en/docs/about-claude/pricing",
)

#: 调研覆盖的五主力（§7.8 问 1；Opus 4.8 不得省略）。
_ANTHROPIC_FAMILY = {
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-opus-4-8",
    "claude-haiku-4-5",
}


def _family(model_name: str) -> str | None:
    """返回调研覆盖的型号规范名；未覆盖返回 None。"""
    name = model_name.lower()
    if name in _ANTHROPIC_FAMILY:
        return name
    return None


def _context_window(family: str) -> int:
    return _CONTEXT_WINDOW_HAIKU if family == "claude-haiku-4-5" else _CONTEXT_WINDOW_DEFAULT


def _max_output(family: str) -> int:
    return _MAX_OUTPUT_HAIKU if family == "claude-haiku-4-5" else _MAX_OUTPUT_DEFAULT


def _thinking_default_on(family: str) -> bool:
    """§7.8 问 5：Claude 5（Opus/Sonnet/Fable）默认开；Opus 4.8 默认关
    （须显式 adaptive）；Haiku 4.5 仅 extended（显式 enabled）。"""
    return family in ("claude-opus-5", "claude-sonnet-5", "claude-fable-5")


def _cache_min_block(family: str) -> int:
    """§7.8 问 4（A3 最小可缓存长度，按型号）：Fable/Opus 5=512；
    Opus 4.8/Sonnet 5=1024；Haiku 4.5=4096。"""
    if family in ("claude-fable-5", "claude-opus-5"):
        return 512
    if family == "claude-haiku-4-5":
        return 4096
    return 1024


def _pricing_for(family: str | None) -> ModelPricing:
    if family is None:
        return _DEFAULT_ANTHROPIC_PRICING
    return _ANTHROPIC_PRICING[family]


def _prompt_variant(model_name: str) -> str:
    # 未调研变体保持 DEFAULT_CAPABILITIES.prompt_variant（"default"），与 A12–A17 一致
    family = _family(model_name)
    return "claude" if family is not None else "default"


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def matches(self, base_url: str, model_name: str) -> bool:
        url = base_url.lower()
        name = model_name.lower()
        # §7.8 ③：anthropic URL 或 claude- 模型名前缀 → 命中。
        # "anthropic" in url 命中中转站路径含 anthropic 的 URL 属预期（模型族确实来自 Anthropic）。
        return "anthropic" in url or name.startswith("claude-")

    def capabilities(self, model_config: dict) -> ModelCapabilities:
        model_name = str(model_config.get("model_name") or "").lower()
        family = _family(model_name)

        caps = replace(
            DEFAULT_CAPABILITIES,
            provider=self.name,
            usage_fields=_ANTHROPIC_USAGE,
            pricing=_pricing_for(family),
            prompt_variant=_prompt_variant(model_name),
        )
        if family is not None:
            context_window = _context_window(family)
            caps = replace(
                caps,
                context_window=context_window,
                compaction_threshold=int(context_window * _COMPACTION_RATIO),
                # §7.8 A1：max_output 128k（Haiku 64k）
                max_output_tokens=_max_output(family),
                supports_function_calling=True,
                # §7.8 A1：五主力均支持视觉
                supports_vision=True,
                supports_reasoning=True,
                # §7.8 问 5：Claude 5 默认开；Opus 4.8 / Haiku 4.5 默认关
                thinking_default_on=_thinking_default_on(family),
                # §7.8 ③：原生 Messages 支持显式 cache_control（与 OpenAI 自动缓存不同）。
                # OpenAI 兼容层不支持 cache（A6）——A19 按真实端点行为处理。
                supports_prompt_cache=True,
                # §7.8 ③ 未列 json_schema；StructuredOutputMode 仅支持 function_calling /
                # json_in_text（A12–A17 同裁决；无运行时消费点）
                structured_output="function_calling",
                prompt_variant=_prompt_variant(model_name),
                # §7.8 问 5：非默认 temperature/top_p/top_k 一律 400（与是否 thinking 无关）
                # → 不传自定义采样参数，保持默认采样
                accepts_temperature=False,
                # §7.8 问 6：官方无 tiktoken → chars:3.0 启发式占位（A5 前）；
                # 精确计数走 messages.count_tokens；4.7+ 族同文约 +30% tokens
                tokenizer="chars:3.0",
                # §7.8 ③：Anthropic 无 reasoning.effort（thinking 走 content block /
                # output_config.effort，属 A21）→ 不设 effort_presets
                effort_presets={},
                # §7.8 问 4（A19）：显式 cache_control 断点（最多 4 个，静态在前）+
                # 按型号最小块 + TTL 5min=300s
                cache_min_block_tokens=_cache_min_block(family),
                cache_ttl_s=300,
                cache_breakpoints=("tools", "system", "session_static", "tail"),
            )
        return caps.merged_with_overrides(model_config)
