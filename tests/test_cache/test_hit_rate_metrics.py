"""B1: 命中率度量契约与基线文件（cache-hit-rate）。

把"能看"的命中率变成"能度量、能回归、能当门"的基线（PHASE-B §5 B1）。

覆盖：
1. TokenStats 度量字段存在性与口径（cache_hit_rate = hit / prompt * 100）。
2. Pi 源码实证要求的双口径：totals（累计）与 latest（最近一次 assistant 请求）。
3. evals/baselines/cache-hit-rate.json 可加载、版本字段存在。
4. 0 除保护。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_BASELINE_PATH = Path(__file__).resolve().parents[2] / "evals" / "baselines" / "cache-hit-rate.json"


def _make_stats():
    from RxyCode.RxyCode1_1_0.utils.streaming import TokenStats

    return TokenStats()


class TestHitRateMetricsFields:
    """B1 判据：度量字段存在性 + 公式口径。"""

    def test_metric_fields_exist(self):
        stats = _make_stats()
        assert hasattr(stats, "prompt_tokens")
        assert hasattr(stats, "cache_hit_tokens")
        assert hasattr(stats, "cache_hit_rate")

    def test_cache_hit_rate_formula(self):
        stats = _make_stats()
        stats.add_real_usage(3000, 0, 2000)
        assert stats.cache_hit_rate == pytest.approx(2000 / 3000 * 100)

    def test_cache_hit_rate_zero_division_protected(self):
        stats = _make_stats()
        assert stats.cache_hit_rate == 0.0

    def test_cache_hit_rate_accumulates_correctly(self):
        stats = _make_stats()
        stats.add_real_usage(1000, 0, 500)
        stats.add_real_usage(1000, 0, 0)
        assert stats.cache_hit_rate == pytest.approx(25.0)


class TestHitRateTotalsVsLatest:
    """B1 实现参考（Pi 双口径）：totals 累计 vs latest 最近一次 assistant 请求。"""

    def test_latest_request_tracked(self):
        stats = _make_stats()
        stats.add_real_usage(1000, 100, 800)
        latest = stats.latest_request
        assert latest["prompt_tokens"] == 1000
        assert latest["hit_tokens"] == 800
        assert latest["hit_rate"] == pytest.approx(80.0)

    def test_latest_overwritten_by_next_request(self):
        stats = _make_stats()
        stats.add_real_usage(1000, 100, 800)
        stats.add_real_usage(2000, 200, 0)
        latest = stats.latest_request
        assert latest["prompt_tokens"] == 2000
        assert latest["hit_tokens"] == 0
        assert latest["hit_rate"] == 0.0

    def test_latest_untouched_before_first_request(self):
        stats = _make_stats()
        assert stats.latest_request["prompt_tokens"] == 0
        assert stats.latest_request["hit_tokens"] == 0
        assert stats.latest_request["hit_rate"] == 0.0

    def test_totals_remain_cumulative_while_latest_is_single(self):
        stats = _make_stats()
        stats.add_real_usage(1000, 0, 800)
        stats.add_real_usage(1000, 0, 200)
        assert stats.prompt_tokens == 2000
        assert stats.cache_hit_tokens == 1000
        assert stats.latest_request["prompt_tokens"] == 1000
        assert stats.latest_request["hit_tokens"] == 200

    def test_reset_clears_latest(self):
        stats = _make_stats()
        stats.add_real_usage(1000, 0, 800)
        stats.reset()
        assert stats.latest_request["prompt_tokens"] == 0
        assert stats.latest_request["hit_tokens"] == 0

    def test_real_deepseek_chunk_end_to_end(self):
        """预审意见 4：DeepSeek usage-shaped integration fixture → 双口径。

        DeepSeek 流式 chunk 携带 ``prompt_cache_hit_tokens``，经
        ``_record_usage`` 进入 TokenStats；totals 累计、latest 为最近一次。
        注：chunk 为按 provider usage 形状构造的集成 fixture（非线上保存的
        原始响应），用于锁定字段映射与统计链路。
        """
        from types import SimpleNamespace

        from RxyCode.RxyCode1_1_0.core.agent_v2 import _record_usage
        from RxyCode.RxyCode1_1_0.utils.streaming import token_stats

        token_stats.reset()
        chunk1 = SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=1000,
                completion_tokens=500,
                prompt_cache_hit_tokens=800,
                prompt_tokens_details=None,
            ),
            usage_metadata=None,
            content=None,
        )
        chunk2 = SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=2000,
                completion_tokens=400,
                prompt_cache_hit_tokens=200,
                prompt_tokens_details=None,
            ),
            usage_metadata=None,
            content=None,
        )
        _record_usage(chunk1)
        _record_usage(chunk2)
        assert token_stats.prompt_tokens == 3000
        assert token_stats.cache_hit_tokens == 1000
        assert token_stats.cache_hit_rate == pytest.approx(1000 / 3000 * 100)
        assert token_stats.latest_request["prompt_tokens"] == 2000
        assert token_stats.latest_request["hit_tokens"] == 200
        assert token_stats.latest_request["hit_rate"] == pytest.approx(10.0)


class TestCacheHitRateBaselineFile:
    """B1 判据：基线文件可加载、版本字段存在。"""

    def test_baseline_file_exists(self):
        assert _BASELINE_PATH.is_file(), (
            "missing evals/baselines/cache-hit-rate.json; run B1 sampling first"
        )

    def test_baseline_required_fields_present(self):
        data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        for field in ("version", "date", "backend", "model",
                      "prompt_tokens", "hit_tokens", "hit_rate"):
            assert field in data, f"baseline missing field: {field}"

    def test_baseline_version_field(self):
        data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        assert isinstance(data.get("version"), str) and data["version"]

    def test_baseline_schema_and_calculation_fields(self):
        """预审意见 3：基线文件须可审计——schema_version + 计算口径字段。"""
        data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        assert isinstance(data.get("schema_version"), int)
        assert data.get("calculation") == "cache_hit_tokens / prompt_tokens * 100"
        assert isinstance(data.get("sample_count"), int) and data["sample_count"] >= 1
        assert data.get("provider") and data.get("base_url")

    def test_baseline_hit_rate_numeric(self):
        data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        assert isinstance(data.get("hit_rate"), (int, float))
        assert 0.0 <= data["hit_rate"] <= 100.0

    def test_baseline_hit_rate_consistent_with_tokens(self):
        data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        prompt = int(data["prompt_tokens"])
        hit = int(data["hit_tokens"])
        expected = hit / prompt * 100 if prompt else 0.0
        assert data["hit_rate"] == pytest.approx(expected, abs=0.01)
