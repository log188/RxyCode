"""Provider 注册表解析规则测试。"""
import pytest

from config.model_capabilities import DEFAULT_CAPABILITIES
from config.model_limits import UNKNOWN_MODEL_FALLBACK
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
        {"model_name": "gpt-4o", "api_key": "k", "base_url": "b"}, caps,
    )
    assert kwargs["model"] == "gpt-4o"
    # Phase 3 M4：不再回退固定 8192；无解析值时用未知模型高位兜底。
    assert kwargs["max_tokens"] == UNKNOWN_MODEL_FALLBACK
    assert kwargs["temperature"] == 0.7
    assert kwargs["max_retries"] == 3
    assert kwargs["streaming"] is True
    assert kwargs["stream_usage"] is True


def test_llm_kwargs_uses_resolved_max_tokens_when_provided():
    """M4：调用方已解析时，resolved_max_tokens 优先于 fallback。"""
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


def test_llm_kwargs_auto_falls_back_to_unknown():
    """M4：max_tokens='auto' 且无 resolved 时 → 未知兜底，不返回 'auto'。"""
    p = providers.resolve({})
    caps = p.capabilities({})
    kwargs = p.llm_kwargs(
        {"model_name": "m", "api_key": "k", "base_url": "b", "max_tokens": "auto"},
        caps,
    )
    assert isinstance(kwargs["max_tokens"], int)
    assert kwargs["max_tokens"] > 0
    assert kwargs["max_tokens"] == UNKNOWN_MODEL_FALLBACK


@pytest.mark.parametrize("usage,expected", [
    ({"prompt_cache_hit_tokens": 128}, 128),
    ({"prompt_tokens_details": {"cached_tokens": 64}}, 64),
    ({}, 0),
    ({"prompt_cache_hit_tokens": "bad"}, 0),
])
def test_extract_cache_read_handles_both_conventions(usage, expected):
    p = providers.resolve({})
    assert p.extract_cache_read(usage, p.capabilities({})) == expected
