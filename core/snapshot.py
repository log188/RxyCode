"""B7: Git 快照回滚基础（opencode snapshot 语义）。

LLM 调用前捕获工作区 Git 状态（status/diff），坏结局可回滚到快照点。
容错设计：git 不可用 / 非仓库 / 命令失败时快照标记为未捕获，
绝不阻断主流程。
"""

from __future__ import annotations

import logging
import subprocess
import time

_logger = logging.getLogger(__name__)

GIT_TIMEOUT_S = 15


def _run_git_quiet(args: list[str], cwd: str, stdin_text: str | None = None) -> str:
    """同步执行 git 命令；失败抛异常（由调用方决定容错）。"""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=GIT_TIMEOUT_S,
        input=stdin_text,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed rc={result.returncode}: "
            f"{result.stderr.strip()}"
        )
    return result.stdout


class GitSnapshot:
    """一次 Git 工作区快照。

    ``capture()`` 在 LLM 调用前调用，记录 git status --porcelain 与
    ``git diff``（含 staged）文本；``restore()`` 把工作区回滚到捕获点。
    """

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = str(repo_path)
        self.captured = False
        self.timestamp: float = 0.0
        self.status_text: str | None = None
        self.diff_text: str | None = None
        self._restore_diff: str | None = None

    def capture(self) -> bool:
        """捕获当前工作区状态；返回是否成功。

        **只捕获一次**（初始基线，luna R6-1）：已捕获过则直接返回 True，
        不覆盖——否则每轮 LLM 调用前的重复捕获会丢失原始基线。
        """
        if self.captured:
            return True
        try:
            status = _run_git_quiet(["status", "--porcelain"], self.repo_path)
            # 工作区 diff（仅 unstaged；apply -R 可精确反向应用）。
            diff = _run_git_quiet(["diff"], self.repo_path)
        except Exception as exc:  # noqa: BLE001 - 快照失败必须容错
            _logger.warning("B7 git snapshot capture skipped: %s", exc)
            self.captured = False
            return False
        self.status_text = status
        self.diff_text = diff
        self._restore_diff = diff
        self.timestamp = time.time()
        self.captured = True
        return True

    def restore(self) -> bool:
        """把工作区精确回滚到捕获点；未捕获 → 安全 no-op。

        两步恢复（luna R7-2）：
        1. ``git apply -R`` 反向应用当前工作区 diff（回滚 LLM 引入的修改）；
        2. ``git apply`` 重放快照时的 diff（恢复快照前的未提交修改）。

        快照前已有的 unstaged/staged 修改因此被保留，untracked 文件不受影响。
        """
        if not self.captured:
            return False
        try:
            current_diff = _run_git_quiet(["diff"], self.repo_path)
            if current_diff.strip():
                _run_git_quiet(["apply", "-R", "-p1"], self.repo_path, current_diff)
            if self._restore_diff and self._restore_diff.strip():
                _run_git_quiet(["apply", "-p1"], self.repo_path, self._restore_diff)
            return True
        except Exception as exc:  # noqa: BLE001 - 回滚失败不阻断
            _logger.warning("B7 git snapshot restore failed: %s", exc)
            return False

    def to_dict(self) -> dict:
        return {
            "captured": self.captured,
            "timestamp": self.timestamp,
            "status_text": (self.status_text or "")[:2000],
            "diff_text": (self.diff_text or "")[:2000],
        }
