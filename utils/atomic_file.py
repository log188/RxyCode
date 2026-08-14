"""Small atomic file-write primitives used by mutating tools."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _normalize_script_line_endings(path: Path, content: str) -> str:
    """Use the native line ending required by Windows batch interpreters.

    ``cmd.exe`` treats LF-only ``.bat``/``.cmd`` files as malformed on the
    supported Windows runtime: command lines can lose their first character
    and the resulting failures trigger an unnecessary model recovery round.
    Normalize only batch scripts; all other file types retain the exact text
    supplied by the agent.
    """
    if path.suffix.lower() not in {".bat", ".cmd"}:
        return content
    return content.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")


def atomic_write_text(path: str | Path, content: str) -> None:
    """Durably replace ``path`` with UTF-8 text from the same directory."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = _normalize_script_line_endings(target, content)
    fd, temporary = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
