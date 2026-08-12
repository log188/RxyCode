"""Persistence and lifecycle contract for Desktop task history."""

from __future__ import annotations

from pathlib import Path

from appserver.sessions import SessionStore
from appserver.task_store import DesktopTaskStore
from appserver.server import AppServer


def test_task_store_persists_rename_trash_restore_and_purge(tmp_path: Path):
    path = tmp_path / "desktop" / "tasks.json"
    store = DesktopTaskStore(path)
    record = store.upsert(
        session_id="s1",
        title="Release audit",
        workspace_root=tmp_path / "workspace",
        model_id="deepseek/deepseek-v4",
        provider_id="deepseek",
    )

    assert record["session_id"] == "s1"
    store.rename("s1", "Payment audit")
    store.trash("s1")
    assert store.list(include_trashed=False) == []
    assert store.list(include_trashed=True)[0]["trashed_at"] is not None

    reloaded = DesktopTaskStore(path)
    reloaded.restore("s1")
    assert reloaded.list()[0]["title"] == "Payment audit"
    reloaded.purge("s1")
    assert reloaded.list(include_trashed=True) == []


def test_session_store_hydrates_persistent_tasks_and_updates_them(tmp_path: Path):
    task_store = DesktopTaskStore(tmp_path / "tasks.json")
    first = SessionStore(task_store=task_store)
    record = first.create(tmp_path / "workspace", title="Investigate outage")
    first.rename(record.session_id, "Outage report")
    first.set_model(record.session_id, "glm/glm-5", "glm")

    second = SessionStore(task_store=DesktopTaskStore(tmp_path / "tasks.json"))
    hydrated = second.get(record.session_id)
    assert hydrated is not None
    assert hydrated.title == "Outage report"
    assert hydrated.model_id == "glm/glm-5"
    assert hydrated.provider_id == "glm"


def test_server_task_lifecycle_routes_keep_workspace_intact(monkeypatch, tmp_path: Path):
    import asyncio
    from unittest.mock import AsyncMock

    server = AppServer(stub=True)
    server._initialized = True
    record = server._sessions.create(tmp_path / "workspace", title="Audit")
    responses: list[object] = []
    monkeypatch.setattr(
        server,
        "_respond",
        AsyncMock(side_effect=lambda _request_id, payload: responses.append(payload)),
    )

    asyncio.run(server._handle_sessions_list({"include_trashed": False}, 1))
    assert responses[-1]["sessions"][0]["session_id"] == record.session_id

    asyncio.run(
        server._handle_session_rename(
            {"session_id": record.session_id, "title": "Renamed"}, 2
        )
    )
    asyncio.run(
        server._handle_session_trash({"session_id": record.session_id}, 3)
    )
    asyncio.run(server._handle_sessions_list({"include_trashed": False}, 4))
    assert responses[-1]["sessions"] == []
    asyncio.run(
        server._handle_session_restore({"session_id": record.session_id}, 5)
    )
    asyncio.run(
        server._handle_session_purge({"session_id": record.session_id}, 6)
    )
    assert not (tmp_path / "workspace").exists()


def test_server_persists_host_notifications_for_cursor_replay(tmp_path: Path):
    server = AppServer(stub=True)
    server._task_store = DesktopTaskStore(tmp_path / "tasks.json")
    server._sessions = SessionStore(task_store=server._task_store)
    record = server._sessions.create(tmp_path / "workspace", title="Replay audit")

    server._persist_notification({
        "jsonrpc": "2.0",
        "method": "event/tool_end",
        "params": {
            "session_id": record.session_id,
            "call_id": "call-1",
            "ok": True,
            "summary": "read completed",
        },
    })

    events, cursor, gap = server._task_store.events(record.session_id, 0)
    assert cursor == 1
    assert gap is False
    assert events[0]["method"] == "event/tool_end"
    assert events[0]["params"]["call_id"] == "call-1"


def test_server_replay_skips_stream_deltas_and_redacts_tool_secrets(tmp_path: Path):
    server = AppServer(stub=True)
    server._task_store = DesktopTaskStore(tmp_path / "tasks.json")
    server._sessions = SessionStore(task_store=server._task_store)
    record = server._sessions.create(tmp_path / "workspace", title="Safe replay")

    server._persist_notification({
        "method": "event/message_delta",
        "params": {"session_id": record.session_id, "text": "do not persist prompt-like text"},
    })
    server._persist_notification({
        "method": "event/tool_begin",
        "params": {
            "session_id": record.session_id,
            "call_id": "call-secret",
            "tool_name": "bash",
            "arguments": {"command": "curl --api-key sk-live-secret https://example.invalid"},
        },
    })

    events, cursor, gap = server._task_store.events(record.session_id, 0)
    assert cursor == 1
    assert gap is False
    assert len(events) == 1
    serialized = str(events[0])
    assert "do not persist prompt-like text" not in serialized
    assert "sk-live-secret" not in serialized
    assert "[REDACTED]" in serialized
