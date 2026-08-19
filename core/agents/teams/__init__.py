"""Builtin TeamSpec loaders."""

from __future__ import annotations

from pathlib import Path

import yaml

from RxyCode.RxyCode1_1_0.core.agents.spec import validate_team
from RxyCode.RxyCode1_1_0.protocol.agents import AgentSpec, SopStage, TeamSpec

_DIR = Path(__file__).resolve().parent


def load_builtin_team(name: str = "software_dev") -> TeamSpec:
    path = _DIR / f"{name}.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    members = [AgentSpec(**row) for row in raw["members"]]
    stages = [SopStage(**row) for row in raw["stages"]]
    team = TeamSpec(
        name=raw["name"],
        display_name=raw.get("display_name", raw["name"]),
        description=raw.get("description", ""),
        members=members,
        stages=stages,
        entry_stage=raw["entry_stage"],
        total_token_budget=int(raw.get("total_token_budget", 500_000)),
        total_timeout_s=float(raw.get("total_timeout_s", 1800)),
        max_delegations=int(raw.get("max_delegations", 20)),
    )
    validate_team(team)
    return team
