import os
from pathlib import Path
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class SkillInput(BaseModel):
    name: str = Field(description="Name of the skill to load")


def _skill_dirs() -> list[Path]:
    configured = os.environ.get("RXYCODE_SKILLS_DIRS", "").strip()
    if configured:
        return [Path(item) for item in configured.split(os.pathsep) if item]
    return [
        Path(os.path.expanduser("~")) / ".rxycode" / "skills",
        Path(os.path.expanduser("~")) / ".claude" / "skills",
        Path(os.path.expanduser("~")) / ".codex" / "skills",
        Path(os.path.expanduser("~")) / ".mimocode" / "skills",
    ]


def load_skill(name: str) -> str:
    for base in _skill_dirs():
        if not base.exists():
            continue
        for d in base.rglob(name):
            if d.is_dir():
                skill_file = d / "SKILL.md"
                if skill_file.exists():
                    return skill_file.read_text(encoding="utf-8", errors="replace")
                for f in d.glob("*.md"):
                    return f.read_text(encoding="utf-8", errors="replace")
        for d in base.rglob("SKILL.md"):
            if name.lower() in d.parent.name.lower():
                return d.read_text(encoding="utf-8", errors="replace")

    return f"Skill '{name}' was not found in any skill directory."


skill_tool = StructuredTool(
    name="skill",
    description="Load a specialized skill by name. Reads skill instructions from skill directories.",
    func=load_skill,
    args_schema=SkillInput,
)
