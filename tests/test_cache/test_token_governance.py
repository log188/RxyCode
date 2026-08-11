"""B6: token 治理 —— 工具输出截断 / per-model 输出上限 / 推理 few-shot 豁免 / 重复输出去重。

完成判据对应：
1. 工具输出截断（超长输出、JSON 结构保持、不污染前缀）
2. max_output_tokens 按模型解析（未知模型高位兜底，无全局 8192）
3. 推理模型不加 few-shot
4. 重复工具输出去重（结构化指纹）
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from config.model_capabilities import (
    DEFAULT_CAPABILITIES,
    ModelCapabilities,
)

from RxyCode.RxyCode1_1_0.config.model_limits import (
    UNKNOWN_MODEL_FALLBACK,
    resolve_output_limit,
)
from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2


def _new_agent(caps: ModelCapabilities = DEFAULT_CAPABILITIES):
    """轻量 AgentV2：跳过构造，直接测治理方法。"""
    agent = object.__new__(AgentV2)
    agent._capabilities = caps
    agent._tool_orchestrator = SimpleNamespace(get_all=lambda: {})
    agent._memory = SimpleNamespace(_rag_enabled=False)
    return agent


# ============================================================================
# 完成判据 1：工具输出截断（落地前、结构保持、不污染前缀）
# ============================================================================


def test_tool_output_max_chars_default_2000():
    """cache.tool_output_max_chars 默认 2000（opencode 2k 语义）。"""
    from RxyCode.RxyCode1_1_0.config.settings import _default_config

    assert _default_config()["cache"]["tool_output_max_chars"] == 2000


def test_truncate_tool_text_overlong_plain_text():
    """超长普通文本截断：长度 ≤ 2000 且带截断标记。"""
    agent = _new_agent()
    text = "word " * 2000  # 10000 chars
    out = agent._truncate_tool_text(text)
    assert len(out) <= 2000
    assert "[truncated]" in out
    assert out.startswith("word ")
    assert len(out) < len(text)


def test_truncate_tool_text_short_untouched():
    """≤ 2000 字符的文本原样返回（不截断）。"""
    agent = _new_agent()
    text = "short" * 100  # 500 chars
    assert agent._truncate_tool_text(text) == text


def test_truncate_tool_text_json_structure_preserved():
    """超长 JSON 截断后仍是合法 JSON（结构保持）。"""
    agent = _new_agent()
    payload = {
        "files": [
            {"name": f"file_{i:03d}.py", "lines": "x" * 500} for i in range(30)
        ]
    }
    text = json.dumps(payload)
    out = agent._truncate_tool_text(text)
    assert len(out) <= 2000
    parsed = json.loads(out)  # 必须合法 JSON
    assert isinstance(parsed, dict)
    assert "files" in parsed


def test_truncate_tool_text_json_short_untouched():
    """短 JSON 原样返回（结构不变）。"""
    agent = _new_agent()
    text = json.dumps({"name": "a.py", "lines": "hello"})
    assert agent._truncate_tool_text(text) == text


def test_truncate_tool_text_does_not_pollute_prefix():
    """截断只作用于新落地文本副本，不动已有消息（不污染前缀）。"""
    agent = _new_agent()
    original = "x" * 5000
    out = agent._truncate_tool_text(original)
    assert original == "x" * 5000  # 原始字符串未被改写
    assert out != original


def test_truncate_tool_text_honors_token_limit_too():
    """A20 token 维度仍生效：token 限制更严格时叠加截断。"""
    agent = _new_agent(ModelCapabilities(tool_output_token_limit=50))
    text = "word " * 1000
    out = agent._truncate_tool_text(text)
    from RxyCode.RxyCode1_1_0.core.agent_v2 import _estimate_tokens

    assert _estimate_tokens(out, agent._tokenizer_spec()) <= 50


def test_truncate_json_top_level_string_hard_bounded():
    """顶层长 JSON 字符串：截断后合法且 ≤ 2000（luna R1-1）。"""
    agent = _new_agent()
    text = json.dumps("x" * 5000)
    out = agent._truncate_tool_text(text)
    assert len(out) <= 2000
    assert json.loads(out) == "x" * (len(out) - 2)


def test_truncate_json_huge_number_hard_bounded():
    """顶层超长数字：退化为最小合法 JSON 且 ≤ limit（luna R1-1）。"""
    agent = _new_agent()
    text = json.dumps(int("9" * 3000))
    out = agent._truncate_tool_text(text)
    assert len(out) <= 2000
    json.loads(out)  # 合法


def test_truncate_json_long_key_hard_bounded():
    """超长 key：丢弃或最小化后仍 ≤ 2000 且合法（luna R1-1）。"""
    agent = _new_agent()
    text = json.dumps({("k" * 3000): "v"})
    out = agent._truncate_tool_text(text)
    assert len(out) <= 2000
    json.loads(out)  # 合法


def test_truncate_plain_tiny_limit_hard_bounded():
    """limit 小于截断标记时：纯头部截断，仍 ≤ limit（luna R1-2）。"""
    agent = _new_agent()
    # monkeypatch 字符上限为极小值，验证硬上限
    agent._tool_output_max_chars = lambda: 10
    text = "x" * 5000
    out = agent._truncate_tool_text(text)
    assert len(out) <= 10


def test_truncate_json_tiny_limit_hard_bounded():
    """极小字符上限下 JSON 截断仍合法且 ≤ limit（luna R1-2）。"""
    agent = _new_agent()
    agent._tool_output_max_chars = lambda: 5
    text = json.dumps({"name": "x" * 5000})
    out = agent._truncate_tool_text(text)
    assert len(out) <= 5
    json.loads(out)


def test_truncate_json_top_level_string_tiny_limit():
    """顶层 JSON 字符串在 limit=1/2 下仍 ≤ limit 且合法（luna R2-1）。"""
    agent = _new_agent()
    for limit in (1, 2):
        agent._tool_output_max_chars = lambda _l=limit: _l
        out = agent._truncate_tool_text(json.dumps("x" * 5000))
        assert len(out) <= limit
        json.loads(out)  # 合法 JSON


def test_truncate_json_top_level_empty_string_tiny_limit():
    """顶层空字符串在 limit=1 下仍 ≤ limit 且合法（luna R3-1）。"""
    agent = _new_agent()
    agent._tool_output_max_chars = lambda: 1
    out = agent._truncate_json_chars("", 1)
    assert len(out) <= 1
    json.loads(out)


def test_truncate_json_no_progress_loop_terminates():
    """值全 null 时 _minimize_values 返回 False，立即退化不空转（luna R4-1）。"""
    agent = _new_agent()
    out = agent._truncate_json_chars({"a": None}, 1)
    assert len(out) <= 1
    json.loads(out)


def test_truncate_json_long_key_dropped_keeps_structure():
    """超长 key 删除后保留容器结构（{} 而非退化标量）（luna R4-2）。"""
    agent = _new_agent()
    out = agent._truncate_json_chars({("k" * 3000): "v"}, 2000)
    assert json.loads(out) == {}  # 保留 dict 结构


def test_truncate_json_key_exactly_32_dropped():
    """整体超限时，长度恰好 32 的 key 也被删除（>=32 语义，luna R5-1）。

    构造：多个 32 字符 key（值 1 字符无法再截短）→ 整体超 2000 →
    值截断路径无进展 → 触发 _drop_long_keys 删除路径。
    """
    agent = _new_agent()
    payload = {f"k{i:02d}" + "x" * 29: "v" for i in range(60)}
    payload["keep"] = "keep"
    out = agent._truncate_json_chars(payload, 2000)
    parsed = json.loads(out)
    assert len(out) <= 2000
    assert "keep" in parsed
    assert len(parsed) < 61  # 至少删了一个 32 字符 key


def test_truncate_json_nested_long_key_dropped():
    """整体超限时，嵌套 dict 中的超长 key 也被删除（递归，luna R5-1）。"""
    agent = _new_agent()
    inner = {f"k{i:02d}" + "x" * 29: "v" for i in range(60)}
    inner["keep"] = "keep"
    payload = {"outer": {"inner": inner}}
    out = agent._truncate_json_chars(payload, 2000)
    parsed = json.loads(out)
    assert len(out) <= 2000
    assert "outer" in parsed
    assert "keep" in parsed["outer"]["inner"]
    assert len(parsed["outer"]["inner"]) < 61


def test_dedup_repeated_fingerprint_set_semantics():
    """A→B→A 场景：第二次 A 仍是重复（指纹集合而非最后一个，luna R5-2）。"""
    agent = _new_agent()
    agent._seen_tool_fingerprints = {}
    first = agent._dedupe_tool_output("read", '{"file": "a.py"}')
    second = agent._dedupe_tool_output("read", '{"file": "b.py"}')
    third = agent._dedupe_tool_output("read", '{"file": "a.py"}')
    assert first == '{"file": "a.py"}'
    assert second == '{"file": "b.py"}'
    assert "duplicate" in third.lower() or "重复" in third


def test_tool_output_max_chars_rejects_bool(monkeypatch):
    """bool 配置值视为非法 → None（不截断，luna R4-3）。"""
    from RxyCode.RxyCode1_1_0.core import agent_v2 as agent_v2_mod

    agent = _new_agent()
    monkeypatch.setattr(
        agent_v2_mod._settings,
        "load_config",
        lambda: {"cache": {"tool_output_max_chars": True}},
    )
    assert agent._tool_output_max_chars() is None


def test_dedup_uses_raw_output_not_truncated():
    """去重指纹基于原始输出：截断后相同但原始不同 → 不去重（luna R1-3）。"""
    agent = _new_agent()
    agent._seen_tool_fingerprints = {}
    # 两个原始输出差异在中间 3000 字符区（被截断区），头尾相同：
    # plain 截断（head + marker + tail）后两者完全相同。
    common_head = "H" * 1000
    common_tail = "T" * 1000
    long_a = common_head + "A" * 3000 + common_tail
    long_b = common_head + "B" * 3000 + common_tail
    truncated_a = agent._truncate_tool_text(long_a)
    truncated_b = agent._truncate_tool_text(long_b)
    # 截断后相同（差异区被截掉）
    assert truncated_a == truncated_b
    # 但指纹按原始输出计算 → 不同 → 不去重
    first = agent._dedupe_tool_output("read", long_a)
    second = agent._dedupe_tool_output("read", long_b)
    assert first == long_a
    assert second == long_b


# ============================================================================
# 完成判据 2：max_output_tokens 按模型解析（Phase 3 resolver）
# ============================================================================


def test_resolve_output_limit_catalog_exact():
    """目录精确命中 → 用目录的 max_output_tokens。"""
    res = resolve_output_limit(
        provider_id="deepseek",
        model_id="deepseek-chat",
        configured_max_tokens=None,
        catalog_record={
            "provider_id": "deepseek",
            "model_id": "deepseek-chat",
            "model_max_output_tokens": 8192,
            "model_context_window": 128_000,
        },
        provider_default=None,
        input_tokens=1000,
    )
    assert res.resolved_max_tokens == 8192
    assert res.source == "catalog_exact_provider"


def test_resolve_output_limit_unknown_model_high_fallback():
    """未知模型 → 高位兜底（32768），不是全局 8192。"""
    res = resolve_output_limit(
        provider_id="some-new-provider",
        model_id="brand-new-model",
        configured_max_tokens=None,
        catalog_record=None,
        provider_default=None,
        input_tokens=1000,
    )
    assert res.resolved_max_tokens == UNKNOWN_MODEL_FALLBACK
    assert res.source == "unknown_fallback"


def test_resolve_output_limit_never_8192_global():
    """未知模型兜底 ≠ 8192（Phase 3 已移除全局 8192）。"""
    res = resolve_output_limit(
        provider_id="p",
        model_id="m",
        configured_max_tokens=None,
        catalog_record=None,
        provider_default=None,
        input_tokens=100,
    )
    assert res.resolved_max_tokens != 8192


def test_resolve_output_limit_provider_default():
    """provider 能力上限在无目录时兜底。"""
    res = resolve_output_limit(
        provider_id="p",
        model_id="m",
        configured_max_tokens=None,
        catalog_record=None,
        provider_default=16384,
        input_tokens=100,
    )
    assert res.resolved_max_tokens == 16384
    assert res.source == "provider_default"


def test_raw_stream_uses_resolver_not_global_8192():
    """_raw_stream 的 max_tokens 走 _resolve_request_max_tokens（resolver）。"""
    agent = _new_agent()
    agent.model_config = {"model_name": "brand-new-model"}
    agent._resolved_limits = None  # 强制走 retry 解析路径
    agent._capabilities = None  # 未知模型
    import inspect

    sig = inspect.signature(AgentV2._raw_stream)
    assert "max_tokens" in sig.parameters  # keep-alive 参数契约保留
    # _resolve_request_max_tokens 未知模型时兜底 32768（非 8192）
    val = agent._resolve_request_max_tokens(100)
    assert val == UNKNOWN_MODEL_FALLBACK


# ============================================================================
# 完成判据 3：推理模型不加 few-shot
# ============================================================================


def test_include_few_shot_reasoning_model_off():
    """supports_reasoning=True + 未显式配置 → 不加 few-shot。"""
    agent = _new_agent(ModelCapabilities(supports_reasoning=True))
    assert agent._include_few_shot() is False


def test_include_few_shot_non_reasoning_default_on():
    """supports_reasoning=False（默认）→ 现状不变，加 few-shot。"""
    agent = _new_agent(DEFAULT_CAPABILITIES)
    assert agent._include_few_shot() is True


def test_include_few_shot_reasoning_explicit_policy_wins():
    """推理模型显式 few_shot_policy="full" → 尊重显式配置。"""
    agent = _new_agent(
        ModelCapabilities(supports_reasoning=True, few_shot_policy="full")
    )
    assert agent._include_few_shot() is True


def test_include_few_shot_reasoning_explicit_none_policy():
    """推理模型显式 few_shot_policy="none" → 不加。"""
    agent = _new_agent(
        ModelCapabilities(supports_reasoning=True, few_shot_policy="none")
    )
    assert agent._include_few_shot() is False


# ============================================================================
# 完成判据 4：重复工具输出去重（结构化指纹）
# ============================================================================


def test_dedup_fingerprint_json_key_order_insensitive():
    """结构化指纹：JSON key 顺序不同但结构相同 → 同一指纹。"""
    agent = _new_agent()
    a = json.dumps({"name": "x", "lines": 3})
    b = json.dumps({"lines": 3, "name": "x"})
    assert agent._tool_output_fingerprint(a) == agent._tool_output_fingerprint(b)


def test_dedup_fingerprint_distinct_content_differs():
    """内容不同 → 指纹不同。"""
    agent = _new_agent()
    assert (
        agent._tool_output_fingerprint('{"name": "a"}')
        != agent._tool_output_fingerprint('{"name": "b"}')
    )


def test_dedup_fingerprint_timestamp_logs_not_folded():
    """带时间戳日志：字节不同 → 指纹不同（不误伤去重）。"""
    agent = _new_agent()
    t1 = json.dumps({"ts": "2026-08-10T10:00:00", "msg": "tick"})
    t2 = json.dumps({"ts": "2026-08-10T10:00:01", "msg": "tick"})
    assert agent._tool_output_fingerprint(t1) != agent._tool_output_fingerprint(t2)


def test_dedup_tool_output_second_call_placeholder():
    """同工具同指纹第二次出现 → 占位符替换，不重复进历史。"""
    agent = _new_agent()
    agent._seen_tool_fingerprints = {}
    first = agent._dedupe_tool_output("read", '{"file": "a.py"}')
    second = agent._dedupe_tool_output("read", '{"file": "a.py"}')
    assert first == '{"file": "a.py"}'  # 首次原样
    assert "duplicate" in second.lower() or "重复" in second  # 第二次占位符


def test_dedup_tool_output_distinct_content_kept():
    """同工具不同指纹 → 两次都保留。"""
    agent = _new_agent()
    agent._seen_tool_fingerprints = {}
    first = agent._dedupe_tool_output("read", '{"file": "a.py"}')
    second = agent._dedupe_tool_output("read", '{"file": "b.py"}')
    assert first == '{"file": "a.py"}'
    assert second == '{"file": "b.py"}'


def test_dedup_tool_output_different_tools_kept():
    """不同工具相同内容 → 不去重（各自保留）。"""
    agent = _new_agent()
    agent._seen_tool_fingerprints = {}
    first = agent._dedupe_tool_output("read", '{"v": 1}')
    second = agent._dedupe_tool_output("grep", '{"v": 1}')
    assert first == '{"v": 1}'
    assert second == '{"v": 1}'


def test_dedup_tool_output_plain_text_fingerprint():
    """非 JSON 文本：按文本指纹去重（内容相同才去重）。"""
    agent = _new_agent()
    agent._seen_tool_fingerprints = {}
    first = agent._dedupe_tool_output("ls", "a.py\nb.py")
    second = agent._dedupe_tool_output("ls", "a.py\nb.py")
    assert first == "a.py\nb.py"
    assert "duplicate" in second.lower() or "重复" in second
