"""Anthropic provider 行为测试（A18 补全：§7.8 五主力）。"""

import pytest

from config.model_capabilities import DEFAULT_CAPABILITIES, ModelPricing
from core import providers
from core.providers.anthropic import AnthropicProvider
from core.providers.openai import OpenAIProvider


@pytest.mark.parametrize(
    "cfg",
    [
        {
            "base_url": "https://api.anthropic.com/v1",
            "model_name": "claude-opus-5",
        },
        {
            "base_url": "https://relay.example/v1",
            "model_name": "claude-sonnet-5",
        },
        {"base_url": "https://example.com", "model_name": "claude-haiku-4-5"},
        {"base_url": "https://api.anthropic.com/v1", "model_name": "claude-fable-5"},
        {"base_url": "https://relay.example/v1", "model_name": "claude-opus-4-8"},
    ],
)
def test_matches_by_url_or_model_name(cfg):
    assert isinstance(providers.resolve(cfg), AnthropicProvider)


def test_unknown_model_does_not_match_anthropic():
    p = providers.resolve(
        {"base_url": "https://unknown.example/v1", "model_name": "mystery-1"}
    )
    assert isinstance(p, OpenAIProvider)


def test_uses_claude_prompt_variant():
    caps = providers.resolve({"model_name": "claude-opus-5"}).capabilities(
        {"model_name": "claude-opus-5"}
    )
    assert caps.prompt_variant == "claude"


def test_cache_read_uses_flat_cache_read_input_tokens():
    p = providers.resolve({"model_name": "claude-opus-5"})
    caps = p.capabilities({"model_name": "claude-opus-5"})
    assert p.extract_cache_read({"cache_read_input_tokens": 512}, caps) == 512
    assert (
        p.extract_cache_read(
            {"prompt_tokens_details": {"cached_tokens": 99}}, caps
        )
        == 0
    )


def test_supports_prompt_cache_reflects_explicit_cache_control():
    """§7.8：Anthropic 需显式 cache_control（原生 Messages），与 OpenAI 自动缓存不同。"""
    caps = providers.resolve({"model_name": "claude-opus-5"}).capabilities(
        {"model_name": "claude-opus-5"}
    )
    assert caps.supports_prompt_cache is True


def test_opus_context_window_is_1m_not_legacy_256k():
    caps = providers.resolve({"model_name": "claude-opus-5"}).capabilities(
        {"model_name": "claude-opus-5"}
    )
    assert caps.context_window == 1_000_000
    assert caps.context_window != 256_000


def test_haiku_context_window_is_200k():
    caps = providers.resolve({"model_name": "claude-haiku-4-5"}).capabilities(
        {"model_name": "claude-haiku-4-5"}
    )
    assert caps.context_window == 200_000


def test_supports_reasoning_and_tools():
    caps = providers.resolve({"model_name": "claude-opus-5"}).capabilities(
        {"model_name": "claude-opus-5"}
    )
    assert caps.supports_reasoning is True
    assert caps.supports_function_calling is True


def test_user_override_beats_provider_default():
    p = providers.resolve({"model_name": "claude-opus-5"})
    caps = p.capabilities({"model_name": "claude-opus-5", "context_window": 32_000})
    assert caps.context_window == 32_000


# ---- A18 补全：§7.8 ③ 五主力 ----


@pytest.mark.parametrize("name,context,maxout", [
    ("claude-opus-5", 1_000_000, 128_000),
    ("claude-sonnet-5", 1_000_000, 128_000),
    ("claude-fable-5", 1_000_000, 128_000),
    ("claude-opus-4-8", 1_000_000, 128_000),
    ("claude-haiku-4-5", 200_000, 64_000),
])
def test_five_mainstays_window_and_output(name, context, maxout):
    """§7.8 ③：五主力 context/max_output（A1 表 1M/200k/128k/64k）。"""
    caps = providers.resolve({"model_name": name}).capabilities({"model_name": name})
    assert caps.context_window == context
    assert caps.max_output_tokens == maxout
    assert caps.supports_vision is True


@pytest.mark.parametrize("name,default_on", [
    ("claude-opus-5", True),
    ("claude-sonnet-5", True),
    ("claude-fable-5", True),   # thinking always on, cannot disable
    ("claude-opus-4-8", False),  # default off; must explicit adaptive (A4)
    ("claude-haiku-4-5", False),  # extended only, explicit enabled (A1/A5)
])
def test_thinking_default_on_per_mainstay(name, default_on):
    """§7.8 问 5：Claude 5 默认开；Opus 4.8 / Haiku 4.5 默认关。"""
    caps = providers.resolve({"model_name": name}).capabilities({"model_name": name})
    assert caps.thinking_default_on is default_on


@pytest.mark.parametrize("name,inp,outp,hit", [
    ("claude-opus-5", 5.0, 25.0, 0.50),
    ("claude-sonnet-5", 2.0, 10.0, 0.20),
    ("claude-fable-5", 10.0, 50.0, 1.00),
    ("claude-opus-4-8", 5.0, 25.0, 0.50),
    ("claude-haiku-4-5", 1.0, 5.0, 0.10),
])
def test_per_mainstay_pricing(name, inp, outp, hit):
    """§7.8 问 7：五主力 input/output/cache_hit 分条（USD，as_of=2026-08-02）。"""
    caps = providers.resolve({"model_name": name}).capabilities({"model_name": name})
    assert isinstance(caps.pricing, ModelPricing)
    assert caps.pricing.input_per_mtok == inp
    assert caps.pricing.output_per_mtok == outp
    assert caps.pricing.cached_input_per_mtok == hit
    assert caps.pricing.as_of == "2026-08-02"
    assert caps.pricing.source_url


def test_cache_write_flat_mapping():
    """§7.8 ③：Anthropic 缓存写入在顶层 usage.cache_creation_input_tokens。"""
    caps = providers.resolve({"model_name": "claude-opus-5"}).capabilities(
        {"model_name": "claude-opus-5"}
    )
    assert caps.usage_fields.cache_write_flat == ("cache_creation_input_tokens",)
    assert caps.usage_fields.cache_read_flat == ("cache_read_input_tokens",)


def test_opus_48_tokenizer_notes():
    """§7.8 问 6：无 tiktoken，用 count_tokens；tokenizer 非官方启发式。"""
    caps = providers.resolve({"model_name": "claude-opus-4-8"}).capabilities(
        {"model_name": "claude-opus-4-8"}
    )
    assert caps.tokenizer == "chars:3.0"


def test_unknown_anthropic_variant_stays_conservative():
    """未调研型号不套用调研能力：仅 provider/usage/pricing 变化，能力字段保守。"""
    for name in ["claude-unknown-variant", "claude-opus-3", "claude-mythos-5"]:
        caps = providers.resolve({"model_name": name}).capabilities({"model_name": name})
        assert caps.provider == "anthropic"
        assert caps.context_window == DEFAULT_CAPABILITIES.context_window == 256_000
        assert caps.max_output_tokens is None
        assert caps.supports_reasoning is False
        assert caps.prompt_variant == DEFAULT_CAPABILITIES.prompt_variant == "default"