"""成员邮箱。

所有消息都经团长中转（DC2，抄 WorkBuddy「所有跨成员的信息流必须经主理人
中转」）。刻意做成 append-only 且记录 relayed_by，理由是可追溯——多 Agent
系统最难调试的问题是"这个错误判断是谁传出去的"。

对照：腾讯 CodeBuddy Agent Teams 允许成员直连。我们不采纳，因为直连会让
委派树变成图，失去限流点和 trace 的父子关系。
"""

from __future__ import annotations

from dataclasses import dataclass


class MailboxError(ValueError):
    """Illegal mailbox operation."""


@dataclass(frozen=True)
class MailMessage:
    from_role: str
    to_role: str
    body: str
    relayed_by: str
    kind: str = "consult"


class Mailbox:
    """Append-only directed messages. Every row records the coordinator."""

    def __init__(self) -> None:
        self._messages: list[MailMessage] = []

    def relay(
        self,
        *,
        from_role: str,
        to_role: str,
        body: str,
        relayed_by: str,
        kind: str = "consult",
    ) -> MailMessage:
        if not relayed_by:
            raise MailboxError("relayed_by is required")
        if from_role == to_role:
            raise MailboxError("members may not mail themselves")
        msg = MailMessage(
            from_role=from_role,
            to_role=to_role,
            body=body,
            relayed_by=relayed_by,
            kind=kind,
        )
        self._messages.append(msg)
        return msg

    def all(self) -> list[MailMessage]:
        return list(self._messages)
