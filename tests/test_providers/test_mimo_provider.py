"""MIMOProvider 显式能力测试（A16）：匹配、能力声明、定价、usage 提取。

数值全部来自 A0 批 6 调研报告（§7.6，2026-08-02 三方审计通过）。
主路径 = Chat Completions。双主力 mimo-v2.5-pro + mimo-v2.5 都必须覆盖。
"""

import pytest

from config.model_capabilities import DEFAULT_CAPABILITIES, ModelPricing
from core import providers
from core.providers.mimo import MIMOProvider

_API = "https://api.xiaomimimo.com/v1"


def _resolve(model_name: str, base_url: str = _API):
    cfg = {"base_url": base_url, "model_name": model_name, "resolved_max_tokens": 8192}
    return providers.resolve(cfg), cfg


def _caps(model_name: str, base_url: str = _API):
    p, cfg = _resolve(model_name, base_url)
    return p.capabilities(cfg)


# ---- 匹配正反例 ---------------------------------------------------------


@pytest.mark.parametrize("cfg", [
    {"base_url": _API, "model_name": "mimo-v2.5-pro"},
    {"base_url": "https://mimo.mi.com/v1", "model_name": "mimo-v2.5"},
    {"base_url": "https://relay.example/v1", "model_name": "mimo-v2.5-pro"},
])
def test_matches_by_url_or_model_name(cfg):
    assert isinstance(providers.resolve(cfg), MIMOProvider)


def test_does_not_match_broad_mimo_url():
    # §7.6 ③：仅 xiaomimimo / mimo.mi.com url 命中；「mimo」in url 会误伤第三方网关
    p = providers.resolve({"base_url": "https://api.somemimo.example/v1",
                           "model_name": "x"})
    assert not isinstance(p, MIMOProvider)


def test_mimo_v_prefix_not_matched():
    """§7.6 ③ 仅认 mimo- 前缀；mimo_v 不在授权匹配范围。"""
    p = providers.resolve({"base_url": "https://relay.example/v1",
                           "model_name": "mimo_v2"})
    assert not isinstance(p, MIMOProvider)


@pytest.mark.parametrize("cfg", [
    {"base_url": "https://api.deepseek.com/v1", "model_name": "deepseek-chat"},
    {"base_url": "https://api.openai.com/v1", "model_name": "gpt-5.6-sol"},
    {"base_url": "https://api.moonshot.cn/v1", "model_name": "kimi-k3"},
    {"base_url": "https://api.minimaxi.com/v1", "model_name": "MiniMax-M3"},
    {"base_url": "https://ark.cn-beijing.volces.com/api/coding/v3", "model_name": "glm-5.2"},
])
def test_does_not_steal_other_models(cfg):
    assert not isinstance(providers.resolve(cfg), MIMOProvider)


def test_resolve_returns_mimo_for_mimo_config():
    p = providers.resolve({"base_url": _API, "model_name": "mimo-v2.5-pro"})
    assert isinstance(p, MIMOProvider)


# ---- §7.6 ③：共用骨架（两主力相同） --------------------------------------


@pytest.mark.parametrize("name", ["mimo-v2.5-pro", "mimo-v2.5"])
def test_shared_window_and_caps(name):
    """§7.6 ③：两主力共用 1M/128K 启发式、FC/reasoning/thinking/prompt_cache。"""
    caps = _caps(name)
    assert caps.provider == "mimo"
    assert caps.context_window == 1_048_576
    assert caps.max_output_tokens == 131_072
    assert caps.supports_function_calling is True
    assert caps.supports_reasoning is True
    assert caps.thinking_default_on is True
    assert caps.supports_prompt_cache is True
    assert caps.tokenizer == "chars:1.5"


def test_thinking_mode_forces_sampling_defaults():
    """§7.6 问 5：思考模式 temperature/top_p 强制 1.0/0.95 → 不注入自定义采样参数。"""
    caps = _caps("mimo-v2.5-pro")
    assert caps.accepts_temperature is False
    p, cfg = _resolve("mimo-v2.5-pro")
    kwargs = p.llm_kwargs(cfg, caps)
    assert "temperature" not in kwargs
    assert "top_p" not in kwargs


# ---- §7.6 ③：双主力差异（vision / variant / 定价） ------------------------


def test_pro_is_text_only():
    caps = _caps("mimo-v2.5-pro")
    assert caps.supports_vision is False
    assert caps.prompt_variant == "mimo-v2.5-pro"


def test_v25_is_multimodal():
    """§7.6 ③ 主力 B：mimo-v2.5 原生全模态（文本+图像+视频+音频）。"""
    caps = _caps("mimo-v2.5")
    assert caps.supports_vision is True
    assert caps.prompt_variant == "mimo-v2.5"


# ---- §7.6 问 4：usage 嵌套 cached_tokens ---------------------------------


def test_cache_read_uses_nested_cached_tokens():
    """§7.6 问 4：usage.prompt_tokens_details.cached_tokens（嵌套），非平铺。"""
    p = providers.resolve({"base_url": _API, "model_name": "mimo-v2.5-pro"})
    caps = p.capabilities({"base_url": _API, "model_name": "mimo-v2.5-pro"})
    assert caps.usage_fields.cache_read_flat == ()
    assert caps.usage_fields.cache_read_nested == (("prompt_tokens_details", "cached_tokens"),)
    assert caps.usage_fields.reasoning == ()
    assert caps.usage_fields.reasoning_nested == (
        ("completion_tokens_details", "reasoning_tokens"),
    )
    assert p.extract_cache_read(
        {"prompt_tokens_details": {"cached_tokens": 64}}, caps
    ) == 64
    assert p.extract_cache_read({"cached_tokens": 99}, caps) == 0


# ---- §7.6 问 7：定价按型号分条（CNY） -----------------------------------


@pytest.mark.parametrize("name,inp,outp,cached", [
    ("mimo-v2.5-pro", 3.00, 6.00, 0.025),
    ("mimo-v2.5", 1.00, 2.00, 0.02),
    ("mimo-v2.5-pro-ultraspeed", 9.0, 18.0, 0.075),
])
def test_per_model_pricing(name, inp, outp, cached):
    """§7.6 问 7：定价按型号分条；cache_write 限时免费 → None。"""
    caps = _caps(name)
    assert isinstance(caps.pricing, ModelPricing)
    assert caps.pricing.input_per_mtok == inp
    assert caps.pricing.output_per_mtok == outp
    assert caps.pricing.cached_input_per_mtok == cached
    assert caps.pricing.cache_write_per_mtok is None
    assert caps.pricing.as_of == "2026-08-02"
    assert caps.pricing.source_url


def test_ultraspeed_not_default_mainstay():
    """§7.6 ③/问 8：UltraSpeed 是独立型号（非 service_tier 字段），能力窗口同 pro。"""
    caps = _caps("mimo-v2.5-pro-ultraspeed")
    assert caps.context_window == 1_048_576
    assert caps.supports_vision is False
    assert caps.prompt_variant == "mimo-v2.5-pro-ultraspeed"


def test_unknown_mimo_variant_stays_conservative():
    """未调研型号不套用调研能力：仅 provider/usage/pricing 变化，能力字段保守。"""
    for name in ["mimo-v1", "mimo-unknown-variant", "mimo-v2"]:
        caps = _caps(name)
        assert caps.provider == "mimo"
        assert caps.context_window == DEFAULT_CAPABILITIES.context_window == 256_000
        assert caps.max_output_tokens is None
        assert caps.supports_reasoning is False
        assert caps.supports_vision is False
        assert caps.prompt_variant == DEFAULT_CAPABILITIES.prompt_variant == "default"


# ---- DC1 / 用户覆盖 / llm_kwargs -----------------------------------------


def test_user_override_beats_provider_default():
    p = providers.resolve({"base_url": _API, "model_name": "mimo-v2.5-pro"})
    caps = p.capabilities({"base_url": _API, "model_name": "mimo-v2.5-pro",
                           "context_window": 64_000})
    assert caps.context_window == 64_000


def test_llm_kwargs_injects_chat_thinking():
    """§7.6 ③：Chat thinking 经 extra_body thinking.enabled。"""
    p, cfg = _resolve("mimo-v2.5-pro")
    caps = p.capabilities(cfg)
    kwargs = p.llm_kwargs(cfg, caps)
    body = kwargs.get("extra_body") or {}
    assert body.get("thinking") == {"type": "enabled"}


def test_unknown_model_falls_back_to_defaults():
    """DC1：未知模型（非 mimo）仍拿到与改造前一致的默认能力。"""
    cfg = {"base_url": "https://relay.example/v1", "model_name": "mystery-1"}
    p = providers.resolve(cfg)
    caps = p.capabilities(cfg)
    assert caps == DEFAULT_CAPABILITIES
