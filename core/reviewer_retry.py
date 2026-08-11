"""B7: reviewer 重试（SWE-agent reviewer.py 语义，默认关闭）。

独立 reviewer 打分；不达标重跑；同分取 API 调用最少者。
默认关闭（CB8：默认路径行为不变）；开启时有 API 调用预算保护。
"""

from __future__ import annotations

from typing import Any


class ReviewerBudget:
    """API 调用预算保护：超过 max_calls 不再重试。"""

    def __init__(self, max_calls: int) -> None:
        if not isinstance(max_calls, int) or max_calls < 1:
            raise ValueError(f"max_calls must be int >= 1, got {max_calls!r}")
        self.max_calls = max_calls
        self.calls = 0

    def consume(self) -> None:
        self.calls += 1

    def can_retry(self) -> bool:
        return self.calls < self.max_calls

    def remaining(self) -> int:
        return max(0, self.max_calls - self.calls)


def pick_best_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """从多次尝试中选出最优。

    评分高者优先；**同分取 API 调用最少者**（SWE-agent 语义）。
    attempts 元素需含 ``score``（float）与 ``api_calls``（int）。
    """
    if not attempts:
        return None
    return max(
        attempts,
        key=lambda a: (
            float(a.get("score", 0.0)),
            -int(a.get("api_calls", 0)),
        ),
    )
