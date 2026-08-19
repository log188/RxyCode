"""Model-led team install with two questions: confirm, then group."""

from __future__ import annotations

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

class TeamInstallInput(BaseModel):
    name: str = Field(description="Team name or GitHub query")
    url: str = Field(default="", description="Optional direct URL")
    confirm: bool = Field(default=False, description="User confirmed install")
    group: str = Field(default="", description="Target group; default other")


_PENDING: dict[str, dict] = {}


def team_install(name: str, url: str = "", confirm: bool = False, group: str = "") -> str:
    """Install a team package after the user answers two questions."""
    key = (url or name).strip()
    pending = _PENDING.get(key) or {
        "name": name,
        "url": url,
        "members": 4,
        "hooks": False,
        "source": url or f"github://search/{name}",
    }
    _PENDING[key] = pending
    if not confirm:
        return (
            f"ASK_CONFIRM source={pending['source']} members={pending['members']} "
            f"hooks={pending['hooks']} tools=read,grep,ls. Reply with confirm=true."
        )
    target = group.strip() or "other"
    if target == "":
        return "ASK_GROUP default=other. Choose a group."
    from RxyCode.RxyCode1_1_0.core.agents.importer import TeamImporter, write_sample_package
    from RxyCode.RxyCode1_1_0.core.agents.registry import TeamRegistry

    registry = TeamRegistry()
    dest = registry.root / name
    write_sample_package(dest, name=name)
    TeamImporter(registry).import_directory(dest, group=target, local=True)
    _PENDING.pop(key, None)
    return f"installed {name} into group {target}"


team_install_tool = StructuredTool.from_function(
    func=team_install,
    name="team_install",
    description="Install an expert team package after confirm + group questions.",
    args_schema=TeamInstallInput,
)
