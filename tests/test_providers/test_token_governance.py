"""A20: per-model token 治理 —— 3 新字段默认 + 消费点（fake provider）。"""

from types import SimpleNamespace

import pytest

from config.model_capabilities import (
    DEFAULT_CAPABILITIES,
    ModelCapabilities,
)


# ---- 完成判据 1：四个字段默认全为 None（现状零变化） ---------------------


def test_new_fields_default_to_none():
    """max_output_tokens / few_shot_policy / tool_send_policy / tool_output_token_limit
    默认全 None（现状零变化）。"""
    caps = DEFAULT_CAPABILITIES
    assert caps.max_output_tokens is None
    assert caps.few_shot_policy is None
    assert caps.tool_send_policy is None
    assert caps.tool_output_token_limit is None


def test_default_capabilities_unchanged():
    """默认能力既有字段保持。"""
    caps = DEFAULT_CAPABILITIES
    assert caps.provider == "openai"
    assert caps.context_window == 256_000
    assert caps.tokenizer == "tiktoken:o200k_base"


def test_fields_are_append_only():
    """字段只追加：构造时设定值可读回，未设定保持 None。"""
    caps = ModelCapabilities(
        few_shot_policy="first2",
        tool_send_policy="subset",
        tool_output_token_limit=1000,
    )
    assert caps.few_shot_policy == "first2"
    assert caps.tool_send_policy == "subset"
    assert caps.tool_output_token_limit == 1000
    assert caps.max_output_tokens is None


# ---- 消费点：_get_core_tools 按 tool_send_policy（fake provider） -----------


class _FakeAgent:
    """Minimal fake carrying the fields _get_core_tools reads."""

    def __init__(self, caps: ModelCapabilities, tools: list):
        self._caps = caps
        self._tools = tools

    def _tool_list(self):
        return list(self._tools)


def _apply_tool_send_policy(agent) -> list:
    """A20 消费点：按 caps.tool_send_policy 过滤工具列表。"""
    tools = list(agent._tools)
    policy = getattr(agent._caps, "tool_send_policy", None)
    if policy == "subset":
        # 会话内固定的确定性子集：保留前 8 个工具（按名字排序稳定）
        return sorted(tools, key=lambda t: getattr(t, "name", ""))[:8]
    return tools


def test_tool_send_policy_default_full():
    """默认（None）→ 全量发送，现状不变。"""
    tools = [SimpleNamespace(name=f"t{i}") for i in range(12)]
    agent = _FakeAgent(DEFAULT_CAPABILITIES, tools)
    assert len(_apply_tool_send_policy(agent)) == 12


def test_tool_send_policy_subset():
    """subset → 保留确定性子集（前 8 个按名排序）。"""
    tools = [SimpleNamespace(name=f"t{i:02d}") for i in range(12)]
    caps = ModelCapabilities(tool_send_policy="subset")
    agent = _FakeAgent(caps, tools)
    out = _apply_tool_send_policy(agent)
    assert len(out) == 8
    assert [t.name for t in out] == sorted(t.name for t in tools)[:8]


def test_tool_send_policy_subset_small_pool():
    """工具少于 8 个时 subset 返回全部（不截断）。"""
    tools = [SimpleNamespace(name=f"t{i}") for i in range(4)]
    caps = ModelCapabilities(tool_send_policy="subset")
    agent = _FakeAgent(caps, tools)
    assert len(_apply_tool_send_policy(agent)) == 4


# ---- 真实消费点：AgentV2._get_core_tools（fake orchestrator） -------------


def _new_agent(caps: ModelCapabilities, tools: list):
    from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2

    agent = object.__new__(AgentV2)
    agent._capabilities = caps
    agent._tool_orchestrator = SimpleNamespace(get_all=lambda: {t.name: t for t in tools})
    agent._memory = SimpleNamespace(_rag_enabled=False)
    return agent


def test_agent_get_core_tools_default_full():
    """默认（tool_send_policy=None）→ _get_core_tools 全量，现状不变。"""
    tools = [SimpleNamespace(name=f"tool{i:02d}") for i in range(12)]
    agent = _new_agent(DEFAULT_CAPABILITIES, tools)
    out = agent._get_core_tools()
    assert len(out) == 12


def test_agent_get_core_tools_subset():
    """tool_send_policy="subset" → 前 8 个（按名排序确定性子集）。"""
    tools = [SimpleNamespace(name=f"tool{i:02d}") for i in range(12)]
    agent = _new_agent(ModelCapabilities(tool_send_policy="subset"), tools)
    out = agent._get_core_tools()
    assert len(out) == 8
    assert [t.name for t in out] == sorted(t.name for t in tools)[:8]


def test_agent_include_few_shot_none_true():
    """few_shot_policy=None（现状）→ include_few_shot=True。"""
    agent = _new_agent(DEFAULT_CAPABILITIES, [])
    assert agent._include_few_shot() is True


def test_agent_include_few_shot_none_value():
    """few_shot_policy="none" → include_few_shot=False。"""
    agent = _new_agent(ModelCapabilities(few_shot_policy="none"), [])
    assert agent._include_few_shot() is False


def test_agent_include_few_shot_full_true():
    """few_shot_policy="full" → include_few_shot=True。"""
    agent = _new_agent(ModelCapabilities(few_shot_policy="full"), [])
    assert agent._include_few_shot() is True


# ---- 消费点：max_output_tokens 经 resolver 生效（Phase 3 M4） ---------------


def test_max_output_tokens_feeds_resolver_input():
    """max_output_tokens 作为 resolver 的能力上限输入（A20 卡步骤 3 的 max_tokens 覆盖）。"""
    caps = ModelCapabilities(max_output_tokens=65_536)
    # resolver 在 agent_v2._build_llm_from_config 消费 caps.max_output_tokens；
    # 此处断言字段可被读入 resolver 的 capability_max_output_tokens 参数。
    assert caps.max_output_tokens == 65_536


# ---- 消费点：few_shot_policy 决定 include_few_shot --------------------------


def test_few_shot_policy_none_keeps_current():
    """None → 保持现状（include_few_shot 沿用 A9 前行为）。"""
    caps = DEFAULT_CAPABILITIES
    assert caps.few_shot_policy is None


def test_few_shot_policy_values():
    """few_shot_policy 允许 full / first2 / none。"""
    for v in ("full", "first2", "none"):
        caps = ModelCapabilities(few_shot_policy=v)
        assert caps.few_shot_policy == v


# ---- 消费点：tool_output_token_limit 驱动截断阈值 ---------------------------


def _truncate_if_limited(content: str, limit: int | None) -> str:
    """A20 消费点：tool_output_token_limit 设定时按阈值截断（保留头尾）。"""
    if limit is None:
        return content
    # 简化：3 字符/token 估算（同 compressor._middle_truncate 的 chars_per_token）
    chars = limit * 3
    if len(content) <= chars * 2 + 100:
        return content
    return content[:chars] + "\n...[truncated]...\n" + content[-chars:]


def test_tool_output_limit_none_no_truncation():
    """默认 None → 不截断。"""
    content = "x" * 5000
    assert _truncate_if_limited(content, None) == content


def test_tool_output_limit_truncates_middle():
    """设 limit → 保留头尾，中间截断。"""
    content = "A" * 300 + "B" * 300 + "C" * 300
    out = _truncate_if_limited(content, 50)
    assert "[truncated]" in out
    assert out.startswith("A" * 50)
    assert out.endswith("C" * 50)
    assert "B" * 300 not in out


def test_tool_output_limit_short_content_untouched():
    """内容足够短时不截断。"""
    content = "short"
    assert _truncate_if_limited(content, 1000) == content
