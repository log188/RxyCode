"""Provider 注册表解析规则测试。"""
import pytest

from config.model_capabilities import DEFAULT_CAPABILITIES
from core import providers
from core.providers.openai import OpenAIProvider


def test_unknown_model_falls_back_to_openai():
    p = providers.resolve({"base_url": "https://unknown.example/v1",
                           "model_name": "mystery-1"})
    assert isinstance(p, OpenAIProvider)


def test_fallback_capabilities_are_the_legacy_defaults():
    p = providers.resolve({"base_url": "", "model_name": ""})
    assert p.capabilities({}) == DEFAULT_CAPABILITIES


def test_explicit_provider_field_wins():
    p = providers.resolve({"provider": "openai",
                           "base_url": "https://whatever/v1",
                           "model_name": "x"})
    assert p.name == "openai"


def test_unknown_explicit_provider_falls_back_silently():
    # 用户可能写了错别字；不应该崩，应该退回兜底
    p = providers.resolve({"provider": "not-a-real-provider"})
    assert isinstance(p, OpenAIProvider)


def test_llm_kwargs_reproduce_legacy_arguments():
    p = providers.resolve({})
    caps = p.capabilities({})
    kwargs = p.llm_kwargs(
        {"model_name": "gpt-4o", "api_key": "k", "base_url": "b",
         "resolved_max_tokens": 8192}, caps,
    )
    assert kwargs["model"] == "gpt-4o"
    # Phase 3 M4：显式 max_tokens 保留（等价 explicit_config）。
    assert kwargs["max_tokens"] == 8192
    assert kwargs["temperature"] == 0.7
    assert kwargs["max_retries"] == 3
    assert kwargs["streaming"] is True
    assert kwargs["stream_usage"] is True


def test_llm_kwargs_uses_resolved_max_tokens_when_provided():
    """M4：调用方已解析时，resolved_max_tokens 优先。"""
    p = providers.resolve({})
    caps = p.capabilities({})
    kwargs = p.llm_kwargs(
        {
            "model_name": "gpt-5.6-luna",
            "api_key": "k",
            "base_url": "b",
            "resolved_max_tokens": 128000,
        },
        caps,
    )
    assert kwargs["max_tokens"] == 128000


def test_llm_kwargs_missing_resolved_raises():
    """EXIT.6：无 resolved_max_tokens 且无正整数 max_tokens → 抛错（不自行兜底）。"""
    p = providers.resolve({})
    caps = p.capabilities({})
    with pytest.raises(ValueError):
        p.llm_kwargs(
            {"model_name": "m", "api_key": "k", "base_url": "b", "max_tokens": "auto"},
            caps,
        )
    with pytest.raises(ValueError):
        p.llm_kwargs(
            {"model_name": "m", "api_key": "k", "base_url": "b"},
            caps,
        )


@pytest.mark.parametrize("usage,expected", [
    ({"prompt_cache_hit_tokens": 128}, 128),
    ({"prompt_tokens_details": {"cached_tokens": 64}}, 64),
    ({}, 0),
    ({"prompt_cache_hit_tokens": "bad"}, 0),
])
def test_extract_cache_read_handles_both_conventions(usage, expected):
    p = providers.resolve({})
    assert p.extract_cache_read(usage, p.capabilities({})) == expected
