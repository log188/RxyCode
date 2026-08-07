"""Deterministic detection of tasks and claims that require tool evidence."""

from __future__ import annotations

import re
from collections.abc import Iterable

from RxyCode.RxyCode1_1_0.core.safety.policy import RiskLevel, get_tool_risk
from RxyCode.RxyCode1_1_0.execution.evidence import ToolEvidence


_ACTION_RE = re.compile(
    r"\b(?:create|write|edit|modify|delete|remove|install|download|execute|run|"
    r"open|format|save|update|rename|move|copy|commit|push|deploy|implement|"
    r"fix|add|build|refactor|test)\b|"
    r"(?:创建|写入|编辑|修改|删除|移除|安装|下载|执行|运行|打开|格式化|保存|"
    r"更新|重命名|移动|复制|提交|推送|部署|实现|修复|新增|添加|构建|重构|"
    r"测试)",
    re.IGNORECASE,
)
_STRONG_ACTION_RE = re.compile(
    r"\b(?:implement|fix|build|refactor)\b|"
    r"(?:实现|修复|构建|重构)",
    re.IGNORECASE,
)
_ARTIFACT_RE = re.compile(
    r"\b(?:file|directory|folder|code|project|package|server|workflow|command|"
    r"repository|repo|document|image|artifact|configuration|config|task|"
    r"database|table|endpoint|feature|bug|issue|button|component|application|"
    r"app|test|suite|module|function|class|api|authentication|login)\b|"
    r"(?:文件|目录|代码|项目|包|服务|工作流|命令|仓库|文档|图片|产物|配置|"
    r"任务|数据库|表|接入点|功能|问题|按钮|组件|应用|测试|模块|函数|类|"
    r"接口|认证|登录)",
    re.IGNORECASE,
)
_COMPLETION_CLAIM_RE = re.compile(
    r"^\s*(?:(?:successfully|already)\s+)?(?:created|wrote|written|edited|"
    r"modified|deleted|removed|installed|downloaded|executed|ran|opened|"
    r"formatted|saved|updated|renamed|moved|copied|committed|pushed|deployed|"
    r"implemented|fixed|added|built|refactored|tested|completed)\b|"
    r"\b(?:i|we)\s+(?:have\s+)?(?:created|written|edited|modified|deleted|"
    r"installed|downloaded|executed|opened|saved|updated|implemented|fixed|"
    r"added|built|refactored|tested|completed)\b|"
    r"^\s*(?:成功(?:地)?|已经)?(?:已创建|已写入|已编辑|已修改|已删除|已移除|"
    r"已安装|已下载|已执行|已运行|已打开|已格式化|已保存|已更新|已重命名|"
    r"已移动|已复制|已提交|已推送|已部署|已实现|已修复|已新增|已添加|已构建|"
    r"已重构|已测试|已完成)",
    re.IGNORECASE,
)
_EXPLANATION_RE = re.compile(
    r"^\s*(?:(?:how|what|why|who|when|where|which)\b|"
    r"(?:explain|describe|analy[sz]e|list|show(?:\s+me)?|summari[sz]e|"
    r"compare|review)\b|"
    r"(?:can|could|would)\s+you\s+(?:explain|describe|list|show|"
    r"summari[sz]e|compare|review)\b|"
    r"如何|怎么|解释|说明|分析|什么|为何|为什么|谁|何时|哪里|哪(?:个|些)?|"
    r"列出|显示|展示|总结|概括|比较|对比|审查|评审)",
    re.IGNORECASE,
)

#: 请求正文中的**显式**解释/总结/搜索请求短语（非锚定，中段匹配）。
#: 它比锚定的 _EXPLANATION_RE 弱：只覆盖 ACTION+ARTIFACT 启发式，
#: **不**覆盖强副作用动词（见 task_requires_side_effect_evidence）。
#: 覆盖两类真实场景：
#:   - "请总结/帮我概括/总结一下" 式显式请求；
#:   - "搜索 … 然后总结" 式只读研究-总结任务（如 evals websearch-summary，
#:     其约束行含"创建/修改+文件"会误触发 ACTION+ARTIFACT）。
_EXPLICIT_EXPLANATION_RE = re.compile(
    r"(?:请|麻烦|帮我)\s*(?:总结|概括|说明|解释|分析|列出|汇总|介绍|展示|"
    r"搜索|查询|检索)|"
    r"please\s+(?:summarize|summarise|explain|describe|list|show)\b|"
    r"(?:总结|概括|说明|解释|分析|汇总|搜索|查询|检索)(?:一下|一遍)|"
    r"(?:搜索|检索|查询|websearch|research)\b[\s\S]{0,120}?(?:总结|概括|汇总|"
    r"conclude|summarize)",
    re.IGNORECASE,
)

# Task effects that by definition produce NO write/danger side effect.  A task
# declared with one of these must never be forced to supply WRITE/DANGER tool
# evidence -- for example a "verify file integrity" task whose description merely
# mentions that the file was written.  Treating it as a side-effect task would
# fail an otherwise-successful verification.
_NON_SIDE_EFFECT_EFFECTS = frozenset(
    {
        "read",
        "verify",
        "check",
        "none",
        "explain",
        "search",
        "query",
        "analysis",
    }
)


def is_supporting_effect(effect: object) -> bool:
    """True when ``effect`` denotes a non-mutating (read/verify/check) action."""
    return (
        str(getattr(effect, "value", effect) or "").strip().lower()
        in _NON_SIDE_EFFECT_EFFECTS
    )


def task_requires_side_effect_evidence(
    *,
    title: str,
    description: str = "",
    requirement: str = "",
    result: str = "",
    tools_hint: Iterable[str] = (),
    effect: str = "auto",
) -> bool:
    """Return true when accepting prose without a side effect would be unsafe."""
    declared_effect = str(getattr(effect, "value", effect) or "auto").lower()
    if declared_effect in {"write", "danger"}:
        return True
    # A non-mutating task (read/verify/check/...) produces no write side effect,
    # so it must not be forced to supply WRITE/DANGER tool evidence.
    if declared_effect in _NON_SIDE_EFFECT_EFFECTS:
        return False

    for tool_name in tools_hint:
        if str(tool_name).strip() and get_tool_risk(str(tool_name).strip()) >= RiskLevel.WRITE:
            return True

    request = "\n".join((title, description, requirement)).strip()
    # 锚定解释意图（请求以解释/总结词开头）：即使提到修复/重构话题也是只读
    anchored_explanation = bool(_EXPLANATION_RE.search(request))
    # 中段显式请求短语（请总结/总结一下/搜索…总结）：覆盖 ACTION+ARTIFACT
    # 启发式，但**不**覆盖强副作用动词。
    explicit_request = anchored_explanation or bool(
        _EXPLICIT_EXPLANATION_RE.search(request)
    )
    if not anchored_explanation and _STRONG_ACTION_RE.search(request):
        return True
    if not explicit_request and (
        _ACTION_RE.search(request) and _ARTIFACT_RE.search(request)
    ):
        return True
    return not explicit_request and bool(
        _COMPLETION_CLAIM_RE.search(result or "")
    )


def evidence_risk_level(record: ToolEvidence) -> RiskLevel | None:
    """Resolve the invocation risk, preserving pre-risk evidence compatibility."""
    if record.risk is None:
        return get_tool_risk(record.tool)
    try:
        return RiskLevel[str(record.risk).strip().upper()]
    except KeyError:
        return None


def has_verified_side_effect(evidence: Iterable[dict | ToolEvidence]) -> bool:
    """Return true only for an executed, successful WRITE/DANGER tool record."""
    for raw_record in evidence:
        try:
            record = (
                raw_record
                if isinstance(raw_record, ToolEvidence)
                else ToolEvidence.model_validate(raw_record)
            )
        except Exception:
            continue
        if not record.passed:
            continue
        risk = evidence_risk_level(record)
        if risk is None:
            continue
        if risk >= RiskLevel.WRITE:
            return True
    return False


__all__ = [
    "evidence_risk_level",
    "has_verified_side_effect",
    "task_requires_side_effect_evidence",
]
