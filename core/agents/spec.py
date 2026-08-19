"""Static validation for AgentSpec / TeamSpec.

Catch loops and unknown roles at config time, not after tokens are spent.
"""

from __future__ import annotations

from RxyCode.RxyCode1_1_0.protocol.agents import TeamSpec

#: Hard cap on Coordinator -> member delegation depth (DC6).
#: This is **not** Phase D ``subagent_depth`` (0/1/2 on ChildSession).
#: The two counters are independent: D counts isolated child sessions,
#: F counts expert-team stage hops. See PHASE-F §3.2 DC6.
MAX_DELEGATE_DEPTH = 3

_ALLOWED_EXTRA_PREFIXES = ("pair.", "vision.", "persona.", "ecosystem.")


class AgentSpecError(ValueError):
    """Invalid AgentSpec / TeamSpec configuration."""


def validate_team(team: TeamSpec) -> None:
    """静态校验一支专家团。

    这些检查存在的意义是在配置时拦住错误，而不是等线上跑炸。
    """
    roles = {m.role for m in team.members}
    if len(roles) != len(team.members):
        raise AgentSpecError("duplicate role in team members")

    stage_names = {s.name for s in team.stages}
    if len(stage_names) != len(team.stages):
        raise AgentSpecError("duplicate stage name")

    if team.entry_stage not in stage_names:
        raise AgentSpecError(f"entry_stage {team.entry_stage!r} is not a stage")

    for stage in team.stages:
        if stage.role not in roles:
            raise AgentSpecError(
                f"stage {stage.name!r} references unknown role {stage.role!r}"
            )
        for nxt in (stage.next_on_success, stage.next_on_failure):
            if nxt is not None and nxt not in stage_names:
                raise AgentSpecError(
                    f"stage {stage.name!r} points at unknown stage {nxt!r}"
                )

    for member in team.members:
        if member.role in member.may_consult:
            raise AgentSpecError(f"role {member.role!r} may not consult itself")
        for target in member.may_consult:
            if target not in roles:
                raise AgentSpecError(
                    f"role {member.role!r} may_consult unknown role {target!r}"
                )
        _check_extra_namespaces(member.extra, where=f"member {member.role!r}")

    _check_extra_namespaces(team.extra, where="team")
    _check_stage_graph_terminates(team)
    _check_consult_graph_acyclic(team)


def _check_extra_namespaces(extra: dict[str, object], *, where: str) -> None:
    """Namespaced extra keys must use pair.* / vision.* / persona.* / ecosystem.*."""
    for key in extra:
        if "." not in key:
            continue
        if not any(key.startswith(prefix) for prefix in _ALLOWED_EXTRA_PREFIXES):
            raise AgentSpecError(
                f"{where} extra key {key!r} uses an unknown namespace "
                f"(allowed prefixes: {', '.join(_ALLOWED_EXTRA_PREFIXES)})"
            )


def _check_stage_graph_terminates(team: TeamSpec) -> None:
    """确认 SOP 图存在可达的终点。

    全是环、没有 next=None 的出口，会让团队永远跑下去（预算会兜住，但那是
    最后一道防线，不该靠它）。
    """
    by_name = {stage.name: stage for stage in team.stages}
    seen: set[str] = set()
    stack = [team.entry_stage]
    has_exit = False
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        stage = by_name[name]
        for nxt in (stage.next_on_success, stage.next_on_failure):
            if nxt is None:
                has_exit = True
            elif nxt not in seen:
                stack.append(nxt)
    if not has_exit:
        raise AgentSpecError("SOP graph has no reachable exit")


def _check_consult_graph_acyclic(team: TeamSpec) -> None:
    """确认咨询图无环。

    A 可咨询 B、B 可咨询 A 会导致互相甩锅的无限往返。DFS 三色找环。
    """
    graph = {member.role: list(member.may_consult) for member in team.members}
    white, gray, black = 0, 1, 2
    color = {role: white for role in graph}

    def dfs(node: str) -> None:
        color[node] = gray
        for nxt in graph.get(node, ()):
            state = color.get(nxt)
            if state is None:
                continue
            if state == gray:
                raise AgentSpecError("consult graph contains a cycle")
            if state == white:
                dfs(nxt)
        color[node] = black

    for role in graph:
        if color[role] == white:
            dfs(role)
