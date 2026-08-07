"""MiniMaxProvider 显式能力测试（A15）：匹配、能力声明、定价、usage 提取。

数值全部来自 A0 批 5 调研报告（§7.5，2026-08-02 三方审计通过）。
主路径 = Chat Completions / ChatOpenAI。
"""

import pytest

from config.model_capabilities import DEFAULT_CAPABILITIES, ModelPricing
from core import providers
from core.providers.minimax import MiniMaxProvider

_CN = "https://api.minimaxi.com/v1"
_INTL = "https://api.minimax.io/v1"


def _resolve(model_name: str, base_url: str = _CN):
    cfg = {"base_url": base_url, "model_name": model_name, "resolved_max_tokens": 8192}
    return providers.resolve(cfg), cfg


def _caps(model_name: str, base_url: str = _CN):
    p, cfg = _resolve(model_name, base_url)
    return p.capabilities(cfg)


# ---- 匹配正反例 ---------------------------------------------------------


@pytest.mark.parametrize("cfg", [
    {"base_url": _CN, "model_name": "MiniMax-M3"},
    {"base_url": _INTL, "model_name": "MiniMax-M3"},
    {"base_url": "https://relay.example/v1", "model_name": "MiniMax-M2.7"},
    {"base_url": _CN, "model_name": "M2.7"},  # model name contains minimax? no; minimaxi in url
])
def test_matches_by_url_or_model_name(cfg):
    assert isinstance(providers.resolve(cfg), MiniMaxProvider)


@pytest.mark.parametrize("cfg", [
    {"base_url": "https://api.deepseek.com/v1", "model_name": "deepseek-chat"},
    {"base_url": "https://api.openai.com/v1", "model_name": "gpt-5.6-sol"},
    {"base_url": "https://api.moonshot.cn/v1", "model_name": "kimi-k3"},
    {"base_url": "https://ark.cn-beijing.volces.com/api/coding/v3", "model_name": "glm-5.2"},
])
def test_does_not_steal_other_models(cfg):
    assert not isinstance(providers.resolve(cfg), MiniMaxProvider)


def test_resolve_returns_minimax_for_minimax_config():
    p = providers.resolve({"base_url": _CN, "model_name": "MiniMax-M3"})
    assert isinstance(p, MiniMaxProvider)


# ---- §7.5 ③：MiniMax-M3 主骨架 ------------------------------------------


def test_m3_section_7_5_values():
    """§7.5 ③：M3 的 context/max_output/vision/reasoning/variant/tokenizer。"""
    caps = _caps("MiniMax-M3")
    assert caps.provider == "minimax"
    assert caps.context_window == 1_000_000
    assert caps.compaction_threshold == 900_000  # ≈90%（同 DeepSeek/OpenAI 惯例）
    assert caps.max_output_tokens == 524_288
    assert caps.supports_function_calling is True
    assert caps.supports_vision is True
    assert caps.supports_reasoning is True
    assert caps.thinking_default_on is True
    assert caps.supports_prompt_cache is True
    assert caps.prompt_variant == "minimax-m3"
    assert caps.tokenizer == "chars:1.6"


def test_m3_chat_path_has_no_effort_presets():
    """§7.5 ③：Chat 路径无 reasoning.effort，勿套 DeepSeek/Kimi effort_presets。"""
    caps = _caps("MiniMax-M3")
    assert caps.effort_presets == {}


def test_m3_keeps_temperature():
    """§7.5 问 5：未找到 thinking 拒绝 temperature 明文 → accepts_temperature=True。"""
    caps = _caps("MiniMax-M3")
    assert caps.accepts_temperature is True
    p, cfg = _resolve("MiniMax-M3")
    kwargs = p.llm_kwargs(cfg, caps)
    assert "temperature" in kwargs


# ---- §7.5 问 2：M2.x 窗口 -----------------------------------------------


@pytest.mark.parametrize("name", [
    "MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2.1", "MiniMax-M2",
])
def test_m2x_window(name):
    caps = _caps(name)
    assert caps.context_window == 204_800
    assert caps.compaction_threshold == 184_320  # ≈90%，且不得高于 context_window（默认 232k 会超窗口）
    assert caps.max_output_tokens == 204_800
    assert caps.supports_reasoning is True
    assert caps.thinking_default_on is True
    assert caps.prompt_variant == "minimax-m2x"  # A15 卡裁决：M2.x 家族变体（文档已定义）


# ---- §7.5 问 4：usage 嵌套 cached_tokens ---------------------------------


def test_cache_read_uses_nested_cached_tokens():
    """§7.5 问 4：usage.prompt_tokens_details.cached_tokens（嵌套），非平铺。"""
    p = providers.resolve({"base_url": _CN, "model_name": "MiniMax-M3"})
    caps = p.capabilities({"base_url": _CN, "model_name": "MiniMax-M3"})
    assert caps.usage_fields.cache_read_flat == ()
    assert caps.usage_fields.cache_read_nested == (("prompt_tokens_details", "cached_tokens"),)
    assert caps.usage_fields.reasoning == ()
    assert caps.usage_fields.reasoning_nested == ()
    assert caps.usage_fields.cache_write_nested == ()
    assert p.extract_cache_read(
        {"prompt_tokens_details": {"cached_tokens": 64}}, caps
    ) == 64
    assert p.extract_cache_read({"cached_tokens": 99}, caps) == 0


def test_reasoning_is_in_message_delta_not_usage():
    """§7.5 问 5：reasoning_content / reasoning_details 在 message/delta，不在 usage。"""
    caps = _caps("MiniMax-M3")
    assert caps.usage_fields.reasoning == ()
    assert caps.usage_fields.reasoning_nested == ()
    # A8 的 delta/message 抽取路径依赖 supports_reasoning 已开启
    assert caps.supports_reasoning is True


def test_llm_kwargs_injects_chat_thinking():
    """§7.5 ③：M3 Chat thinking 经 extra_body thinking=adaptive + reasoning_split=True。"""
    p, cfg = _resolve("MiniMax-M3")
    caps = p.capabilities(cfg)
    kwargs = p.llm_kwargs(cfg, caps)
    body = kwargs.get("extra_body") or {}
    assert body.get("thinking") == {"type": "adaptive"}
    assert body.get("reasoning_split") is True


def test_llm_kwargs_m2x_only_reasoning_split():
    """§7.5 ③：M2.x 思考关不掉——不注入 adaptive，仅 reasoning_split=True。"""
    for name in ["MiniMax-M2.7", "MiniMax-M2", "MiniMax-M2.5-highspeed"]:
        p, cfg = _resolve(name)
        caps = p.capabilities(cfg)
        kwargs = p.llm_kwargs(cfg, caps)
        body = kwargs.get("extra_body") or {}
        assert "thinking" not in body, f"{name} must not inject M3-only adaptive"
        assert body.get("reasoning_split") is True


def test_m2x_vision_stays_false():
    """§7.5 问 1：仅 M3 有官方 image/video 证据；M2.x 不臆造 supports_vision。"""
    for name in ["MiniMax-M2.7", "MiniMax-M2", "MiniMax-M2.1-highspeed"]:
        assert _caps(name).supports_vision is False


# ---- §7.5 问 7：定价按型号分条（CNY） -----------------------------------


@pytest.mark.parametrize("name,inp,outp,cached,cwrite", [
    ("MiniMax-M3", 2.10, 8.40, 0.42, None),
    ("MiniMax-M2.7", 2.1, 8.4, 0.42, 2.625),
    ("MiniMax-M2.7-highspeed", 4.2, 16.8, 0.42, 2.625),
    ("MiniMax-M2.5", 2.1, 8.4, 0.21, 2.625),
    ("MiniMax-M2.1", 2.1, 8.4, 0.21, 2.625),
    ("MiniMax-M2", 2.1, 8.4, 0.21, 2.625),
])
def test_per_model_pricing(name, inp, outp, cached, cwrite):
    """§7.5 问 7：定价按型号分条；highspeed 独立；M3 被动写入无额外价。"""
    caps = _caps(name)
    assert isinstance(caps.pricing, ModelPricing)
    assert caps.pricing.input_per_mtok == inp
    assert caps.pricing.output_per_mtok == outp
    assert caps.pricing.cached_input_per_mtok == cached
    assert caps.pricing.cache_write_per_mtok == cwrite
    assert caps.pricing.as_of == "2026-08-02"
    assert caps.pricing.source_url


@pytest.mark.parametrize("name,inp,outp,cached,cwrite", [
    ("MiniMax-M2.5-highspeed", 4.2, 16.8, 0.21, 2.625),
    ("MiniMax-M2.1-highspeed", 4.2, 16.8, 0.21, 2.625),
    ("MiniMax-M2-highspeed", 4.2, 16.8, 0.21, 2.625),
])
def test_legacy_highspeed_pricing(name, inp, outp, cached, cwrite):
    """§7.5 问 7 末行：legacy -highspeed 档 4.2/16.8/0.21/2.625（M2.5/M2.1/M2）。"""
    caps = _caps(name)
    assert caps.pricing.input_per_mtok == inp
    assert caps.pricing.output_per_mtok == outp
    assert caps.pricing.cached_input_per_mtok == cached
    assert caps.pricing.cache_write_per_mtok == cwrite


def test_unknown_minimax_variant_stays_conservative():
    """未调研型号不套用调研能力：仅 provider/usage/pricing 变化，能力字段保守。"""
    for name in ["MiniMax-X", "unknown-minimax-variant"]:
        caps = _caps(name)
        assert caps.provider == "minimax"
        assert caps.context_window == DEFAULT_CAPABILITIES.context_window == 256_000
        assert caps.max_output_tokens is None
        assert caps.supports_reasoning is False
        assert caps.effort_presets == {}
        assert caps.prompt_variant == DEFAULT_CAPABILITIES.prompt_variant == "default"


# ---- DC1 / 用户覆盖 ------------------------------------------------------


def test_user_override_beats_provider_default():
    p = providers.resolve({"base_url": _CN, "model_name": "MiniMax-M3"})
    caps = p.capabilities({"base_url": _CN, "model_name": "MiniMax-M3",
                           "context_window": 64_000})
    assert caps.context_window == 64_000


def test_unknown_model_falls_back_to_defaults():
    """DC1：未知模型（非 minimax）仍拿到与改造前一致的默认能力。"""
    cfg = {"base_url": "https://relay.example/v1", "model_name": "mystery-1"}
    p = providers.resolve(cfg)
    caps = p.capabilities(cfg)
    assert caps == DEFAULT_CAPABILITIES
