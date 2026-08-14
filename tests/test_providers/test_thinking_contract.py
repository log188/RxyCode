"""FXC5 · per-model thinking / echo contracts (PHASE-FIX §5 FXC5).

Covers the decision table rows with payload / serialized-message assertions:
- DeepSeek (mandatory_echo): echo reasoning_content only when tool_calls are
  present; plain-text assistant turns never get a forced reasoning field
- Kimi / MiMo / GLM (mandatory_echo): echo across user turns, empty allowed
- Qwen (no_thinking): reasoning_content is NEVER put back into messages
- GPT / Doubao / Grok (none): no raw CoT echo
- provider extra_body goldens (thinking/reasoning_effort/enable_thinking)
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2, _should_echo_reasoning


def _convert(msgs, reasoning_contract=None, provider_id=None):
    return AgentV2._to_openai_messages(
        msgs, reasoning_contract=reasoning_contract, provider_id=provider_id
    )


# ---------------------------------------------------------------------------
# echo decision helper (unit level)
# ---------------------------------------------------------------------------


def test_qwen_never_echoes_reasoning():
    assert _should_echo_reasoning("no_thinking", "qwen", True, "reasoning") is False
    assert _should_echo_reasoning("no_thinking", "qwen", False, "reasoning") is False


def test_none_contract_never_echoes():
    for provider in ("openai", "doubao", "grok"):
        assert _should_echo_reasoning("none", provider, True, "reasoning") is False


def test_deepseek_echoes_only_with_tool_calls():
    assert _should_echo_reasoning("mandatory_echo", "deepseek", True, "reasoning") is True
    assert _should_echo_reasoning("mandatory_echo", "deepseek", False, "reasoning") is False


def test_kimi_mimo_glm_echo_across_turns_empty_ok():
    for provider in ("kimi", "mimo", "glm"):
        assert _should_echo_reasoning("mandatory_echo", provider, False, "") is True
        assert _should_echo_reasoning("mandatory_echo", provider, True, "") is True


def test_unknown_contract_falls_back_to_old_behaviour():
    # legacy path keeps echoing captured reasoning when present
    assert _should_echo_reasoning(None, "deepseek", False, "reasoning") is True


# ---------------------------------------------------------------------------
# serialized messages (the wire contract)
# ---------------------------------------------------------------------------


def test_qwen_serialized_messages_never_contain_reasoning_content():
    msgs = [
        SystemMessage(content="SYS"),
        AIMessage(content="think then answer", reasoning_content="hidden chain"),
        HumanMessage(content="ok"),
    ]
    out = _convert(msgs, reasoning_contract="no_thinking", provider_id="qwen")
    assert all("reasoning_content" not in m for m in out)


def test_deepseek_plain_text_assistant_has_no_reasoning_field():
    msgs = [
        SystemMessage(content="SYS"),
        AIMessage(content="plain answer", reasoning_content="thinking but no tools"),
        HumanMessage(content="go on"),
    ]
    out = _convert(msgs, reasoning_contract="mandatory_echo", provider_id="deepseek")
    assistant = next(m for m in out if m["role"] == "assistant")
    assert "reasoning_content" not in assistant  # no tool_calls -> no echo


def test_deepseek_tool_call_echoes_reasoning():
    msgs = [
        SystemMessage(content="SYS"),
        AIMessage(
            content="",
            reasoning_content="decided to search",
            tool_calls=[
                {
                    "name": "websearch",
                    "args": {"q": "x"},
                    "id": "call_1",
                    "type": "tool_call",
                }
            ],
        ),
        HumanMessage(content="ok"),
    ]
    out = _convert(msgs, reasoning_contract="mandatory_echo", provider_id="deepseek")
    assistant = next(m for m in out if m["role"] == "assistant")
    assert assistant["reasoning_content"] == "decided to search"


def test_kimi_empty_reasoning_still_echoed():
    msgs = [
        SystemMessage(content="SYS"),
        AIMessage(content="ok", reasoning_content=""),
        HumanMessage(content="continue"),
    ]
    out = _convert(msgs, reasoning_contract="mandatory_echo", provider_id="kimi")
    assistant = next(m for m in out if m["role"] == "assistant")
    assert assistant.get("reasoning_content") == ""


def test_gpt_serialized_messages_no_reasoning_echo():
    msgs = [
        SystemMessage(content="SYS"),
        AIMessage(content="answer", reasoning_content="chain"),
        HumanMessage(content="ok"),
    ]
    out = _convert(msgs, reasoning_contract="none", provider_id="openai")
    assert all("reasoning_content" not in m for m in out)


# ---------------------------------------------------------------------------
# provider extra_body golden contracts
# ---------------------------------------------------------------------------


def _provider_llm_kwargs(provider_cls, model_name, model_config=None):
    from RxyCode.RxyCode1_1_0.config.model_capabilities import DEFAULT_CAPABILITIES

    caps = provider_cls().capabilities({"model_name": model_name})
    cfg = {
        "model_name": model_name,
        "effort": "balanced",
        "api_key": "sk-test",
        "resolved_max_tokens": 2048,
    }
    if model_config:
        cfg.update(model_config)
    return provider_cls().llm_kwargs(cfg, caps)


def test_mimo_sends_thinking_object_and_no_effort():
    from RxyCode.RxyCode1_1_0.core.providers.mimo import MIMOProvider

    kwargs = _provider_llm_kwargs(MIMOProvider, "mimo-v2.5-pro")
    body = kwargs.get("extra_body") or {}
    assert body.get("thinking") == {"type": "enabled"}
    assert "reasoning_effort" not in kwargs


def test_minimax_m3_sends_adaptive_thinking():
    from RxyCode.RxyCode1_1_0.core.providers.minimax import MiniMaxProvider

    kwargs = _provider_llm_kwargs(MiniMaxProvider, "minimax-m3")
    body = kwargs.get("extra_body") or {}
    assert body.get("thinking") == {"type": "adaptive"}


def test_qwen_sends_enable_thinking_not_type_disabled():
    from RxyCode.RxyCode1_1_0.core.providers.qwen import QwenProvider

    kwargs = _provider_llm_kwargs(QwenProvider, "qwen3.7-max")
    body = kwargs.get("extra_body") or {}
    assert body.get("enable_thinking") is True
    assert "thinking" not in body  # never {type: disabled}


def test_kimi_k3_sends_reasoning_effort_not_thinking_object():
    from RxyCode.RxyCode1_1_0.core.providers.kimi import KimiProvider

    kwargs = _provider_llm_kwargs(KimiProvider, "kimi-k3", {"effort": "max"})
    assert kwargs.get("reasoning_effort") == "max"
    body = kwargs.get("extra_body") or {}
    # k3 must not carry a thinking object ({type: enabled} 400s on k3)
    assert body.get("thinking") is None
