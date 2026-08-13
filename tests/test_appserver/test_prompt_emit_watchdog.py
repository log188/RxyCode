"""Prompt-job liveness must survive child-session RPCs on the same worker.

Root cause of same-session second-turn ``job stalled >120s``: GUI/TUI
``child_sessions/list|events`` call ``AgentHost.run_subagent_rpc``, which
replaced ``host._emit``. Worker heartbeats then went through
``_emit_host_notification`` (no ``touch_job``). Collapsed thinking emits
no reasoning events, so the watchdog saw 120s of silence and killed the
worker. OpenCode/Claude do not treat silent thinking as a dead job.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from appserver.agent_host import AgentHost
from appserver.server import AppServer
from appserver.watchdog import WatchdogState


def _host(tmp_path) -> AgentHost:
    import asyncio

    loop = asyncio.get_running_loop()
    return AgentHost(
        session_id="s1",
        workspace_root=tmp_path,
        stub=True,
        project_root=tmp_path,
        forward_server_request=AsyncMock(),
        main_loop=loop,
    )


@pytest.mark.asyncio
async def test_subagent_rpc_does_not_replace_live_prompt_emit(tmp_path, monkeypatch):
    host = _host(tmp_path)
    prompt_emit = object()
    host._emit = prompt_emit
    monkeypatch.setattr(host, "_pipe_request", AsyncMock(return_value={"ok": True}))

    await host.run_subagent_rpc(
        "child_sessions/list",
        {"root_session_id": "s1"},
        timeout=5.0,
        emit=lambda _msg: None,
    )

    assert host._emit is prompt_emit


def test_host_notification_touches_active_job_for_session():
    server = AppServer(stub=True)
    server._watchdog = WatchdogState()
    server._watchdog.register_job("job-1", "s1", request_id=1)
    job = server._watchdog.jobs["job-1"]
    job.last_progress_at = time.monotonic() - 50.0

    server._emit_host_notification(
        {
            "jsonrpc": "2.0",
            "method": "event/heartbeat",
            "params": {"session_id": "s1"},
        }
    )

    assert time.monotonic() - job.last_progress_at < 1.0
    assert server._watchdog.stalled_jobs() == []
