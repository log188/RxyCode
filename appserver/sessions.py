"""In-process session registry for appserver."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .task_store import DesktopTaskStore


@dataclass
class AppSessionRecord:
    session_id: str
    workspace_root: Path
    title: str = "New task"
    model_id: str | None = None
    provider_id: str | None = None
    status: str = "queued"
    trashed_at: str | None = None
    created_at: str = ""
    updated_at: str = ""
    usage: dict[str, object] = field(
        default_factory=lambda: {
            "input_tokens": None,
            "output_tokens": None,
            "cache_hit_tokens": None,
            "cache_write_tokens": None,
            "cache_hit_rate": None,
            "reporting_status": "not_reported",
        }
    )


class SessionStore:
    """Track multiple concurrent sessions in one appserver process."""

    def __init__(self, *, task_store: DesktopTaskStore | None = None) -> None:
        self._sessions: dict[str, AppSessionRecord] = {}
        self._task_store = task_store
        if task_store is not None:
            for task in task_store.list(include_trashed=True):
                self._sessions[str(task["session_id"])] = self._from_task(task)

    def create(
        self,
        workspace_root: Path | str,
        *,
        title: str = "新任务",
        model_id: str | None = None,
        provider_id: str | None = None,
    ) -> AppSessionRecord:
        session_id = uuid.uuid4().hex[:12]
        record = AppSessionRecord(
            session_id=session_id,
            workspace_root=Path(workspace_root),
            title=title,
            model_id=model_id,
            provider_id=provider_id,
        )
        self._sessions[session_id] = record
        self._persist(record)
        return record

    def get(self, session_id: str) -> AppSessionRecord | None:
        return self._sessions.get(session_id)

    def list_ids(self) -> list[str]:
        return list(self._sessions.keys())

    def set_model(
        self, session_id: str, model_id: str, provider_id: str | None = None
    ) -> AppSessionRecord:
        record = self._sessions.get(session_id)
        if record is None:
            raise KeyError(session_id)
        record.model_id = model_id
        record.provider_id = provider_id
        self._persist(record)
        return record

    def list(self, *, include_trashed: bool = False) -> list[AppSessionRecord]:
        values = list(self._sessions.values())
        if not include_trashed:
            values = [record for record in values if record.trashed_at is None]
        return sorted(values, key=lambda record: record.updated_at, reverse=True)

    def rename(self, session_id: str, title: str) -> AppSessionRecord:
        record = self._require(session_id)
        clean = title.strip()
        if not clean:
            raise ValueError("title is required")
        record.title = clean
        self._touch(record)
        self._persist(record)
        return record

    def trash(self, session_id: str) -> AppSessionRecord:
        record = self._require(session_id)
        record.trashed_at = _now()
        self._touch(record)
        self._persist(record)
        return record

    def restore(self, session_id: str) -> AppSessionRecord:
        record = self._require(session_id)
        record.trashed_at = None
        self._touch(record)
        self._persist(record)
        return record

    def purge(self, session_id: str) -> None:
        self._require(session_id)
        self._sessions.pop(session_id, None)
        if self._task_store is not None and self._task_store.get(session_id) is not None:
            self._task_store.purge(session_id)

    def update_status(self, session_id: str, status: str) -> AppSessionRecord | None:
        record = self._sessions.get(session_id)
        if record is None:
            return None
        record.status = status
        self._touch(record)
        self._persist(record)
        return record

    def update_usage(self, session_id: str, usage: dict[str, object]) -> AppSessionRecord | None:
        record = self._sessions.get(session_id)
        if record is None:
            return None
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_hit_tokens",
            "cache_write_tokens",
            "cache_hit_rate",
            "reporting_status",
        ):
            if key in usage:
                record.usage[key] = usage[key]
        self._touch(record)
        self._persist(record)
        return record

    def _require(self, session_id: str) -> AppSessionRecord:
        record = self._sessions.get(session_id)
        if record is None:
            raise KeyError(session_id)
        return record

    @staticmethod
    def _from_task(task: dict) -> AppSessionRecord:
        return AppSessionRecord(
            session_id=str(task["session_id"]),
            workspace_root=Path(str(task["workspace_root"])),
            title=str(task.get("title") or "New task"),
            model_id=task.get("model_id"),
            provider_id=task.get("provider_id"),
            status=str(task.get("status") or "queued"),
            trashed_at=task.get("trashed_at"),
            created_at=str(task.get("created_at") or ""),
            updated_at=str(task.get("updated_at") or ""),
            usage=dict(task.get("usage") or {}),
        )

    @staticmethod
    def _touch(record: AppSessionRecord) -> None:
        record.updated_at = _now()

    def _persist(self, record: AppSessionRecord) -> None:
        if self._task_store is None:
            return
        if not record.created_at:
            record.created_at = _now()
        if not record.updated_at:
            record.updated_at = record.created_at
        self._task_store.upsert(
            session_id=record.session_id,
            title=record.title,
            workspace_root=record.workspace_root,
            model_id=record.model_id,
            provider_id=record.provider_id,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
            trashed_at=record.trashed_at,
            usage=record.usage,
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
