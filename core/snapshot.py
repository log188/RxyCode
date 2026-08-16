"""B7: Git 快照回滚基础（opencode snapshot 语义）。

LLM 调用前捕获工作区 Git 状态（status/diff），坏结局可回滚到快照点。
容错设计：git 不可用 / 非仓库 / 命令失败时快照标记为未捕获，
绝不阻断主流程。
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time

_logger = logging.getLogger(__name__)

# A snapshot is a best-effort rollback aid, not a prerequisite for an LLM
# request.  A hung Windows worktree must not consume the whole first-token
# budget.  Callers may override this in focused tests.
GIT_TIMEOUT_S = 1.0


def _run_git_quiet(args: list[str], cwd: str, stdin_text: str | None = None) -> str:
    """同步执行 git 命令；失败抛异常（由调用方决定容错）。"""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
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


async def _run_git_async(
    args: list[str], cwd: str, stdin_text: str | None = None
) -> str:
    """Run a read-only git command without blocking the appserver loop.

    ``subprocess.run(timeout=...)`` is synchronous and was previously called
    from the async AgentV2 turn.  On Windows a stuck git child can therefore
    block watchdog heartbeats while Python waits for process teardown.  The
    async subprocess is explicitly killed on timeout and its pipes are
    drained before the timeout is surfaced.
    """
    process = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        stdin=asyncio.subprocess.PIPE if stdin_text is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    input_bytes = None if stdin_text is None else stdin_text.encode("utf-8")
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=input_bytes), timeout=GIT_TIMEOUT_S
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise TimeoutError(
            f"git {' '.join(args)} timed out after {GIT_TIMEOUT_S:.0f}s"
        ) from exc
    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"git {' '.join(args)} failed rc={process.returncode}: {detail}"
        )
    return stdout.decode("utf-8", errors="replace")


class GitSnapshot:
    """一次 Git 工作区快照。

    ``capture()`` 在 LLM 调用前调用，记录 git status --porcelain 与
    ``git diff``（含 staged）文本；``restore()`` 把工作区回滚到捕获点。
    """

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = str(repo_path)
        self.captured = False
        # Optional capture is attempted once per snapshot. A failed attempt
        # must not add one Git timeout before every subsequent model round.
        self._capture_attempted = False
        self.timestamp: float = 0.0
        self.status_text: str | None = None
        self.diff_text: str | None = None
        self._restore_diff: str | None = None

    def capture(self) -> bool:
        """捕获当前工作区状态；返回是否成功。

        **只捕获一次**（初始基线，luna R6-1）：已捕获过则直接返回 True，
        不覆盖——否则每轮 LLM 调用前的重复捕获会丢失原始基线。
        """
        if self._capture_attempted:
            return self.captured
        self._capture_attempted = True
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

    async def capture_async(self) -> bool:
        """Capture a snapshot without blocking an async AgentV2 turn."""
        if self._capture_attempted:
            return self.captured
        self._capture_attempted = True
        if self.captured:
            return True
        try:
            status = await asyncio.wait_for(
                _run_git_async(["status", "--porcelain"], self.repo_path),
                timeout=GIT_TIMEOUT_S,
            )
            diff = await asyncio.wait_for(
                _run_git_async(["diff"], self.repo_path), timeout=GIT_TIMEOUT_S
            )
        except Exception as exc:  # noqa: BLE001 - snapshot failure is optional
            _logger.warning("B7 async git snapshot capture skipped: %s", exc)
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
