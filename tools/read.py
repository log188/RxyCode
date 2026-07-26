from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ..core.session_runtime import resolve_session_path


class ReadInput(BaseModel):
    filePath: str = Field(description="Absolute or session-relative file path")
    offset: int = Field(default=1, description="Starting line number (1-indexed)")
    limit: int = Field(default=800, description="Max lines to read (default 800; use offset to page through larger files)")


def read_file(filePath: str, offset: int = 1, limit: int = 800) -> str:
    p = resolve_session_path(filePath)
    if not p.exists():
        return f"[error: path not found: {filePath}]"
    if p.is_dir():
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        lines = []
        for e in entries:
            suffix = "/" if e.is_dir() else ""
            lines.append(f"{e.name}{suffix}")
        return "\n".join(lines)
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        start = max(0, offset - 1)
        end = min(len(all_lines), start + limit)
        selected = all_lines[start:end]
        result = []
        for i, line in enumerate(selected, start=start + 1):
            result.append(f"{i}: {line.rstrip()}")
        return "\n".join(result)
    except Exception as e:
        return f"[error reading file: {e}]"


read_tool = StructuredTool.from_function(
    func=read_file,
    name="read",
    description=(
        "Read a file or list a directory. Relative paths use the session working directory. "
        "Returns content with line numbers. Reads at most `limit` lines (default 800); "
        "for larger files, page through with `offset` (e.g. offset=801 for the next chunk)."
    ),
    args_schema=ReadInput,
)
