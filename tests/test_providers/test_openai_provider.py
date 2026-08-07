"""OpenAIProvider 显式优化测试：DC1 保持 + 显式能力（A12）。"""

import pytest

from config.model_capabilities import DEFAULT_CAPABILITIES, ModelPricing
from core import providers
from core.providers.openai import OpenAIProvider


def _resolve(model_name: str):
    cfg = {"base_url": "https://api.openai.com/v1", "model_name": model_name}
    return providers.resolve(cfg), cfg


def _caps(model_name: str):
    p, cfg = _resolve(model_name)
    return p.capabilities(cfg)


# ---- 匹配（卡内测试） -------------------------------------------------


def test_explicit_openai_url_is_matched():
    p = providers.resolve({"base_url": "https://api.openai.com/v1",
                           "model_name": "gpt-5.2"})
    assert isinstance(p, OpenAIProvider)


def test_relay_with_gpt_name_is_matched():
    p = providers.resolve({"base_url": "https://relay.example/v1",
                           "model_name": "gpt-5.2"})
    assert isinstance(p, OpenAIProvider)


# ---- DC1（卡内测试） ---------------------------------------------------


def test_fallback_path_keeps_legacy_defaults():
    # DC1：未知模型仍拿到与改造前逐字节一致的能力
    caps = providers.resolve(
        {"base_url": "https://relay.example/v1", "model_name": "mystery-1"}
    ).capabilities({"base_url": "https://relay.example/v1", "model_name": "mystery-1"})
    assert caps == DEFAULT_CAPABILITIES


# ---- 显式命中（卡内测试） ----------------------------------------------


def test_matched_gpt_gets_explicit_caps():
    caps = providers.resolve({"base_url": "https://api.openai.com/v1",
                              "model_name": "gpt-5.2"}).capabilities(
        {"base_url": "https://api.openai.com/v1", "model_name": "gpt-5.2"})
    assert caps.provider == "openai"
    assert caps.pricing.source_url  # 调研报告 URL 已填
    assert caps.effort_presets.get("fast")


def test_reasoning_model_drops_temperature():
    p = providers.resolve({"base_url": "https://api.openai.com/v1",
                           "model_name": "o4-mini"})
    caps = p.capabilities({"base_url": "https://api.openai.com/v1",
                           "model_name": "o4-mini"})
    kwargs = p.llm_kwargs({"base_url": "https://api.openai.com/v1",
                           "model_name": "o4-mini"}, caps)
    assert "temperature" not in kwargs


# ---- §7.2 ③ 显式能力（gpt-5.6 三档） -----------------------------------


@pytest.mark.parametrize("name,inp,outp,cached,cwrite", [
    ("gpt-5.6-sol", 5.00, 30.00, 0.50, 6.25),
    ("gpt-5.6-terra", 2.00, 12.00, 0.20, 2.50),
    ("gpt-5.6-luna", 0.20, 1.20, 0.02, 0.25),
])
def test_per_model_pricing(name, inp, outp, cached, cwrite):
    """§7.2 问 7：定价按型号分条，带 cache_write 与 as_of/source_url。"""
    caps = _caps(name)
    assert caps.pricing.input_per_mtok == inp
    assert caps.pricing.output_per_mtok == outp
    assert caps.pricing.cached_input_per_mtok == cached
    assert caps.pricing.cache_write_per_mtok == cwrite
    assert caps.pricing.as_of == "2026-08-02"
    assert caps.pricing.source_url


def test_unknown_openai_model_gets_explicit_none_pricing():
    """未调研型号（如 gpt-5.2）→ 价格显式 None（来源 URL 仍在），不得静默当 0。"""
    caps = _caps("gpt-5.2")
    assert isinstance(caps.pricing, ModelPricing)
    assert caps.pricing.input_per_mtok is None
    assert caps.pricing.source_url


@pytest.mark.parametrize("name,variant", [
    ("gpt-5.6-sol", "gpt-5.6-sol"),
    ("gpt-5.6-terra", "gpt-5.6-terra"),
    ("gpt-5.6-luna", "gpt-5.6-luna"),
])
def test_gpt_5_6_section_7_2_values(name, variant):
    """§7.2 ③：context/compaction/vision/reasoning/prompt_variant。"""
    caps = _caps(name)
    assert caps.context_window == 1_050_000
    assert caps.compaction_threshold == 945_000
    assert caps.max_output_tokens == 128_000
    assert caps.supports_vision is True
    assert caps.supports_reasoning is True
    assert caps.thinking_default_on is True
    assert caps.supports_prompt_cache is True
    assert caps.prompt_variant == variant


def test_gpt_5_6_alias_maps_to_sol():
    """§7.2 问 1：gpt-5.6 是 gpt-5.6-sol 的别名。"""
    caps = _caps("gpt-5.6")
    assert caps.context_window == 1_050_000
    assert caps.prompt_variant == "gpt-5.6-sol"
    assert caps.pricing.input_per_mtok == 5.00


def test_unknown_5_6_variant_is_not_researched():
    """gpt-5.6-<unknown> 不得误套调研能力（收紧匹配）。"""
    caps = _caps("gpt-5.6-unknown")
    assert caps.context_window == 256_000
    assert caps.max_output_tokens is None
    assert caps.supports_reasoning is False
    p, cfg = _resolve("gpt-5.6-unknown")
    assert "reasoning_effort" not in p.llm_kwargs(cfg, caps)


def test_non_researched_gpt_does_not_inject_reasoning_effort():
    """gpt-4o/gpt-5.2 无 §7.2 数据：仅保留推理能力时注入 reasoning_effort。"""
    caps = _caps("gpt-4o")
    assert caps.supports_reasoning is False
    p, cfg = _resolve("gpt-4o")
    kwargs = p.llm_kwargs(cfg, caps)
    assert "reasoning_effort" not in kwargs


def test_usage_field_map_has_5_6_mappings():
    """§7.2 ③：cache_write_nested / reasoning_nested usage 映射已承载。"""
    caps = _caps("gpt-5.6-sol")
    assert ("prompt_tokens_details", "cache_write_tokens") in caps.usage_fields.cache_write_nested
    assert ("completion_tokens_details", "reasoning_tokens") in caps.usage_fields.reasoning_nested


def test_gpt_5_6_keeps_temperature():
    """§7.2 问 5：未找到 GPT-5.6 拒绝 temperature 的明文，不得外推 o 系列。"""
    caps = _caps("gpt-5.6-sol")
    p, cfg = _resolve("gpt-5.6-sol")
    kwargs = p.llm_kwargs(cfg, caps)
    assert "temperature" in kwargs


def test_reasoning_effort_is_top_level_param():
    """§7.2 问 5/③：Chat Completions 顶层参数 reasoning_effort（非 extra_body）。"""
    caps = _caps("gpt-5.6-sol")
    p, cfg = _resolve("gpt-5.6-sol")
    kwargs = p.llm_kwargs(cfg, caps)
    assert kwargs.get("reasoning_effort") == "medium"
    assert "reasoning_effort" not in (kwargs.get("extra_body") or {})


@pytest.mark.parametrize("effort,expected", [
    ("fast", "low"),
    ("balanced", "medium"),
    ("deep", "high"),
    ("ultra", "medium"),  # 未知档位回退 medium
])
def test_effort_preset_mapping(effort, expected):
    caps = _caps("gpt-5.6-sol")
    p, cfg = _resolve("gpt-5.6-sol")
    cfg["effort"] = effort
    assert p.llm_kwargs(cfg, caps)["reasoning_effort"] == expected


# ---- o 系列 --------------------------------------------------------------


def test_o_series_reasoning_caps():
    caps = _caps("o4-mini")
    assert caps.supports_reasoning is True
    assert caps.thinking_default_on is True
    assert caps.accepts_temperature is False


def test_effort_ignored_when_no_presets():
    """兜底路径（DEFAULT_CAPABILITIES）无 effort_presets，不注入 reasoning_effort。"""
    cfg = {"base_url": "https://relay.example/v1", "model_name": "mystery-1"}
    p = providers.resolve(cfg)
    caps = p.capabilities(cfg)
    assert caps == DEFAULT_CAPABILITIES
    assert caps.effort_presets == {}
    kwargs = p.llm_kwargs(cfg, caps)
    assert "reasoning_effort" not in kwargs
