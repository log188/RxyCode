"""FXC4 · session affinity headers + DeepSeek dual-field usage + later compaction.

Coverage per PHASE-FIX §5 FXC4 acceptance:
- Go-gateway requests carry session affinity headers (x-opencode-session +
  x-session-affinity / X-Session-Id); direct official endpoints send only
  X-Session-Id and never fake opencode* headers
- DeepSeek usage fixtures: nested-only and flat-only both read; both present
  -> max (via catalog.read_cached_tokens, FXC1 max path)
- compaction threshold: the old ~90% trigger (943_718) no longer fires early
  on the 1M window; v4 caps move to ~0.97x
"""

from __future__ import annotations

from RxyCode.RxyCode1_1_0.core.catalog import read_cached_tokens, reset_contract_cache


# ---------------------------------------------------------------------------
# session affinity headers
# ---------------------------------------------------------------------------


def _headers(base_url: str, session_id: str = "ses_test123") -> dict:
    from RxyCode.RxyCode1_1_0.core.agent_v2 import build_session_headers

    return build_session_headers(base_url, session_id)


def test_go_gateway_carries_full_affinity_headers():
    headers = _headers("https://opencode.ai/zen/go/v1")
    assert headers["x-opencode-session"] == "ses_test123"
    assert headers["x-session-affinity"] == "ses_test123"
    assert headers["X-Session-Id"] == "ses_test123"


def test_zen_gateway_carries_full_affinity_headers():
    headers = _headers("https://opencode.ai/zen/v1")
    assert headers["x-opencode-session"] == "ses_test123"
    assert headers["X-Session-Id"] == "ses_test123"


def test_direct_official_api_only_sends_session_id():
    headers = _headers("https://api.deepseek.com/v1")
    assert headers == {"X-Session-Id": "ses_test123"}
    assert "x-opencode-session" not in headers  # never fake opencode* headers
    assert "x-session-affinity" not in headers


def test_http_base_url_without_gateway_is_direct():
    headers = _headers("https://api.anthropic.com/v1")
    assert headers == {"X-Session-Id": "ses_test123"}


def test_empty_session_id_still_shapes_headers():
    headers = _headers("https://opencode.ai/zen/go/v1", session_id="")
    assert headers["x-opencode-session"] == ""
    assert headers["X-Session-Id"] == ""


def test_vendor_path_containing_go_or_zen_never_fakes_opencode_headers():
    # a path segment saying /go or /zen on a vendor host is NOT the gateway
    assert _headers("https://api.deepseek.com/v1/go") == {"X-Session-Id": "ses_test123"}
    assert _headers("https://api.openai.com/v1/zen") == {"X-Session-Id": "ses_test123"}
    assert _headers("https://api.anthropic.com/v1/go/chat") == {"X-Session-Id": "ses_test123"}
    assert "x-opencode-session" not in _headers("https://api.deepseek.com/v1/go")
    assert "x-session-affinity" not in _headers("https://api.deepseek.com/v1/go")


def test_build_llm_injects_session_headers_into_chatopenai(monkeypatch):
    """The ChatOpenAI constructor receives default_headers from the gateway
    decision (captured via a fake provider, no network)."""
    from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2

    captured: dict = {}

    class _FakeProvider:
        name = "openai"

        def capabilities(self, model_config):  # noqa: ARG002
            from RxyCode.RxyCode1_1_0.config.model_capabilities import (
                DEFAULT_CAPABILITIES,
            )

            return DEFAULT_CAPABILITIES

        def llm_kwargs(self, model_config, caps):  # noqa: ARG002
            captured["model_config"] = dict(model_config)
            return {"model": "x", "api_key": "sk-test"}

    def fake_resolve(model_config):
        captured["model_config"] = dict(model_config)
        return _FakeProvider()

    import RxyCode.RxyCode1_1_0.core.agent_v2 as av2

    monkeypatch.setattr(av2.providers, "resolve", fake_resolve)
    monkeypatch.setattr(
        "langchain_openai.ChatOpenAI",
        lambda **kwargs: captured.setdefault("kwargs", kwargs),
    )

    agent = AgentV2.__new__(AgentV2)
    agent._session_id = "ses_test123"
    agent._rate_limiter = None
    agent._rate_limit_timeout = None
    agent._rate_provider = None
    agent._rate_model = None
    agent._rate_reserved_output_tokens = 0

    agent._build_llm_from_config(
        {
            "base_url": "https://opencode.ai/zen/go/v1",
            "api_key": "sk-test",
            "model_name": "deepseek/deepseek-v4-flash",
        }
    )
    headers = captured["kwargs"].get("default_headers") or {}
    assert headers.get("x-opencode-session") == "ses_test123"
    assert headers.get("X-Session-Id") == "ses_test123"


# ---------------------------------------------------------------------------
# DeepSeek dual-field usage (catalog max path)
# ---------------------------------------------------------------------------


def test_deepseek_nested_only_reads():
    reset_contract_cache()
    usage = {"prompt_tokens_details": {"cached_tokens": 500}}
    assert read_cached_tokens("deepseek", "deepseek-v4-flash", usage) == 500


def test_deepseek_flat_only_reads():
    reset_contract_cache()
    usage = {"prompt_cache_hit_tokens": 800}
    assert read_cached_tokens("deepseek", "deepseek-v4-flash", usage) == 800


def test_deepseek_both_present_takes_max():
    reset_contract_cache()
    usage = {
        "prompt_cache_hit_tokens": 100,
        "prompt_tokens_details": {"cached_tokens": 900},
    }
    assert read_cached_tokens("deepseek", "deepseek-v4-flash", usage) == 900


# ---------------------------------------------------------------------------
# later compaction (old ~90% no longer fires early on the 1M window)
# ---------------------------------------------------------------------------


def test_v4_compaction_threshold_is_later_than_old_90pct():
    from RxyCode.RxyCode1_1_0.core.providers.deepseek import (
        _COMPACTION_THRESHOLD,
        _CONTEXT_WINDOW,
        DeepSeekProvider,
    )

    assert _CONTEXT_WINDOW == 1_048_576
    assert _COMPACTION_THRESHOLD > 943_718  # old ~90% point
    expected = int(_CONTEXT_WINDOW * 0.97)
    assert _COMPACTION_THRESHOLD == expected

    caps = DeepSeekProvider().capabilities(
        {"model_name": "deepseek-v4-flash", "base_url": "https://api.deepseek.com/v1"}
    )
    assert caps.compaction_threshold == _COMPACTION_THRESHOLD


def test_v4_compaction_behaviour_old_90pct_no_longer_triggers(monkeypatch):
    """Old ~90% point (943_718 window) must not fire compaction; the
    0.97x threshold decides."""
    from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2

    agent = AgentV2.__new__(AgentV2)
    caps = type("Caps", (), {"compaction_threshold": int(1_048_576 * 0.97)})()
    agent._capabilities = caps
    agent._estimate_tokens = lambda messages: 950_000  # between 90% and 97%
    agent._context_window = lambda: 1_048_576
    called = {"n": 0}

    def fake_compact(messages, tail_turns=2, return_telemetry=True):  # sync like the real one
        called["n"] += 1
        return messages, {"compacted": False}

    monkeypatch.setattr("RxyCode.RxyCode1_1_0.core.compaction.compact_messages", fake_compact)

    import asyncio

    asyncio.get_event_loop().run_until_complete(agent._maybe_compress_context([]))
    assert called["n"] == 0  # old 90% point does NOT trigger anymore


def test_v4_compaction_behaviour_triggers_near_97pct(monkeypatch):
    from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2

    agent = AgentV2.__new__(AgentV2)
    caps = type("Caps", (), {"compaction_threshold": int(1_048_576 * 0.97)})()
    agent._capabilities = caps
    agent._estimate_tokens = lambda messages: 1_050_000  # above the 0.97x budget
    agent._context_window = lambda: 1_048_576
    called = {"n": 0}

    def fake_compact(messages, tail_turns=2, return_telemetry=True):  # sync like the real one
        called["n"] += 1
        return messages, {
            "compacted": True,
            "tokens_before": 1_050_000,
            "tokens_after": 800_000,
            "tail_turns": 2,
        }

    monkeypatch.setattr("RxyCode.RxyCode1_1_0.core.compaction.compact_messages", fake_compact)

    import asyncio

    asyncio.get_event_loop().run_until_complete(agent._maybe_compress_context([]))
    assert called["n"] == 1  # 0.97x budget reached -> compaction fires


def test_v4_cache_min_block_tokens_v4_caliber():
    from RxyCode.RxyCode1_1_0.core.providers.deepseek import DeepSeekProvider

    caps = DeepSeekProvider().capabilities(
        {"model_name": "deepseek-v4-flash", "base_url": "https://api.deepseek.com/v1"}
    )
    assert caps.cache_min_block_tokens == 1024  # 256-bucket, ~1024 start (V4)
