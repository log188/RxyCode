"""FXC1: lock cache_contract fields to vendor docs (research §16)."""

from __future__ import annotations

import json
from pathlib import Path

from RxyCode.RxyCode1_1_0.core.catalog import (
    get_contract,
    read_cached_tokens,
    reset_contract_cache,
)

CATALOG = Path(__file__).resolve().parents[2] / "config" / "model_catalog.json"

_SCHEMA_MODES = frozenset(
    {"auto", "explicit_breakpoints", "cache_key", "auto_and_key"}
)


def _records():
    return json.loads(CATALOG.read_text(encoding="utf-8"))["records"]


def _one(provider: str, model: str) -> dict:
    for r in _records():
        if r.get("provider_id") == provider and r.get("model_id") == model:
            return r
    raise AssertionError(f"missing record {provider}:{model}")


def test_luna_ttl_is_30m_not_24h():
    reset_contract_cache()
    c = get_contract("openai", "gpt-5.6-luna")
    assert c["cache_ttl_hours"] == 0.5
    assert c["breakpoints_max"] == 0
    assert c["cache_mode"] == "cache_key"
    assert c["usage_fields"]["cached"] == "prompt_tokens_details.cached_tokens"
    assert c["usage_fields"]["cached_alt"] == "cached_input_tokens"


def test_luna_cached_tokens_max_of_flat_and_nested():
    reset_contract_cache()
    assert read_cached_tokens("openai", "gpt-5.6-luna", {"cached_input_tokens": 800}) == 800
    assert read_cached_tokens(
        "openai",
        "gpt-5.6-luna",
        {"prompt_tokens_details": {"cached_tokens": 500}},
    ) == 500
    assert read_cached_tokens(
        "openai",
        "gpt-5.6-luna",
        {
            "cached_input_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 900},
        },
    ) == 900


def test_zen_luna_has_aligned_contract():
    reset_contract_cache()
    c = get_contract("zen", "gpt-5.6-luna")
    assert c is not None
    assert c["cache_mode"] == "cache_key"
    assert c["cache_ttl_hours"] == 0.5
    assert c["breakpoints_max"] == 0
    assert c["usage_fields"]["cached_alt"] == "cached_input_tokens"


def test_kimi_ttl_is_null():
    reset_contract_cache()
    assert get_contract("kimi", "kimi-k3")["cache_ttl_hours"] is None
    assert get_contract("kimi", "kimi-k2.7-code")["cache_ttl_hours"] is None


def test_kimi_k27_thinking_param_not_effort():
    sample = str(_one("kimi", "kimi-k2.7-code")["cache_contract"].get("thinking_param", {}))
    assert "reasoning_effort" not in sample
    assert "keep:all" in sample.replace(" ", "") or "keep: all" in sample


def test_minimax_m3_is_auto_zero_breakpoints():
    c = _one("minimax", "minimax-m3")["cache_contract"]
    assert c["cache_mode"] == "auto"
    assert c["breakpoints_max"] == 0
    blob = str(c.get("thinking_param", {})).lower()
    assert "enabled" not in blob or "adaptive" in blob


def test_claude_min_tokens():
    assert _one("anthropic", "claude-sonnet-4.5")["cache_contract"]["min_cache_tokens"] == 1024
    assert _one("anthropic", "claude-haiku-4.5")["cache_contract"]["min_cache_tokens"] == 4096


def test_glm_discount_and_window():
    r = _one("glm", "glm-5.2")
    assert abs(r["cache_contract"]["cache_hit_discount"] - 0.186) < 1e-6
    assert r["model_context_window"] == 1048576


def test_mimo_context_window():
    assert _one("mimo", "mimo-v2.5-pro")["model_context_window"] == 1048576
    assert _one("mimo", "mimo-v2.5")["model_context_window"] == 1048576


def test_qwen_thinking_and_cache_creation():
    for model in ("qwen3.7-max", "qwen3.8-max-preview"):
        c = _one("qwen", model)["cache_contract"]
        sample = str(c.get("thinking_param", {})).lower()
        assert "enable_thinking" in sample
        assert "type: disabled" not in sample
        assert c["usage_fields"]["cache_creation"] == "cache_creation_input_tokens"
    preview = str(_one("qwen", "qwen3.8-max-preview")["cache_contract"].get("thinking_param", {})).lower()
    assert "forbidden" in preview or "禁止" in preview


def test_doubao_record_exists_auto():
    reset_contract_cache()
    c = get_contract("doubao", "doubao-seed-2.1-turbo")
    assert c is not None
    assert c["cache_mode"] == "auto"
    assert c["breakpoints_max"] == 0
    assert c.get("prompt_cache_key_required") is False


def test_deepseek_stays_implicit_auto():
    reset_contract_cache()
    for model in ("deepseek-v4-flash", "deepseek-v4-pro"):
        c = get_contract("deepseek", model)
        assert c["cache_mode"] == "auto"
        assert c["breakpoints_max"] in (0, None)
        assert c.get("prompt_cache_key_required") is False


def test_no_cache_mode_aliases():
    for r in _records():
        contract = r.get("cache_contract")
        if not contract:
            continue
        mode = contract.get("cache_mode")
        assert mode in _SCHEMA_MODES, f"{r['provider_id']}:{r['model_id']} mode={mode}"
        assert mode not in {"explicit", "breakpoints"}
