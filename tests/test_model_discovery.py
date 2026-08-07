"""Phase 3 M3/M7: model discovery record tests (id primary key, allowlist)."""
from __future__ import annotations

import pytest

from RxyCode.RxyCode1_1_0.config.model_manager import _parse_discovered_models


def test_parse_discovered_models_dict_data():
    payload = {
        "data": [
            {"id": "deepseek-v4-flash", "owned_by": "deepseek"},
            {"id": "deepseek-v4-pro", "owned_by": "deepseek"},
        ]
    }
    models = _parse_discovered_models(payload)
    assert models == [
        {"id": "deepseek-v4-flash", "owned_by": "deepseek"},
        {"id": "deepseek-v4-pro", "owned_by": "deepseek"},
    ]


def test_parse_discovered_models_string_list():
    payload = ["gpt-5.6-luna", "gpt-5.6-sol"]
    models = _parse_discovered_models(payload)
    assert models == [{"id": "gpt-5.6-luna"}, {"id": "gpt-5.6-sol"}]


def test_parse_discovered_models_allowlist_fields():
    """allowlist：context_window / max_output_tokens / max_completion_tokens 保留，
    其他未知字段忽略。"""
    payload = {
        "data": [
            {
                "id": "m",
                "owned_by": "vendor",
                "context_window": 131072,
                "max_output_tokens": 65536,
                "max_completion_tokens": 65536,
                "bogus_field": 999,   # 未知字段，忽略
            }
        ]
    }
    models = _parse_discovered_models(payload)
    assert models == [{
        "id": "m",
        "owned_by": "vendor",
        "context_window": 131072,
        "max_output_tokens": 65536,
        "max_completion_tokens": 65536,
    }]


def test_parse_discovered_models_invalid_capability_values_ignored():
    """allowlist 能力字段非正整数时视为缺失（不把坏值当能力）。"""
    payload = {
        "data": [
            {
                "id": "m",
                "context_window": -1,
                "max_output_tokens": 0,
                "max_completion_tokens": "big",
            }
        ]
    }
    models = _parse_discovered_models(payload)
    assert models == [{"id": "m"}]


def test_parse_discovered_models_dedup():
    payload = {"data": [{"id": "m"}, {"id": "m"}, {"id": "n"}]}
    models = _parse_discovered_models(payload)
    assert models == [{"id": "m"}, {"id": "n"}]


def test_parse_discovered_models_empty():
    assert _parse_discovered_models({"data": []}) == []
    assert _parse_discovered_models({}) == []
    assert _parse_discovered_models(None) == []


def test_parse_discovered_models_missing_id_skipped():
    payload = {"data": [{"owned_by": "x"}, {"id": "real"}]}
    models = _parse_discovered_models(payload)
    assert models == [{"id": "real"}]
