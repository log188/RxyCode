"""A23: DoubaoProvider registration and capability declaration."""

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from RxyCode.RxyCode1_1_0.config.model_capabilities import DEFAULT_CAPABILITIES
from RxyCode.RxyCode1_1_0.core import providers
from RxyCode.RxyCode1_1_0.core.providers.doubao import DoubaoProvider

_ARK = "https://ark.cn-beijing.volces.com/api/coding/v3"


def test_matches_doubao_models_on_ark():
    p = DoubaoProvider()
    assert p.matches(_ARK, "doubao-seed-2.1-turbo")
    assert p.matches(_ARK, "doubao-seed-2.1-pro")


def test_matches_seed_variant_on_ark():
    """§7.9 matches 规则：模型名含 doubao 或 seed 即命中（官方 ark URL 上）。"""
    p = DoubaoProvider()
    assert p.matches(_ARK, "seed-foo")
    assert p.matches(_ARK, "doubao-seed-2-1-turbo-260628")


def test_does_not_steal_other_ark_models():
    p = DoubaoProvider()
    assert not p.matches(_ARK, "minimax-m3")
    assert not p.matches(_ARK, "glm-5.2")
    assert not p.matches("https://api.deepseek.com/v1", "doubao-seed-2.1-turbo")
    assert not p.matches("https://api.openai.com/v1", "gpt-4o")


def test_volcengine_hostname_not_matched():
    """A23 常见坑：实际域名是 volces.com，勿用 volcengine（否则抢不到 ark 端点）。"""
    p = DoubaoProvider()
    assert not p.matches("https://www.volcengine.com/example", "doubao-seed-2.1-turbo")
    assert p.matches(_ARK, "doubao-seed-2.1-turbo")


def test_ark_substring_url_not_matched():
    """`"ark" in url` 不泛化：任意含 ark 的非官方端点不得匹配（Luna rev1/rev3/rev6）。"""
    p = DoubaoProvider()
    assert not p.matches("https://api.openai.com/v1/ark", "doubao-seed-2.1-turbo")
    assert not p.matches("https://example.com/ark", "doubao-seed-2.1-turbo")
    assert not p.matches("https://not-volces.example/path", "seed-foo")
    assert not p.matches("https://fooark.volces.com/api", "doubao-seed-2.1-turbo")
    assert not p.matches("https://ark@evil.volces.com/x", "doubao-seed-2.1-turbo")
    assert not p.matches("ftp://ark.cn-beijing.volces.com/v1", "doubao-seed-2.1-turbo")
    assert not p.matches("https://ark.cn-beijing.volces.com.evil.example/x", "doubao-seed-2.1-turbo")
    assert not p.matches("http://[::1]/ark", "doubao-seed-2.1-turbo")


def test_ark_url_case_and_region():
    """大小写与合法 ark 区域 hostname（Luna rev6 边界）。"""
    p = DoubaoProvider()
    assert p.matches("HTTPS://ARK.CN-BEIJING.VOLCES.COM/api/coding/v3", "doubao-seed-2.1-turbo")
    assert p.matches("https://ark.cn-north-1.volces.com/api", "doubao-seed-2.1-turbo")
    assert p.matches("https://ark.volces.com/api", "doubao-seed-2.1-turbo")


def test_resolve_returns_doubao_for_doubao_config():
    resolved = providers.resolve(
        {"base_url": _ARK, "model_name": "doubao-seed-2.1-turbo"}
    )
    assert isinstance(resolved, DoubaoProvider)


@pytest.mark.parametrize(
    "name", ["doubao-seed-2.1-turbo", "doubao-seed-2-1-turbo-260628", "doubao-seed-2.1-pro", "doubao-seed-2-1-pro-260628"]
)
def test_resolve_doubao_all_variants(name):
    """ark 别名与官方 snapshot 均经 resolve 命中 DoubaoProvider（Luna rev3）。"""
    resolved = providers.resolve({"base_url": _ARK, "model_name": name})
    assert isinstance(resolved, DoubaoProvider)


def test_capabilities_match_research():
    p = DoubaoProvider()
    caps = p.capabilities({"base_url": _ARK, "model_name": "doubao-seed-2.1-turbo"})
    assert caps.provider == "doubao"
    assert caps.supports_reasoning is True
    assert caps.supports_function_calling is True
    assert caps.usage_fields.reasoning == ("reasoning_content",)
    assert caps.tokenizer == "chars:2.0"
    assert caps.context_window == 256_000
    assert caps.prompt_variant == "doubao"
    assert caps.supports_vision is False
    # §7.9：256k 为软上限，能力层不声明硬上限（A23；max_output_tokens 保持 None）
    assert caps.max_output_tokens is None


def test_turbo_snapshot_variant_caps():
    """官方 snapshot 变体（doubao-seed-2-1-turbo-260628）与 ark 别名同等能力声明。"""
    p = DoubaoProvider()
    for name in ("doubao-seed-2-1-turbo-260628", "doubao-seed-2.1-turbo"):
        caps = p.capabilities({"base_url": _ARK, "model_name": name})
        assert caps.supports_reasoning is True
        assert caps.supports_function_calling is True


def test_pro_caps_stay_conservative():
    # §7.9 R1：pro 未实测，不得声明 reasoning/FC/context/max_output（不得用 turbo 结果外推）
    p = DoubaoProvider()
    for name in ("doubao-seed-2.1-pro", "doubao-seed-2-1-pro-260628"):
        caps = p.capabilities({"base_url": _ARK, "model_name": name})
        assert caps.supports_reasoning is False
        assert caps.supports_function_calling is False
        assert caps.usage_fields.reasoning == ()
        assert caps.context_window == DEFAULT_CAPABILITIES.context_window
        assert caps.compaction_threshold == DEFAULT_CAPABILITIES.compaction_threshold
        assert caps.max_output_tokens == DEFAULT_CAPABILITIES.max_output_tokens


def test_unknown_variant_stays_conservative():
    """未调研变体不继承 turbo 能力/usage/pricing/context 声明（DC1；不得泛化）。"""
    p = DoubaoProvider()
    for name in (
        "doubao-seed-3.0",
        "doubao-seed-2.1-foo",
        "doubao-seed-2.1-turbo-foo",
        "doubao-seed-2.1-turbo-experimental",
    ):
        caps = p.capabilities({"base_url": _ARK, "model_name": name})
        assert caps.supports_reasoning is False
        assert caps.supports_function_calling is False
        assert caps.usage_fields.reasoning == ()
        assert caps.pricing.input_per_mtok is None
        assert caps.context_window == DEFAULT_CAPABILITIES.context_window
        assert caps.compaction_threshold == DEFAULT_CAPABILITIES.compaction_threshold
        assert caps.max_output_tokens == DEFAULT_CAPABILITIES.max_output_tokens


def test_pricing_placeholder_not_zero():
    """§7.9：官方 CNY 定价未换算 USD 前占位 None，不得静默当 0 计费。"""
    p = DoubaoProvider()
    for name in ("doubao-seed-2.1-turbo", "doubao-seed-2.1-pro"):
        caps = p.capabilities({"base_url": _ARK, "model_name": name})
        assert caps.pricing.input_per_mtok is None
        assert caps.pricing.output_per_mtok is None
        assert caps.pricing.cached_input_per_mtok is None
        assert caps.pricing.cache_write_per_mtok is None
        assert caps.pricing.source_url
        assert caps.pricing.as_of == "2026-08-06"


def test_pro_usage_fields_no_reasoning():
    """§7.9 R1：pro 未实测，usage_fields 不含 reasoning 映射（仅 turbo 声明）。"""
    p = DoubaoProvider()
    caps = p.capabilities({"base_url": _ARK, "model_name": "doubao-seed-2.1-pro"})
    assert caps.usage_fields.reasoning == ()


def test_overrides_apply():
    p = DoubaoProvider()
    caps = p.capabilities(
        {"base_url": _ARK, "model_name": "doubao-seed-2.1-turbo", "tokenizer": "tiktoken:o200k_base"}
    )
    assert caps.tokenizer == "tiktoken:o200k_base"


def test_doubao_imports_without_repo_root_on_sys_path():
    """Regression: doubao.py must not require the repo root on sys.path.

    Console scripts (rxycode.exe) and the embedded API server run with a
    sys.path that lacks the repo root, so the top-level ``from config...`` /
    ``from core...`` imports used to raise ModuleNotFoundError: No module
    named 'config', aborting agent init with "Warning: Agent init failed".
    The module must resolve via relative imports instead.
    """
    probe = (
        "import importlib, sys\n"
        "sys.path[:] = [p for p in sys.path if p not in ('', '.')]\n"
        "import os\n"
        "os.chdir(os.path.expanduser('~'))\n"
        "m = importlib.import_module('RxyCode.RxyCode1_1_0.core.providers.doubao')\n"
        "print(m.DoubaoProvider.__name__)\n"
    )
    # 仓库根 = 本测试文件第 4 级父目录（tests/test_core/test_providers/…）；
    # 用 Path.parents 显式表达，避免 dirname 链结构歧义（Luna rev6）。
    root = str(Path(__file__).resolve().parents[3])
    env = dict(os.environ)
    env["PYTHONPATH"] = ""  # 避免隐式依赖仓库根
    env["PYTHONSAFEPATH"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "DoubaoProvider" in result.stdout
