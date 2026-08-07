"""OpenAI provider —— 兜底 + 显式优化（A12）。

DC1 保持方式：本类同时承担"兜底"与"显式 OpenAI"两个角色。
  - 作为兜底（注册表全部落空时选用）：capabilities() 在 matches() 未命中时
    返回 DEFAULT_CAPABILITIES，与 Phase A 之前的硬编码行为逐字节一致。
  - 显式命中（base_url 含 openai.com，或模型名以 gpt-/o1-/o3-/o4- 开头）：
    应用 §7.2 调研报告的显式能力声明（2026-08-02 三方审计通过）。

数值来源（A0 §7.2，2026-08-02 三方审计通过）：
  - https://platform.openai.com/docs/models
  - https://platform.openai.com/docs/pricing
  - https://platform.openai.com/docs/guides/prompt-caching
  - https://platform.openai.com/docs/guides/reasoning
  - https://platform.openai.com/docs/guides/migrate-to-responses
"""

from __future__ import annotations

from dataclasses import replace

try:
    from ...config.model_capabilities import (
        DEFAULT_CAPABILITIES,
        ModelCapabilities,
        ModelPricing,
    )
except ImportError:  # pragma: no cover - repo-root layout (tests)
    from config.model_capabilities import (
        DEFAULT_CAPABILITIES,
        ModelCapabilities,
        ModelPricing,
    )
from .base import BaseProvider

#: gpt-5.6 三档定价（USD/1M，Short context Standard；§7.2 问 7 / ③，定价按型号分条）。
#: ModelPricing 无 cache_write 字段（卡 verbatim 结构），写入计费不在此表内。
_OPENAI_PRICING: dict[str, ModelPricing] = {
    "gpt-5.6-sol": ModelPricing(
        input_per_mtok=5.00,
        output_per_mtok=30.00,
        cached_input_per_mtok=0.50,
        as_of="2026-08-02",
        source_url="https://platform.openai.com/docs/pricing",
    ),
    "gpt-5.6-terra": ModelPricing(
        input_per_mtok=2.00,
        output_per_mtok=12.00,
        cached_input_per_mtok=0.20,
        as_of="2026-08-02",
        source_url="https://platform.openai.com/docs/pricing",
    ),
    "gpt-5.6-luna": ModelPricing(
        input_per_mtok=0.20,
        output_per_mtok=1.20,
        cached_input_per_mtok=0.02,
        as_of="2026-08-02",
        source_url="https://platform.openai.com/docs/pricing",
    ),
}

#: 未调研型号（如 gpt-5.2）→ 价格显式 None（来源 URL 仍在），不得静默当 0。
_DEFAULT_OPENAI_PRICING = ModelPricing(
    input_per_mtok=None,
    output_per_mtok=None,
    cached_input_per_mtok=None,
    as_of="2026-08-02",
    source_url="https://platform.openai.com/docs/pricing",
)


def _is_gpt_5_6(model_name: str) -> bool:
    """§7.2 调研对象为 gpt-5.6 三档（sol/terra/luna）及其别名。"""
    return "gpt-5.6" in model_name.lower()


def _prompt_variant(model_name: str) -> str:
    """gpt-5.6 按型号取 prompt_variant；其余保持默认。"""
    name = model_name.lower()
    for key in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
        if name == key:
            return key
    return "default"


def _pricing_for(model_name: str) -> ModelPricing:
    name = model_name.lower()
    for key, pricing in _OPENAI_PRICING.items():
        if name == key:
            return pricing
    return _DEFAULT_OPENAI_PRICING


class OpenAIProvider(BaseProvider):
    name = "openai"

    def matches(self, base_url: str, model_name: str) -> bool:
        url = base_url.lower()
        name = model_name.lower()
        return "openai.com" in url or name.startswith(("gpt-", "o1-", "o3-", "o4-"))

    def capabilities(self, model_config: dict) -> ModelCapabilities:
        base_url = str(model_config.get("base_url") or "")
        model_name = str(model_config.get("model_name") or "")
        if not self.matches(base_url, model_name):
            # DC1：兜底路径，行为与改造前完全一致。
            return DEFAULT_CAPABILITIES.merged_with_overrides(model_config)
        name = model_name.lower()
        caps = replace(
            DEFAULT_CAPABILITIES,
            provider=self.name,
            pricing=_pricing_for(name),
            effort_presets={
                "fast": "low",
                "balanced": "medium",
                "deep": "high",
            },
        )
        if _is_gpt_5_6(name):
            # §7.2 ③（2026-08-02 审计通过）：gpt-5.6 三档显式能力。
            caps = replace(
                caps,
                context_window=1_050_000,
                compaction_threshold=945_000,
                supports_vision=True,
                supports_reasoning=True,
                thinking_default_on=True,  # 省略 effort → 默认 medium
                supports_prompt_cache=True,
                structured_output="function_calling",
                prompt_variant=_prompt_variant(name),
                # §7.2 问 6：项目侧启发式；未找到官方 5.6 encoding 名
                tokenizer="tiktoken:o200k_base",
            )
        if name.startswith(("o1-", "o3-", "o4-")):
            # §7.2 问 5：旧 o 系列明文拒绝采样参数（5.6 未证实，勿外推）
            caps = replace(
                caps,
                supports_reasoning=True,
                thinking_default_on=True,
                accepts_temperature=False,
            )
        return caps.merged_with_overrides(model_config)

    def llm_kwargs(self, model_config: dict, caps: ModelCapabilities) -> dict:
        kwargs = super().llm_kwargs(model_config, caps)
        if caps.supports_reasoning and not caps.accepts_temperature:
            # §7.2 问 5：仅旧 o 系列有拒绝采样参数的明文；GPT-5.6 未找到，
            # 保留 temperature（accepts_temperature=True）。
            kwargs.pop("temperature", None)
        if caps.effort_presets:
            effort = str(model_config.get("effort") or "balanced")
            preset = caps.effort_presets.get(effort, "medium")
            # §7.2 问 5 / ③：Chat Completions 顶层参数 reasoning_effort
            # （不是 extra_body，也不是 DeepSeek 式 thinking.type）。
            kwargs["reasoning_effort"] = preset
        return kwargs
