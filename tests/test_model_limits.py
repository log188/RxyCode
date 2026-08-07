"""Phase 3 M2/M3/M7: output limit resolution contract and precedence tests."""
from __future__ import annotations

import pytest

from RxyCode.RxyCode1_1_0.config.model_catalog import ModelCatalog
from RxyCode.RxyCode1_1_0.config.model_limits import (
    MODEL_CONTEXT_BUDGET_EXHAUSTED,
    UNKNOWN_MODEL_FALLBACK,
    ModelLimitError,
    ModelLimitRecord,
    OutputLimitResolution,
    normalize_model_key,
    resolve_output_limit,
)


def _record(model_id="demo-model", cap=131072, ctx=262144, provider="demo"):
    return {
        "provider_id": provider,
        "model_id": model_id,
        "model_context_window": ctx,
        "model_max_output_tokens": cap,
        "source": "test-catalog",
        "source_url": "https://example.invalid/catalog",
        "as_of": "2026-08-03",
    }


@pytest.mark.parametrize(
    ("configured", "catalog", "provider_default", "expected", "source"),
    [
        (4096, 131072, 65536, 4096, "explicit_config"),
        (None, 131072, 65536, 131072, "catalog_exact_provider"),
        (None, None, 65536, 65536, "provider_default"),
        (None, None, None, 32768, "unknown_fallback"),
        ("auto", 131072, 65536, 131072, "catalog_exact_provider"),
    ],
)
def test_resolution_precedence(configured, catalog, provider_default, expected, source):
    catalog_record = None
    if catalog is not None:
        catalog_record = _record(cap=catalog)

    result = resolve_output_limit(
        provider_id="demo",
        model_id="demo-model",
        configured_max_tokens=configured,
        catalog_record=catalog_record,
        provider_default=provider_default,
        input_tokens=12000,
        context_safety_margin=1024,
    )

    assert result.resolved_max_tokens == expected
    assert result.source == source


def test_explicit_over_catalog_with_clamp():
    """显式值超过已知硬上限 → explicit_clamped + warning。"""
    result = resolve_output_limit(
        provider_id="demo",
        model_id="demo-model",
        configured_max_tokens=200000,
        catalog_record=_record(cap=131072),
        provider_default=65536,
        input_tokens=1000,
    )
    assert result.resolved_max_tokens == 131072
    assert result.source == "explicit_clamped"
    assert result.warnings


def test_context_window_clamp():
    """已知 context window 参与最终钳制。"""
    result = resolve_output_limit(
        provider_id="demo",
        model_id="demo-model",
        configured_max_tokens=None,
        catalog_record=_record(cap=131072, ctx=10000),
        provider_default=65536,
        input_tokens=5000,
        context_safety_margin=1024,
    )
    # ctx 10000 - input 5000 - margin 1024 = 3976 < 131072 → context_cap
    assert result.resolved_max_tokens == 3976
    assert result.source == "context_cap"


def test_context_budget_exhausted_raises():
    """有效输出上限 < 1 → 结构化 MODEL_CONTEXT_BUDGET_EXHAUSTED。"""
    with pytest.raises(ModelLimitError) as exc:
        resolve_output_limit(
            provider_id="demo",
            model_id="demo-model",
            configured_max_tokens=None,
            catalog_record=_record(cap=131072, ctx=2000),
            provider_default=65536,
            input_tokens=2000,
            context_safety_margin=1024,
        )
    assert exc.value.code == MODEL_CONTEXT_BUDGET_EXHAUSTED


def test_unknown_fallback_constant():
    assert UNKNOWN_MODEL_FALLBACK == 32768


def test_invalid_configured_value_rejected():
    for bad in (0, -5, 1.5, "yes"):
        with pytest.raises(ValueError):
            resolve_output_limit(
                provider_id="demo",
                model_id="demo-model",
                configured_max_tokens=bad,
                catalog_record=None,
                provider_default=None,
                input_tokens=100,
            )


def test_normalize_model_key():
    assert normalize_model_key("  DeepSeek-V4-FLASH ") == "deepseek-v4-flash"
    assert normalize_model_key("") == ""


def test_catalog_cross_provider_coexistence():
    """同一 model_id 在不同 Provider 下可共存，且互不串。"""
    cat = ModelCatalog()
    cat.add_record({
        "provider_id": "a", "model_id": "same-model",
        "model_context_window": 1000, "model_max_output_tokens": 500,
        "source": "test", "source_url": "https://example.invalid/catalog", "as_of": "2026-08-03",
    })
    cat.add_record({
        "provider_id": "b", "model_id": "same-model",
        "model_context_window": 2000, "model_max_output_tokens": 1000,
        "source": "test", "source_url": "https://example.invalid/catalog", "as_of": "2026-08-03",
    })
    rec_a, key_a, _ = cat.lookup("a", "same-model")
    rec_b, key_b, _ = cat.lookup("b", "same-model")
    assert rec_a.model_max_output_tokens == 500
    assert rec_b.model_max_output_tokens == 1000
    assert key_a == "a:same-model"
    assert key_b == "b:same-model"


def test_catalog_duplicate_same_provider_fails_closed():
    cat = ModelCatalog()
    cat.add_record({
        "provider_id": "a", "model_id": "m",
        "model_context_window": 1000, "model_max_output_tokens": 500,
        "source": "test", "source_url": "https://example.invalid/catalog", "as_of": "2026-08-03",
    })
    with pytest.raises(ValueError):
        cat.add_record({
            "provider_id": "a", "model_id": "m",
            "model_context_window": 2000, "model_max_output_tokens": 900,
            "source": "test", "source_url": "https://example.invalid/catalog", "as_of": "2026-08-03",
        })


def test_catalog_family_pattern():
    cat = ModelCatalog()
    cat.add_family("kimi", "kimi-k2*", {
        "model_context_window": 262144, "model_max_output_tokens": None,
        "source": "family", "source_url": "https://example.invalid/catalog", "as_of": "2026-08-03",
    })
    rec, key, pattern = cat.lookup("kimi", "kimi-k2.6")
    assert rec is not None
    assert pattern == "kimi-k2*"
    assert key is None
    # 非 kimi provider 不命中
    rec, _, _ = cat.lookup("other", "kimi-k2.6")
    assert rec is None


def test_catalog_invalid_output_gt_context_rejected():
    cat = ModelCatalog()
    with pytest.raises(ValueError):
        cat.add_record({
            "provider_id": "a", "model_id": "m",
            "model_context_window": 100, "model_max_output_tokens": 500,
            "source": "test", "source_url": None, "as_of": "2026-08-03",
        })


# ---- §7.2 完整六级优先级（审计要求） -------------------------------


def test_priority_exact_model_without_provider():
    """优先级 3：仅一个 Provider 注册该 model_id 时，无 Provider 限定可命中。"""
    cat = ModelCatalog()
    cat.add_record(_record(provider="a", model_id="solo", cap=4096, ctx=8192))
    rec, key, _ = cat.lookup("b", "solo")
    assert rec is not None
    assert rec.model_max_output_tokens == 4096
    assert key == "solo"


def test_priority_exact_model_conflict_fails_closed():
    """优先级 3：同名跨 Provider 时，无 Provider 限定查找必须拒绝。"""
    cat = ModelCatalog()
    cat.add_record(_record(provider="a", model_id="dup", cap=4096, ctx=8192))
    cat.add_record(_record(provider="b", model_id="dup", cap=8192, ctx=8192))
    rec, key, _ = cat.lookup("c", "dup")  # provider=c 未注册
    assert rec is None
    assert key is None


def test_priority_family_pattern_hit():
    """优先级 4：显式登记的 family pattern 命中。"""
    cat = ModelCatalog()
    cat.add_family("kimi", "kimi-k2*", {
        "model_context_window": 262144, "model_max_output_tokens": 131072,
        "source": "family", "source_url": "https://example.invalid/catalog", "as_of": "2026-08-03",
    })
    rec, key, pattern = cat.lookup("kimi", "kimi-k2.7-code")
    assert rec is not None
    assert pattern == "kimi-k2*"
    assert rec.model_max_output_tokens == 131072


def test_priority_exact_beats_family():
    """exact 目录项优先于 family pattern。"""
    cat = ModelCatalog()
    cat.add_family("kimi", "kimi-k2*", {
        "model_context_window": 262144, "model_max_output_tokens": 131072,
        "source": "family", "source_url": "https://example.invalid/catalog", "as_of": "2026-08-03",
    })
    cat.add_record(_record(provider="kimi", model_id="kimi-k2.7-code",
                           cap=32768, ctx=262144))
    rec, key, pattern = cat.lookup("kimi", "kimi-k2.7-code")
    assert key == "kimi:kimi-k2.7-code"  # exact 命中
    assert pattern is None
    assert rec.model_max_output_tokens == 32768


def test_priority_provider_default_used_when_no_catalog():
    """优先级 5：无目录命中时用 provider default。"""
    result = resolve_output_limit(
        provider_id="demo", model_id="unknown-m",
        configured_max_tokens=None,
        catalog_record=None,
        provider_default=65536,
        input_tokens=100,
    )
    assert result.resolved_max_tokens == 65536
    assert result.source == "provider_default"


def test_explicit_clamped_warns_and_clamps():
    """显式值超硬上限 → explicit_clamped + warning，不发送超限值。"""
    result = resolve_output_limit(
        provider_id="demo", model_id="demo-model",
        configured_max_tokens=999999,
        catalog_record=_record(cap=131072),
        provider_default=65536,
        input_tokens=100,
    )
    assert result.resolved_max_tokens == 131072
    assert result.source == "explicit_clamped"
    assert result.warnings
    assert "exceeds" in result.warnings[0]


def test_family_pattern_requires_explicit_registration():
    """family 只允许显式登记；昵称/模糊 substring 不得命中。"""
    cat = ModelCatalog()
    cat.add_family("kimi", "kimi-k2*", {
        "model_context_window": 262144, "model_max_output_tokens": 131072,
        "source": "family", "source_url": "https://example.invalid/catalog", "as_of": "2026-08-03",
    })
    # 未登记的 provider → 不命中
    assert cat.lookup("other", "kimi-k2.6")[0] is None
    # 昵称/显示名（非 id）→ 不命中
    assert cat.lookup("kimi", "旗舰模型")[0] is None
    # 不匹配 pattern 的 id → 不命中
    assert cat.lookup("kimi", "kimi-k3")[0] is None


# ---- ML6 来源过期 / ML8 来源完整性（审计要求） -----------------------


def test_catalog_capability_requires_source_url_and_as_of():
    """ML8：有能力值（context/output）的目录记录必须带 source_url 与 as_of。"""
    from RxyCode.RxyCode1_1_0.config.model_catalog import ModelCatalog

    cat = ModelCatalog()
    # 缺 source_url → 拒绝
    with pytest.raises(ValueError, match="source_url"):
        cat.add_record({
            "provider_id": "a", "model_id": "m",
            "model_context_window": 8192, "model_max_output_tokens": 4096,
            "source": "t", "as_of": "2026-08-03",
        })
    # 缺 as_of → 拒绝
    with pytest.raises(ValueError, match="as_of"):
        cat.add_record({
            "provider_id": "a", "model_id": "m",
            "model_context_window": 8192, "model_max_output_tokens": 4096,
            "source": "t", "source_url": "https://example.invalid/cat",
        })
    # 无能力值（null）的占位记录可省略 URL/as_of
    cat.add_record({
        "provider_id": "a", "model_id": "placeholder",
        "model_context_window": None, "model_max_output_tokens": None,
        "source": "t",
    })


def test_stale_source_produces_warning():
    """ML6：as_of 超过 catalog_max_age_days → 可解释 warning（不静默）。"""
    import datetime as _dt

    from RxyCode.RxyCode1_1_0.config.model_limits import (
        ModelLimitRecord,
        resolve_output_limit,
    )

    old_date = (_dt.date.today() - _dt.timedelta(days=365)).isoformat()
    stale = ModelLimitRecord(
        provider_id="a", model_id="m",
        model_context_window=8192, model_max_output_tokens=4096,
        source="t", source_url="https://example.invalid/cat", as_of=old_date,
    )
    result = resolve_output_limit(
        provider_id="a", model_id="m",
        configured_max_tokens=None,
        catalog_record=stale,
        provider_default=None,
        input_tokens=100,
        catalog_max_age_days=90,
    )
    assert any("days old" in w or "stale" in w for w in result.warnings)
    # source 仍是 catalog 命中（不静默降级）
    assert result.source == "catalog_exact_provider"


def test_missing_as_of_produces_warning():
    """ML6：as_of 缺失 → 可解释 warning。"""
    from RxyCode.RxyCode1_1_0.config.model_limits import (
        ModelLimitRecord,
        resolve_output_limit,
    )

    no_date = ModelLimitRecord(
        provider_id="a", model_id="m",
        model_context_window=8192, model_max_output_tokens=4096,
        source="t", source_url="https://example.invalid/cat", as_of=None,
    )
    result = resolve_output_limit(
        provider_id="a", model_id="m",
        configured_max_tokens=None,
        catalog_record=no_date,
        provider_default=None,
        input_tokens=100,
        catalog_max_age_days=90,
    )
    assert any("no as_of" in w or "as_of" in w for w in result.warnings)
