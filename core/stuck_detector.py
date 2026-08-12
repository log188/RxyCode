"""B7: 死循环检测（OpenHands stuck.py 规则式语义）。

检测工具循环中的重复模式，达到阈值后向主循环报告 stuck，
由调用方决定干预（回滚 / 引导语 / 终止）。规则式、无 LLM 依赖。
"""

from __future__ import annotations

import json
from typing import Any


def _args_fingerprint(args: Any) -> str:
    """把工具参数规范化为稳定指纹（dict 排序 key）。

    args 为 dict 或可 JSON 序列化对象；失败时退回 repr 以保证可用。
    """
    try:
        return json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(args)


class StuckDetector:
    """跨轮工具循环重复模式检测。

    - 连续相同 (name, args 指纹) ≥ threshold 次 → stuck；
    - 交替模式（A,B,A,B…）覆盖 ≥ 2*threshold 次 → stuck；
    - 连续失败（failed=True）同工具 ≥ threshold 次 → stuck。

    阈值默认 3（opencode DOOM_LOOP_THRESHOLD=3），可配置。
    """

    def __init__(self, threshold: int = 3) -> None:
        if not isinstance(threshold, int) or threshold < 2:
            raise ValueError(f"stuck threshold must be int >= 2, got {threshold!r}")
        self.threshold = threshold
        self._history: list[tuple[str, str, bool]] = []
        self._stuck_reason: str | None = None

    def reset(self) -> None:
        """清空历史（新一轮任务开始时调用）。"""
        self._history = []
        self._stuck_reason = None

    def record(self, tool_name: str, tool_args: Any = None, *, failed: bool = False) -> bool:
        """记录一次动作；返回是否已达死循环（stuck）。

        ``failed=True`` 表示该工具执行失败（错误回喂场景）。
        """
        fingerprint = _args_fingerprint(tool_args)
        self._history.append((tool_name, fingerprint, failed))
        if self._detect_repetition() or self._detect_alternation() or self._detect_failures():
            self._stuck_reason = (
                f"stuck after {len(self._history)} tool rounds "
                f"(threshold={self.threshold})"
            )
            return True
        return False

    def is_stuck(self) -> bool:
        """当前是否已 stuck（最后一次 record 触发）。"""
        return self._stuck_reason is not None

    @property
    def stuck_reason(self) -> str | None:
        return self._stuck_reason

    def _last(self, n: int) -> list[tuple[str, str, bool]]:
        return self._history[-n:]

    def _detect_repetition(self) -> bool:
        """连续相同 (name, args) ≥ threshold 次。"""
        t = self.threshold
        if len(self._history) < t:
            return False
        tail = self._last(t)
        signatures = {(name, fp) for name, fp, _failed in tail}
        return len(signatures) == 1

    def _detect_alternation(self) -> bool:
        """交替模式（周期 2..threshold）覆盖 ≥ 2*threshold 次。

        与连续相同不同：要求最近的 2t 次动作落入同一小周期
        （如 A,B,A,B），且周期 ≥ 2 才判定（避免误伤正常多轮）。
        """
        t = self.threshold
        if len(self._history) < 2 * t:
            return False
        tail = self._last(2 * t)
        for period in range(2, t + 1):
            cycle = [(name, fp) for name, fp, _failed in tail[:period]]
            if len(set(cycle)) < 2:
                continue  # 周期内全同 → 交给 repetition 判定
            matches = all(
                (name, fp) == cycle[index % period]
                for index, (name, fp, _failed) in enumerate(tail)
            )
            if matches:
                return True
        return False

    def _detect_failures(self) -> bool:
        """连续失败（failed=True 且同工具）≥ threshold 次。"""
        t = self.threshold
        if len(self._history) < t:
            return False
        tail = self._last(t)
        if not all(failed for _name, _fp, failed in tail):
            return False
        names = {name for name, _fp, _failed in tail}
        return len(names) == 1
