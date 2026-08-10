"""Read-only research/summarize tasks must not be forced to supply
WRITE/DANGER evidence (evals websearch-summary root cause: harness
constraint boilerplate with ACTION+ARTIFACT flipped the heuristic)."""

from __future__ import annotations

from pathlib import Path

import yaml

from RxyCode.RxyCode1_1_0.validation.side_effects import (
    task_requires_side_effect_evidence,
)

_TASKS_DIR = Path(__file__).resolve().parents[2] / "evals" / "tasks"


def _ws_prompt() -> str:
    with open(_TASKS_DIR / "websearch-summary.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["prompt"]


def test_read_only_search_summarize_task_is_not_side_effecting():
    """websearch-summary 是只读搜索+总结任务：约束行含"创建/修改+文件"
    不应让启发式把它判成副作用任务。"""
    title = _ws_prompt()
    assert task_requires_side_effect_evidence(
        title=title, result="", effect="auto"
    ) is False


def test_explicit_read_only_tool_sequence_is_not_a_side_effect_request():
    """Desktop may ask the model to execute inspection tools without writing."""
    title = (
        "Execute exactly these read-only tools: glob for appserver/runtime.py; "
        "grep for install_tui_context_hook; then read lines 1-45. "
        "Do not call bash, cd, ls, write, shell, web, or any other tool."
    )
    assert task_requires_side_effect_evidence(
        title=title, result="", effect="auto"
    ) is False


def test_declared_search_effect_is_exempt():
    """显式声明 effect=search（_NON_SIDE_EFFECT_EFFECTS）直接豁免。"""
    assert task_requires_side_effect_evidence(
        title="创建文件并实现功能", result="", effect="search"
    ) is False


def test_strong_action_with_summarize_wording_still_gated():
    """带强副作用动词（重构）即使含"总结"措辞仍判副作用——防逃逸。"""
    assert task_requires_side_effect_evidence(
        title="重构 compute_total 并总结结果", result="", effect="auto"
    ) is True


def test_create_file_with_explanation_wording_still_gated():
    """无显式解释请求短语时，"创建文件并说明"仍是副作用任务。"""
    assert task_requires_side_effect_evidence(
        title="创建文件 config.yaml 并说明用途", result="", effect="auto"
    ) is True


def test_anchored_explanation_overrides_strong_action():
    """以"解释"开头的请求即使提到修复/重构话题仍是只读任务（不回归）。"""
    assert task_requires_side_effect_evidence(
        title="解释如何修复这个 bug", result="", effect="auto"
    ) is False
