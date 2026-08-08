"""A21: per-model 延迟旋钮 —— effort_presets 消费 + thinking 适配判断。"""

import pytest

from config.model_capabilities import DEFAULT_CAPABILITIES, ModelCapabilities
from core import providers
from core.providers.base import BaseProvider


def _resolve(u, model, effort=None):
    cfg = {"base_url": u, "model_name": model, "resolved_max_tokens": 8192}
    if effort is not None:
        cfg["effort"] = effort
    p = providers.resolve(cfg)
    return p, cfg, p.capabilities(cfg)


# ---- 完成判据 1/6：默认档位 balanced，thinking_default_on 默认 False ---------


def test_thinking_default_on_default_false():
    """thinking_default_on 默认 False；未适配前行为与现状一致。"""
    assert DEFAULT_CAPABILITIES.thinking_default_on is False


def test_default_effort_balanced_no_extra():
    """默认（无 effort 键）→ 无额外注入（balanced=现状）。"""
    p, cfg, caps = _resolve("https://relay.example/v1", "mystery-1")
    kwargs = p.llm_kwargs(cfg, caps)
    assert "reasoning_effort" not in kwargs
    assert "thinking" not in (kwargs.get("extra_body") or {})


# ---- 完成判据 2/4：fast path 走 fast，deep 仅显式触发 ----------------------


def test_effort_for_fast_path_uses_fast():
    """fast path（简单查询 build）→ effort=fast。"""
    agent = _new_agent()
    assert agent._effort_for("build", "what is 2+2?") == "fast"


def test_effort_for_plan_balanced():
    """plan → balanced。"""
    agent = _new_agent()
    assert agent._effort_for("plan", "anything") == "balanced"


def test_effort_for_complex_build_balanced():
    """复杂 build（整库重构）→ balanced。"""
    agent = _new_agent()
    text = "refactor the entire codebase and migrate the whole project"
    assert agent._effort_for("build", text) == "balanced"


def test_deep_only_via_explicit_effort():
    """deep 只由显式配置触发（_effort_for 不自动返回 deep）。"""
    agent = _new_agent()
    assert agent._effort_for("build", "simple") != "deep"
    assert agent._effort_for("plan", "x") != "deep"


# ---- 完成判据 3：各 provider effort_presets 与 §7 一致 ----------------------


def test_deepseek_effort_presets_s71():
    """§7.1：DeepSeek v4 reasoning_effort low/high/max，默认 high。"""
    p, cfg, caps = _resolve("https://api.deepseek.com/v1", "deepseek-v4-flash")
    assert caps.effort_presets == {"fast": "low", "balanced": "high", "deep": "max"}


def test_openai_effort_presets_s72():
    """§7.2：OpenAI gpt-5.6 fast:low/balanced:medium/deep:high。"""
    p, cfg, caps = _resolve("https://api.openai.com/v1", "gpt-5.6-sol")
    assert caps.effort_presets["balanced"] == "medium"


def test_kimi_k3_effort_presets_s73():
    """§7.3：kimi-k3 fast:low/balanced:high/deep:max。"""
    p, cfg, caps = _resolve("https://api.moonshot.cn/v1", "kimi-k3")
    assert caps.effort_presets == {"fast": "low", "balanced": "high", "deep": "max"}


def test_glm52_effort_presets_s74():
    """§7.4：glm-5.2 fast:low/balanced:high/deep:max。"""
    p, cfg, caps = _resolve("https://open.bigmodel.cn/api/paas/v4/", "glm-5.2")
    assert caps.effort_presets == {"fast": "low", "balanced": "high", "deep": "max"}


@pytest.mark.parametrize("u,model", [
    ("https://api.minimaxi.com/v1", "MiniMax-M3"),
    ("https://api.xiaomimimo.com/v1", "mimo-v2.5-pro"),
    ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3.7-plus"),
    ("https://api.anthropic.com/v1", "claude-opus-5"),
])
def test_chat_path_no_effort_presets(u, model):
    """§7.5/7.6/7.7/7.8：Chat 路径无 reasoning.effort → effort_presets 空。"""
    p, cfg, caps = _resolve(u, model)
    assert caps.effort_presets == {}


# ---- 完成判据 5/6：thinking 适配判断 --------------------------------------


def test_thinking_default_on_matched_models():
    """适配 thinking 的模型 thinking_default_on=True（A12–A18 已填）。"""
    for u, model in [
        ("https://api.deepseek.com/v1", "deepseek-v4-flash"),
        ("https://api.openai.com/v1", "gpt-5.6-sol"),
        ("https://api.moonshot.cn/v1", "kimi-k3"),
        ("https://api.anthropic.com/v1", "claude-opus-5"),
    ]:
        p, cfg, caps = _resolve(u, model)
        assert caps.supports_reasoning is True
        assert caps.thinking_default_on is True


def test_effort_injected_only_when_presets_and_reasoning():
    """仅当 supports_reasoning + effort_presets 非空才注入 reasoning_effort。"""
    # OpenAI gpt-5.6-sol：有 presets + reasoning → 注入
    p, cfg, caps = _resolve("https://api.openai.com/v1", "gpt-5.6-sol", effort="fast")
    kwargs = p.llm_kwargs(cfg, caps)
    assert kwargs.get("reasoning_effort") == "low"


def test_empty_presets_no_injection():
    """effort_presets 空（如 mimo Chat）→ 不注入 reasoning_effort（零额外参数）。"""
    p, cfg, caps = _resolve("https://api.xiaomimimo.com/v1", "mimo-v2.5-pro", effort="fast")
    kwargs = p.llm_kwargs(cfg, caps)
    assert "reasoning_effort" not in kwargs


def test_thinking_default_off_no_thinking_injection():
    """thinking_default_on=False 的模型不注入 thinking 参数。"""
    caps = ModelCapabilities(supports_reasoning=True, thinking_default_on=False)
    p = BaseProvider()
    kwargs = p.llm_kwargs({"model_name": "x", "resolved_max_tokens": 8192}, caps)
    assert "thinking" not in (kwargs.get("extra_body") or {})


def test_thinking_default_on_injects_thinking():
    """thinking_default_on=True + reasoning → llm_kwargs 带 thinking 参数。"""
    caps = ModelCapabilities(
        supports_reasoning=True,
        thinking_default_on=True,
        effort_presets={"fast": "low", "balanced": "high", "deep": "max"},
    )
    p = BaseProvider()
    kwargs = p.llm_kwargs({"model_name": "x", "resolved_max_tokens": 8192,
                           "effort": "balanced"}, caps)
    body = kwargs.get("extra_body") or {}
    assert body.get("thinking") == {"type": "enabled"}
    assert kwargs.get("reasoning_effort") == "high"


def _new_agent():
    from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2

    agent = object.__new__(AgentV2)
    agent._capabilities = DEFAULT_CAPABILITIES
    agent._is_simple_query = AgentV2._is_simple_query.__get__(agent, AgentV2)
    return agent
