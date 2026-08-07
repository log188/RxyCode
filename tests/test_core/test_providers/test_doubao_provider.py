"""A23: DoubaoProvider registration and capability declaration."""

import importlib
import os
import subprocess
import sys

from RxyCode.RxyCode1_1_0.config.model_capabilities import DEFAULT_CAPABILITIES
from RxyCode.RxyCode1_1_0.core import providers
from RxyCode.RxyCode1_1_0.core.providers.doubao import DoubaoProvider

_ARK = "https://ark.cn-beijing.volces.com/api/coding/v3"


def test_matches_doubao_models_on_ark():
    p = DoubaoProvider()
    assert p.matches(_ARK, "doubao-seed-2.1-turbo")
    assert p.matches(_ARK, "doubao-seed-2.1-pro")


def test_does_not_steal_other_ark_models():
    p = DoubaoProvider()
    assert not p.matches(_ARK, "minimax-m3")
    assert not p.matches(_ARK, "glm-5.2")
    assert not p.matches("https://api.deepseek.com/v1", "doubao-seed-2.1-turbo")
    assert not p.matches("https://api.openai.com/v1", "gpt-4o")


def test_resolve_returns_doubao_for_doubao_config():
    resolved = providers.resolve(
        {"base_url": _ARK, "model_name": "doubao-seed-2.1-turbo"}
    )
    assert isinstance(resolved, DoubaoProvider)


def test_capabilities_match_research():
    p = DoubaoProvider()
    caps = p.capabilities({"base_url": _ARK, "model_name": "doubao-seed-2.1-turbo"})
    assert caps.provider == "doubao"
    assert caps.supports_reasoning is True
    assert caps.supports_function_calling is True
    assert caps.usage_fields.reasoning == ("reasoning_content",)
    assert caps.tokenizer == "chars:2.0"
    assert caps.context_window == DEFAULT_CAPABILITIES.context_window == 256_000


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
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
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
