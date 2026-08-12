"""Durable Desktop task metadata kept outside user workspaces.

The renderer owns presentation state, while this store owns only task
metadata and protocol replay cursors.  It deliberately never writes into a
workspace root and never stores prompt contents or credentials.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from ..config.settings import get_data_dir
except ImportError:
    from config.settings import get_data_dir


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class DesktopTaskStore:
    """Small atomic JSON store for task summaries and ordered event metadata."""

    def __init__(self, path: Path | str | None = None, *, persistent: bool = True) -> None:
        self.path = Path(path) if path is not None else get_data_dir() / "desktop" / "tasks.json"
        self.persistent = persistent
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = {"tasks": {}, "events": {}}
        self._load()

    def _load(self) -> None:
        if not self.persistent:
            return
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return
        if not isinstance(value, dict):
            return
        tasks = value.get("tasks")
        events = value.get("events")
        if isinstance(tasks, dict):
            self._data["tasks"] = tasks
        if isinstance(events, dict):
            # Before the cursor fix, persisted ``seq`` was copied directly
            # from protocol events.  Normalize that legacy shape on load so a
            # reconnect cursor always addresses this store's append order,
            # while retaining the original protocol sequence for diagnostics.
            normalized: dict[str, list[dict[str, Any]]] = {}
            for session_id, raw_events in events.items():
                if not isinstance(raw_events, list):
                    continue
                session_events: list[dict[str, Any]] = []
                for storage_seq, raw_event in enumerate(raw_events, start=1):
                    if not isinstance(raw_event, dict):
                        continue
                    value = dict(raw_event)
                    old_seq = value.get("seq")
                    if "protocol_seq" not in value and isinstance(old_seq, int):
                        value["protocol_seq"] = old_seq
                    value["seq"] = storage_seq
                    session_events.append(value)
                normalized[str(session_id)] = session_events
            self._data["events"] = normalized

    def _save(self) -> None:
        if not self.persistent:
            return
        payload = json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True)
        fd, temp_name = tempfile.mkstemp(prefix="tasks-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def upsert(
        self,
        *,
        session_id: str,
        title: str,
        workspace_root: Path | str,
        model_id: str | None = None,
        provider_id: str | None = None,
        status: str = "queued",
        created_at: str | None = None,
        updated_at: str | None = None,
        trashed_at: str | None = None,
        usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        old = self._data["tasks"].get(session_id)
        now = _now()
        task = {
            "session_id": session_id,
            "title": title,
            "workspace_root": str(workspace_root),
            "model_id": model_id,
            "provider_id": provider_id,
            "status": status,
            "created_at": created_at or (old or {}).get("created_at") or now,
            "updated_at": updated_at or now,
            "trashed_at": trashed_at,
            "child_count": int((old or {}).get("child_count", 0) or 0),
            "usage": usage or (old or {}).get("usage") or {
                "input_tokens": None,
                "output_tokens": None,
                "cache_hit_tokens": None,
                "cache_write_tokens": None,
                "cache_hit_rate": None,
                "reporting_status": "not_reported",
            },
        }
        self._data["tasks"][session_id] = task
        self._save()
        return dict(task)

    def list(self, *, include_trashed: bool = False) -> list[dict[str, Any]]:
        values = list(self._data["tasks"].values())
        if not include_trashed:
            values = [item for item in values if item.get("trashed_at") is None]
        return sorted(values, key=lambda item: str(item.get("updated_at", "")), reverse=True)

    def get(self, session_id: str) -> dict[str, Any] | None:
        task = self._data["tasks"].get(session_id)
        return dict(task) if isinstance(task, dict) else None

    def rename(self, session_id: str, title: str) -> dict[str, Any]:
        task = self._require(session_id)
        clean = title.strip()
        if not clean:
            raise ValueError("title is required")
        task["title"] = clean
        task["updated_at"] = _now()
        self._save()
        return dict(task)

    def trash(self, session_id: str) -> dict[str, Any]:
        task = self._require(session_id)
        task["trashed_at"] = _now()
        task["updated_at"] = _now()
        self._save()
        return dict(task)

    def restore(self, session_id: str) -> dict[str, Any]:
        task = self._require(session_id)
        task["trashed_at"] = None
        task["updated_at"] = _now()
        self._save()
        return dict(task)

    def purge(self, session_id: str) -> None:
        self._require(session_id)
        del self._data["tasks"][session_id]
        self._data["events"].pop(session_id, None)
        self._save()

    def append_event(self, session_id: str, event: dict[str, Any]) -> int:
        events = self._data["events"].setdefault(session_id, [])
        if not isinstance(events, list):
            events = []
            self._data["events"][session_id] = events
        seq = len(events) + 1
        value = dict(event)
        protocol_seq = value.pop("seq", None)
        value["seq"] = seq
        if isinstance(protocol_seq, int):
            value["protocol_seq"] = protocol_seq
        events.append(value)
        self._save()
        return seq

    def events(self, session_id: str, cursor: int = 0) -> tuple[list[dict[str, Any]], int, bool]:
        values = self._data["events"].get(session_id, [])
        if not isinstance(values, list):
            return [], cursor, False
        ordered = [item for item in values if isinstance(item, dict)]
        latest = int(ordered[-1].get("seq", 0)) if ordered else 0
        selected = [item for item in ordered if int(item.get("seq", 0)) > cursor]
        expected = cursor + 1
        gap = bool(selected and int(selected[0].get("seq", expected)) > expected)
        return selected, latest, gap

    def _require(self, session_id: str) -> dict[str, Any]:
        task = self._data["tasks"].get(session_id)
        if not isinstance(task, dict):
            raise KeyError(session_id)
        return task
