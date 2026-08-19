"""F18b team/* RPC. Thin adapter over TeamRegistry + team_install."""

from __future__ import annotations

from typing import Any

from RxyCode.RxyCode1_1_0.core.agents.registry import (
    BUILTIN_GROUPS,
    TeamRegistry,
    TeamRegistryError,
)
from RxyCode.RxyCode1_1_0.tools.team_install_tool import team_install

_ACTIVE: dict[str, str] = {}


def _l1_summary(team) -> str:
    stages = [stage.name for stage in team.stages]
    chain = " → ".join(stages) if stages else "-"
    return f"{len(team.members)} 位角色 · {len(team.stages)} 阶段 · {chain}"


def team_list() -> dict[str, Any]:
    registry = TeamRegistry()
    items = []
    for record in registry.records.values():
        items.append(
            {
                "id": record.team.name,
                "display_name": record.team.display_name,
                "summary": _l1_summary(record.team),
            }
        )
    return {"teams": items}


def team_groups() -> dict[str, Any]:
    registry = TeamRegistry()
    groups = []
    for name, members in registry.groups.items():
        groups.append(
            {
                "id": name,
                "members": list(members),
                "builtin": name in BUILTIN_GROUPS,
            }
        )
    return {"groups": groups}


def team_group_rename(params: dict[str, Any]) -> dict[str, Any]:
    registry = TeamRegistry()
    try:
        registry.rename_group(str(params.get("old") or ""), str(params.get("new") or ""))
    except TeamRegistryError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def team_install_rpc(params: dict[str, Any]) -> dict[str, Any]:
    message = team_install(
        name=str(params.get("name") or ""),
        url=str(params.get("url") or ""),
        confirm=bool(params.get("confirm")),
        group=str(params.get("group") or ""),
    )
    return {"message": message}


def team_set_active(params: dict[str, Any]) -> dict[str, Any]:
    session_id = str(params.get("session_id") or "")
    team_id = str(params.get("team_id") or "")
    registry = TeamRegistry()
    if team_id not in registry.records:
        return {"ok": False, "error": f"unknown team {team_id}"}
    previous = _ACTIVE.get(session_id)
    _ACTIVE[session_id] = team_id
    return {"ok": True, "active": team_id, "changed": previous != team_id}
