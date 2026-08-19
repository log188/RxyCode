"""阶段产出物黑板。

append-only、带作者、按 key 授权可见。同 key 再 put 追加新版本，读取最新。
默认不是全部可见：调用方必须传入授权的 context_keys。
"""

from __future__ import annotations

from dataclasses import dataclass


class BlackboardError(ValueError):
    """Illegal blackboard operation."""


class BlackboardFullError(BlackboardError):
    """Session blackboard exceeded the byte cap."""


@dataclass(frozen=True)
class BoardEntry:
    key: str
    value: str
    author_role: str
    version: int


class Blackboard:
    DEFAULT_LIMIT = 1_000_000

    def __init__(self, *, max_bytes: int = DEFAULT_LIMIT) -> None:
        self._log: dict[str, list[BoardEntry]] = {}
        self._max_bytes = max_bytes
        self._bytes = 0

    def put(self, key: str, value: str, author_role: str) -> BoardEntry:
        encoded = value.encode("utf-8")
        if self._bytes + len(encoded) > self._max_bytes:
            raise BlackboardFullError(
                f"blackboard would exceed {self._max_bytes} bytes"
            )
        version = len(self._log.get(key, ())) + 1
        entry = BoardEntry(
            key=key, value=value, author_role=author_role, version=version
        )
        self._log.setdefault(key, []).append(entry)
        self._bytes += len(encoded)
        return entry

    def get(self, key: str) -> str | None:
        rows = self._log.get(key)
        if not rows:
            return None
        return rows[-1].value

    def versions(self, key: str) -> list[BoardEntry]:
        return list(self._log.get(key, ()))

    def list_keys(self) -> list[str]:
        return list(self._log)

    def view(self, context_keys: list[str]) -> dict[str, str]:
        """Only authorized keys. Default is empty if none granted."""
        visible: dict[str, str] = {}
        for key in context_keys:
            value = self.get(key)
            if value is not None:
                visible[key] = value
        return visible
