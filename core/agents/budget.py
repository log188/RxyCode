"""成本熔断。

Anthropic 实测：多 Agent 消耗约 15 倍于普通对话的 token，且他们公开承认
自己的架构没有熔断——一个失控的子代理能让单次成本再翻 10 倍。腾讯
WorkBuddy 专家团的积分消耗也是单专家的 3-5 倍。

四道闸门，任何一道触发都立即停止整个团队运行并返回已有产出。
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from RxyCode.RxyCode1_1_0.protocol.agents import TeamSpec


class BudgetExceeded(RuntimeError):
    """A team-level fuse tripped. Coordinator must return a partial answer."""


def _settings_agents() -> dict[str, Any]:
    try:
        from RxyCode.RxyCode1_1_0.config.settings import load_config

        raw = load_config().get("agents") or {}
        return dict(raw) if isinstance(raw, Mapping) else {}
    except Exception:
        return {}


class BudgetGuard:
    def __init__(
        self,
        team: TeamSpec | None = None,
        *,
        overrides: Mapping[str, Any] | None = None,
    ) -> None:
        self._overrides = dict(overrides or {})
        self._token_budget = 500_000
        self._timeout_s = 1800.0
        self._started_at = time.monotonic()
        self._deadline = self._started_at + self._timeout_s
        self._max_delegations = 20
        self._tokens_used = 0
        self._delegations = 0
        if team is not None:
            self._bind(team)

    def start(self, team: TeamSpec) -> None:
        self._tokens_used = 0
        self._delegations = 0
        self._bind(team)

    def _bind(self, team: TeamSpec) -> None:
        cfg = _settings_agents()

        def pick(key: str, fallback: Any) -> Any:
            if key in self._overrides and self._overrides[key] is not None:
                return self._overrides[key]
            if key in cfg and cfg[key] is not None:
                return cfg[key]
            return fallback

        self._token_budget = int(pick("total_token_budget", team.total_token_budget))
        self._timeout_s = float(pick("total_timeout_s", team.total_timeout_s))
        self._started_at = time.monotonic()
        self._deadline = self._started_at + self._timeout_s
        self._max_delegations = int(pick("max_delegations", team.max_delegations))

    def snapshot(self) -> dict[str, Any]:
        """Read-only budget view for F12 team-tree headers."""
        return {
            "tokens_used": int(self._tokens_used),
            "token_budget": int(self._token_budget),
            "elapsed_s": max(0.0, time.monotonic() - self._started_at),
            "timeout_s": float(self._timeout_s),
            "delegations": int(self._delegations),
            "max_delegations": int(self._max_delegations),
        }

    def add_tokens(self, n: int) -> None:
        self._tokens_used += max(0, int(n))
        self.check()

    def add_delegation(self) -> None:
        self._delegations += 1
        self.check()

    def consume_consult(self) -> None:
        self.add_delegation()

    def check(self) -> None:
        """任何一道闸门触发就抛 BudgetExceeded。"""
        if self._tokens_used > self._token_budget:
            raise BudgetExceeded(f"token budget {self._token_budget} exhausted")
        if time.monotonic() > self._deadline:
            raise BudgetExceeded("wall-clock deadline reached")
        if self._delegations > self._max_delegations:
            raise BudgetExceeded(
                f"delegation count exceeded {self._max_delegations} — "
                f"likely a ping-pong loop between two stages"
            )
