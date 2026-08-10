from __future__ import annotations

import asyncio
from dataclasses import dataclass

from protocol.subagents import (
    AgentDefinition, AgentMode, ChildStatus, EffectiveTaskPolicy,
    PermissionSpec, PermissionVerdict, TaskPermissionSpec, TaskRequest,
    ToolPermission, TriggerKind, WorkspaceMode, WorkspaceScope,
)
from core.subagents.runtime import create_child_runtime
from core.subagents.sessions import create_child_session


@dataclass
class FakeAgent:
    answer: str = "real child answer"
    session_id: str = ""
    cancelled: bool = False

    def set_session(self, session_id: str) -> str:
        self.session_id = session_id
        return session_id

    async def run(self, prompt: str, *, mode: str = "build") -> str:
        assert prompt == "inspect only"
        assert mode == "build"
        return self.answer

    def cancel(self) -> bool:
        self.cancelled = True
        return True


def _runtime(*, permission: PermissionSpec | None = None):
    definition = AgentDefinition(
        id="general", description="test child", mode=AgentMode.SUBAGENT,
        permission=permission or PermissionSpec(
            read=ToolPermission.from_raw("allow"),
            edit=ToolPermission.from_raw("deny"),
            bash=ToolPermission.from_raw("deny"),
        ),
        task_permission=TaskPermissionSpec(default_verdict=PermissionVerdict.DENY),
        workspace_scope=WorkspaceMode.READ_ONLY,
    )
    request = TaskRequest(
        parent_session_id="primary", agent_id="general", prompt="inspect only",
        trigger=TriggerKind.AUTOMATIC,
    )
    session = create_child_session(
        request,
        EffectiveTaskPolicy(
            permission=definition.permission,
            workspace=WorkspaceScope(mode=WorkspaceMode.READ_ONLY),
        ),
        definition=definition,
    )
    return create_child_runtime(definition, session)


def test_child_execution_bridge_runs_isolated_agent_and_returns_usage():
    fake = FakeAgent()
    runtime = _runtime()
    runtime.set_agent_factory(lambda _model: fake)

    result = asyncio.run(runtime.execute("inspect only"))

    assert result.status == ChildStatus.COMPLETED
    assert result.summary == "real child answer"
    assert fake.session_id == runtime.session_id
    assert result.usage.steps == 1


def test_child_execution_bridge_denies_tool_before_agent_execution():
    fake = FakeAgent()
    runtime = _runtime()
    runtime.set_agent_factory(lambda _model: fake)

    assert runtime.check_tool("bash", {"command": "echo unsafe"}) is False
    assert runtime.check_tool("read", {"filePath": "core/agent_v2.py"}) is True


def test_child_cancel_propagates_to_active_agent():
    fake = FakeAgent()
    runtime = _runtime()
    runtime.set_agent_factory(lambda _model: fake)
    runtime._active_agent = fake

    runtime.cancel_token.cancel()
    runtime.shutdown()

    assert fake.cancelled is True


def test_manager_cancel_reaches_active_agent():
    fake = FakeAgent()
    runtime = _runtime()
    runtime.set_agent_factory(lambda _model: fake)
    runtime._active_agent = fake

    runtime.cancel()

    assert runtime.cancel_token.is_cancelled is True
    assert fake.cancelled is True
