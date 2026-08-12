"""Stdio JSON-RPC transport for the headless RxyCode core (Phase 2 P4)."""

import sys
import types
from pathlib import Path


def _bind_top_level_checkout_to_canonical_package() -> None:
    """Keep absolute RxyCode imports inside the checkout that launched us.

    Desktop development starts ``python -m appserver``.  This makes
    ``appserver`` a top-level module, while core/tool modules still use the
    canonical ``RxyCode.RxyCode1_1_0`` import path.  A sibling checkout on
    ``sys.path`` could otherwise satisfy that name and mix incompatible code
    versions in one worker process.
    """
    if __name__ != "appserver":
        return
    root = Path(__file__).resolve().parent.parent
    canonical_name = "RxyCode.RxyCode1_1_0"
    existing = sys.modules.get(canonical_name)
    if existing is not None and Path(getattr(existing, "__file__", root)).resolve().parent == root:
        return

    parent = sys.modules.get("RxyCode")
    if parent is None:
        parent = types.ModuleType("RxyCode")
        parent.__path__ = [str(root.parent)]
        sys.modules["RxyCode"] = parent
    package = types.ModuleType(canonical_name)
    package.__file__ = str(root / "__init__.py")
    package.__path__ = [str(root)]
    sys.modules[canonical_name] = package
    init_file = root / "__init__.py"
    if init_file.exists():
        source = init_file.read_text(encoding="utf-8-sig")
        exec(compile(source, str(init_file), "exec"), package.__dict__)  # noqa: S102
    parent.RxyCode1_1_0 = package


_bind_top_level_checkout_to_canonical_package()

from .server import AppServer

__all__ = ["AppServer"]
