import asyncio
from unittest.mock import AsyncMock

import pytest

from appserver.server import AppServer


@pytest.mark.asyncio
async def test_worker_notifications_are_written_in_fifo_order(monkeypatch):
    """A slow first worker event must not let a later event overtake it."""
    server = AppServer(stub=True)
    first_write_started = asyncio.Event()
    release_first_write = asyncio.Event()
    written: list[str] = []

    async def write(message):
        method = str(message.get("method", ""))
        if method == "event/tool_end":
            first_write_started.set()
            await release_first_write.wait()
        written.append(method)

    monkeypatch.setattr("appserver.server.write_message", write)

    server._emit_host_notification(
        {"jsonrpc": "2.0", "method": "event/tool_end", "params": {}}
    )
    server._emit_host_notification(
        {"jsonrpc": "2.0", "method": "event/recovery_started", "params": {}}
    )

    await asyncio.wait_for(first_write_started.wait(), timeout=1)
    await asyncio.sleep(0)
    assert written == []

    release_first_write.set()
    await server._drain_emit_writes()
    assert written == ["event/tool_end", "event/recovery_started"]


@pytest.mark.asyncio
async def test_appserver_routes_subagent_rpc_to_primary_worker(tmp_path, monkeypatch):
    server = AppServer(stub=True)
    server._initialized = True
    session = server._sessions.create(tmp_path)
    server._active_session_id = session.session_id
    host = AsyncMock()
    host.run_subagent_rpc.return_value = {
        "accepted": True,
        "request_id": "req-1",
    }
    monkeypatch.setattr(server, "_host_for_session", AsyncMock(return_value=host))
    respond = AsyncMock()
    monkeypatch.setattr(server, "_respond", respond)

    await server._dispatch(
        {
            "jsonrpc": "2.0",
            "id": 71,
            "method": "task/start",
            "params": {"agent_id": "explore", "prompt": "Audit the release"},
        }
    )

    host.ensure_bootstrapped.assert_awaited_once()
    call = host.run_subagent_rpc.await_args
    assert call.args[0] == "task/start"
    assert call.args[1]["root_session_id"] == session.session_id
    assert call.args[1]["parent_session_id"] == session.session_id
    assert callable(call.kwargs["emit"])
    respond.assert_awaited_once_with(
        71, {"accepted": True, "request_id": "req-1"}
    )


@pytest.mark.asyncio
async def test_capability_without_primary_session_is_cleanly_disabled(monkeypatch):
    server = AppServer(stub=True)
    server._initialized = True
    respond = AsyncMock()
    monkeypatch.setattr(server, "_respond", respond)

    await server._dispatch(
        {
            "jsonrpc": "2.0",
            "id": 72,
            "method": "subagents/capability",
            "params": {},
        }
    )

    result = respond.await_args.args[1]
    assert result["subagents_enabled"] is False
    assert result["task"] is False
