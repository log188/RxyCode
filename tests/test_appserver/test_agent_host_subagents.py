import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from appserver.agent_host import AgentHost


def _host(tmp_path: Path) -> AgentHost:
    loop = asyncio.get_running_loop()
    return AgentHost(
        session_id="primary-1",
        workspace_root=tmp_path,
        stub=True,
        project_root=tmp_path,
        forward_server_request=AsyncMock(),
        main_loop=loop,
    )


@pytest.mark.asyncio
async def test_agent_host_forwards_child_session_notifications(tmp_path):
    host = _host(tmp_path)
    emitted: list[dict] = []
    host._emit = emitted.append

    notification = {
        "jsonrpc": "2.0",
        "method": "child_session/created",
        "params": {"root_session_id": "primary-1", "session_id": "child-1"},
    }
    host._route_notification(notification)

    assert emitted == [notification]


@pytest.mark.asyncio
async def test_agent_host_forwards_question_request_like_approval(tmp_path):
    host = _host(tmp_path)
    host._forward_server_request = AsyncMock(
        return_value={"question_id": "q1", "answer": "response"}
    )
    host._respond_to_worker = MagicMock()

    host._route_notification(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "question/request",
            "params": {
                "session_id": "s1",
                "question_id": "q1",
                "question": "哪个环节慢？",
            },
        }
    )
    await asyncio.sleep(0.05)

    host._forward_server_request.assert_awaited_once()
    assert host._forward_server_request.await_args.args[0] == "question/request"
    host._respond_to_worker.assert_called_once_with(
        7, {"question_id": "q1", "answer": "response"}, error=None
    )


@pytest.mark.asyncio
async def test_agent_host_routes_subagent_rpc_through_owned_worker(tmp_path, monkeypatch):
    host = _host(tmp_path)
    pipe_request = AsyncMock(return_value={"subagents_enabled": True})
    monkeypatch.setattr(host, "_pipe_request", pipe_request)
    emitted: list[dict] = []
    emit = emitted.append

    result = await host.run_subagent_rpc(
        "subagents/capability",
        {"root_session_id": "primary-1"},
        timeout=5.0,
        emit=emit,
    )

    assert result == {"subagents_enabled": True}
    assert host._emit is emit
    pipe_request.assert_awaited_once_with(
        "subagents/capability",
        {"root_session_id": "primary-1"},
        timeout=5.0,
    )
