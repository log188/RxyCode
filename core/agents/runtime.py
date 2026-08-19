"""AgentRuntime：Phase D ChildRuntime 的专家角色适配器。

每个角色通过 Phase D 的 ChildSession/ChildRuntime 获得：
  - ToolRegistry   只含 spec.tools 声明的工具
  - cache namespace
  - circuit breaker key
  - memory namespace（memory_scope="private" 时）
  - LLM（按 spec.model 解析，走 Phase A 的 provider 层）

约束（§3.2）：
  DC2 —— runtime 之间不持有对方引用，只通过 Coordinator 通信
  DC3 —— 默认全隔离，共享必须显式声明

本卡不复制 D5：ChildRuntime / ChildSession 生命周期只走
``create_child_session`` + ``create_child_runtime``。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from protocol.subagents import (
    AgentDefinition,
    AgentMode,
    EffectiveTaskPolicy,
    TaskRequest,
    TaskResult,
    TriggerKind,
    WorkspaceMode,
)

from RxyCode.RxyCode1_1_0.core.agents.spec import AgentSpecError
from RxyCode.RxyCode1_1_0.core.subagents.runtime import ChildRuntime, create_child_runtime
from RxyCode.RxyCode1_1_0.core.subagents.sessions import create_child_session
from RxyCode.RxyCode1_1_0.protocol.agents import AgentSpec
from RxyCode.RxyCode1_1_0.recovery.circuit_breaker import get_breaker
from RxyCode.RxyCode1_1_0.tools.registry import ToolRegistry, default_registry

if TYPE_CHECKING:
    from RxyCode.RxyCode1_1_0.core.session import Session


def _definition_from_agent_spec(spec: AgentSpec) -> AgentDefinition:
    """Map F3 AgentSpec onto Phase D AgentDefinition. No second lifecycle."""
    parts = [spec.goal, spec.backstory, *spec.constraints]
    prompt = "\n".join(part for part in parts if part).strip() or spec.display_name
    readonly = spec.mechanical or spec.tools == []
    return AgentDefinition(
        id=spec.role,
        description=spec.goal or spec.display_name,
        mode=AgentMode.SUBAGENT,
        prompt=prompt,
        model=None if spec.mechanical else spec.model,
        workspace_scope=(
            WorkspaceMode.READ_ONLY if readonly else WorkspaceMode.LEASED_WRITE
        ),
        extra=dict(spec.extra),
        subagent_depth=0,
    )


def _no_llm(_model: str | None) -> Any:
    raise RuntimeError("mechanical role has no LLM")


class AgentRuntime:
    """Expert-role adapter over a Phase D ChildRuntime."""

    def __init__(self, spec: AgentSpec, *, session: Session) -> None:
        self._spec = spec
        self._session = session
        self._registry = self._build_scoped_registry(spec.tools)
        self._breaker = get_breaker(f"team:{session.session_id}:{spec.role}")
        # role="default" keeps the F2 single-agent cache key (namespace None).
        self._agent_namespace: str | None = None
        self.resolved_model = spec.model
        self._llm: Any | None = None
        if spec.memory_scope == "shared":
            self._memory_store = session._shared_agent_memory
        else:
            self._memory_store = None

        definition = _definition_from_agent_spec(spec)
        child_session = create_child_session(
            TaskRequest(
                parent_session_id=session.session_id,
                agent_id=spec.role,
                prompt="",
                trigger=TriggerKind.TEAM,
            ),
            EffectiveTaskPolicy(),
            definition=definition,
        )
        self._child = create_child_runtime(
            definition,
            child_session,
            workspace_root=session.workspace_root,
        )
        if spec.mechanical:
            self._child.set_agent_factory(_no_llm)

        self.spawn()
        session.agent_runtimes[spec.role] = self

    def spawn(self) -> "AgentRuntime":
        """Assign the team cache namespace. Solo role=default stays None (DC8)."""
        if self._spec.role == "default":
            self._agent_namespace = None
        else:
            self._agent_namespace = f"agent:{self._spec.role}"
        previous = self._child._agent_factory

        def factory(model: str | None) -> Any:
            if previous is not None:
                agent = previous(model)
            else:
                from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2

                agent = AgentV2(model_name=model)
            if self._agent_namespace is not None:
                try:
                    agent._agent_namespace = self._agent_namespace
                except Exception:
                    pass
            return agent

        self._child.set_agent_factory(factory)
        self.resolved_model = self._spec.model
        return self

    @property
    def spec(self) -> AgentSpec:
        return self._spec

    @property
    def role(self) -> str:
        return self._spec.role

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    @property
    def cache_namespace(self) -> str | None:
        return self._agent_namespace

    @property
    def breaker(self):
        return self._breaker

    @property
    def llm(self) -> Any | None:
        return self._llm

    @property
    def child(self) -> ChildRuntime:
        return self._child

    async def run(self, task: TaskRequest) -> TaskResult:
        """只通过 Phase D ChildRuntime 执行，不持有 Primary 的可变状态。"""
        if self._spec.mechanical:
            raise RuntimeError("mechanical role has no LLM")
        return await self._child.execute(task.prompt)

    def memory_set(self, key: str, value: Any) -> None:
        if self._memory_store is not None:
            self._memory_store[key] = value
            return
        self._child.namespace.memory_set(key, value)

    def memory_get(self, key: str) -> Any | None:
        if self._memory_store is not None:
            return self._memory_store.get(key)
        return self._child.namespace.memory_get(key)

    @staticmethod
    def _build_scoped_registry(tool_names: list[str] | None) -> ToolRegistry:
        """按角色声明构造独立注册表。

        None  → 复制默认注册表全部工具（等同单 Agent 行为）
        []    → 空注册表（纯推理角色）
        [...] → 只放声明的工具

        角色 adapter 可以提供工具声明转换，但最终 registry 必须由 Phase D
        的 PermissionPolicy/WorkspaceScope 再次裁剪。声明了不存在的工具名必须
        抛异常，不能静默忽略。
        """
        scoped = ToolRegistry()
        if tool_names is None:
            for tool in default_registry.get_all():
                scoped.register(tool, risk=default_registry.get_risk(tool.name))
            return scoped
        if not tool_names:
            return scoped
        known = set(default_registry.get_names())
        for name in tool_names:
            if name not in known:
                raise AgentSpecError(f"unknown tool {name!r} in AgentSpec.tools")
            tool = default_registry.get(name)
            if tool is None:
                raise AgentSpecError(f"unknown tool {name!r} in AgentSpec.tools")
            scoped.register(tool, risk=default_registry.get_risk(name))
        return scoped
