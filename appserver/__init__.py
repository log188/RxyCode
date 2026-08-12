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


def _register_bare_core_alias() -> None:
    """Make ``import core`` resolve to this checkout's canonical core package.

    A few modules (``appserver/*``, ``tools/*``) use the bare ``from core...``
    form.  Under a source checkout that works because the repo root is on
    ``sys.path``; under an installed/editable package the canonical name is
    ``RxyCode.RxyCode1_1_0.core`` and the bare name would load a second copy
    of the same files (splitting module singletons such as the approval
    broker).  Registering the alias keeps both spellings the same object.
    """
    if "core" in sys.modules:
        return
    try:
        import RxyCode.RxyCode1_1_0.core as _core_pkg
    except ImportError:
        return
    sys.modules["core"] = _core_pkg


_bind_top_level_checkout_to_canonical_package()
_register_bare_core_alias()

from .server import AppServer

__all__ = ["AppServer"]
