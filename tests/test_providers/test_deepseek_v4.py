"""A22: DeepSeek v4 补全 —— v4-flash/pro 识别、能力、effort、thinking、回传契约。

数值来自 A0 §7.1（2026-08-02 三方审计通过）。
"""

import pytest

from config.model_capabilities import DEFAULT_CAPABILITIES, ModelPricing
from core import providers
from core.providers.deepseek import DeepSeekProvider


def _resolve(model_name: str):
    cfg = {"base_url": "https://api.deepseek.com", "model_name": model_name,
           "resolved_max_tokens": 8192}
    return providers.resolve(cfg), cfg


def _caps(model_name: str):
    p, cfg = _resolve(model_name)
    return p.capabilities(cfg)


# ---- 完成判据 2：v4 识别 / 能力 / effort / thinking 与 §7.1 一致 ------------


@pytest.mark.parametrize("name", ["deepseek-v4-flash", "deepseek-v4-pro"])
def test_v4_matches(name):
    p = providers.resolve({"base_url": "https://api.deepseek.com", "model_name": name})
    assert isinstance(p, DeepSeekProvider)


def test_v4_context_and_output_s71():
    """§7.1 问 2：v4 1M context；max output 384K。"""
    for name in ("deepseek-v4-flash", "deepseek-v4-pro"):
        caps = _caps(name)
        assert caps.context_window == 1_048_576
        assert caps.max_output_tokens == 384_000


def test_v4_thinking_default_on_s71():
    """§7.1 问 5：v4 适配 thinking，默认开启，effort 默认 high。"""
    for name in ("deepseek-v4-flash", "deepseek-v4-pro"):
        caps = _caps(name)
        assert caps.supports_reasoning is True
        assert caps.thinking_default_on is True
        assert caps.accepts_temperature is False
        assert caps.effort_presets == {"fast": "low", "balanced": "high", "deep": "max"}


def test_v4_tools_s71():
    """§7.1 问 3：v4 全系支持 Tool Calls。"""
    for name in ("deepseek-v4-flash", "deepseek-v4-pro"):
        assert _caps(name).supports_function_calling is True


def test_v4_prompt_variant():
    """§7.1：v4-flash/pro 专属 prompt_variant。"""
    assert _caps("deepseek-v4-flash").prompt_variant == "deepseek-v4-flash"
    assert _caps("deepseek-v4-pro").prompt_variant == "deepseek-v4-pro"


def test_v4_usage_fields_s71():
    """§7.1 问 4：缓存命中顶层 prompt_cache_hit_tokens；reasoning_content 平铺。"""
    caps = _caps("deepseek-v4-flash")
    assert caps.usage_fields.cache_read_flat == ("prompt_cache_hit_tokens",)
    assert caps.usage_fields.reasoning == ("reasoning_content",)


# ---- 完成判据 3：tools + reasoning_content 回传契约 ------------------------


def test_to_openai_messages_echoes_reasoning_content():
    """带 tools 的轮次必须回传 reasoning_content（§7.1 问 5；否则 400）。"""
    from langchain_core.messages import AIMessage, ToolMessage
    from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2

    ai = AIMessage(
        content="thinking then answer",
        tool_calls=[{"id": "call_1", "name": "fetch", "args": {"url": "x"}}],
        additional_kwargs={"reasoning_content": "chain of thought"},
    )
    out = AgentV2._to_openai_messages(
        [ai, ToolMessage(content="ok", tool_call_id="call_1")]
    )
    assert out[0]["role"] == "assistant"
    assert out[0]["reasoning_content"] == "chain of thought"
    assert out[0]["tool_calls"][0]["id"] == "call_1"


def test_to_openai_messages_reasoning_from_attr():
    """reasoning_content 也可从消息属性取（非 additional_kwargs 时）。"""
    from langchain_core.messages import AIMessage
    from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2

    ai = AIMessage(content="answer", reasoning_content="cot via attr")
    out = AgentV2._to_openai_messages([ai])
    assert out[0]["reasoning_content"] == "cot via attr"


# ---- 完成判据 4：旧型号（deepseek-chat/reasoner）保持 A3 逻辑不回归 ---------


def test_legacy_chat_non_thinking_s71():
    """旧 deepseek-chat → non-thinking（A3 行为）；§7.1 过渡期指向 flash non-thinking。"""
    caps = _caps("deepseek-chat")
    assert caps.supports_reasoning is False
    assert caps.thinking_default_on is False
    assert caps.effort_presets == {}
    assert caps.context_window == 1_048_576  # 过渡期仍 1M


def test_legacy_reasoner_thinking_s71():
    """旧 deepseek-reasoner → thinking（A3 行为）；§7.1 过渡期指向 flash thinking。"""
    caps = _caps("deepseek-reasoner")
    assert caps.supports_reasoning is True
    assert caps.thinking_default_on is True
    assert caps.accepts_temperature is False


# ---- 完成判据 1：TODO 已填充；DC1/兜底 ------------------------------------


def test_deepseek_pricing_s71():
    """§7.1 问 7：v4-flash/pro 定价分条（USD，as_of=2026-08-02）。"""
    p, cfg = _resolve("deepseek-v4-flash")
    caps = p.capabilities(cfg)
    assert isinstance(caps.pricing, ModelPricing)
    assert caps.pricing.input_per_mtok == 0.14
    assert caps.pricing.output_per_mtok == 0.28
    assert caps.pricing.cached_input_per_mtok == 0.0028
    assert caps.pricing.as_of == "2026-08-02"
    assert caps.pricing.source_url


def test_unknown_deepseek_variant_conservative():
    """未调研变体不套用 v4 调研能力（DC1：max_output 保守 None）。"""
    caps = _caps("deepseek-unknown-x")
    assert caps.provider == "deepseek"
    assert caps.context_window == 1_048_576
    assert caps.max_output_tokens is None
    assert caps.pricing.input_per_mtok is None
