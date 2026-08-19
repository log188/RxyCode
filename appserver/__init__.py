"""Stdio JSON-RPC transport for the headless RxyCode core (Phase 2 P4)."""

import importlib
import importlib.util
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


# Frozen list, not a directory scan (that would swallow tests/scripts/docs).
# Measured 2026-08-19 on fix2@fb92730 by the PHASE-FIX2 §1.6 script:
#   import appserver + core.session/agent_v2, tools.registry,
#   memory.manager, execution.executor, then collect top-level names
#   present under both spellings as distinct objects.
# Result: config, execution, memory, protocol, tools.
# `core` is included because RL4 already unified it; omitting it would
# re-split it.
_UNIFIED_TOP_LEVEL_PACKAGES = frozenset(
    {"config", "core", "execution", "memory", "protocol", "tools"}
)
_CANONICAL_PREFIX = "RxyCode.RxyCode1_1_0."


class _BarePackageAliasLoader:
    """Load a bare name by returning the already-executed canonical module."""

    def __init__(self, canonical_name: str) -> None:
        self.canonical_name = canonical_name

    def create_module(self, spec):  # noqa: ANN001 - importlib loader protocol
        return importlib.import_module(self.canonical_name)

    def exec_module(self, module) -> None:  # noqa: ANN001, ARG002
        return None


class _BarePackageRedirectFinder:
    """sys.meta_path hook: bare ``pkg.X`` is ``RxyCode.RxyCode1_1_0.pkg.X``.

    Aliasing only a package object is not enough.  The first bare
    ``import pkg.X`` would still create a second module and rebind the
    attribute on the shared parent, splitting singletons and isinstance.
    Redirecting the spec makes the import system keep one module object.
    """

    def find_spec(self, fullname, path, target=None):  # noqa: ANN001, ARG002
        root = fullname.partition(".")[0]
        if root not in _UNIFIED_TOP_LEVEL_PACKAGES:
            return None
        canonical = _CANONICAL_PREFIX + fullname
        existing = sys.modules.get(canonical)
        if existing is not None:
            is_package = hasattr(existing, "__path__")
            origin = getattr(existing, "__file__", None)
        else:
            try:
                can_spec = importlib.util.find_spec(canonical)
            except (ImportError, ModuleNotFoundError, ValueError):
                return None
            if can_spec is None:
                return None
            is_package = can_spec.submodule_search_locations is not None
            origin = can_spec.origin
        return importlib.util.spec_from_loader(
            fullname,
            _BarePackageAliasLoader(canonical),
            origin=origin,
            is_package=is_package,
        )


def _register_bare_package_aliases() -> None:
    """Make bare ``import pkg`` resolve to this checkout's canonical package.

    A few modules (``appserver/*``, ``tools/*``) use the bare ``from core...``
    (and the same form for protocol / config / …) spelling.  Under a source
    checkout that works because the repo root is on ``sys.path``; under an
    installed/editable package the canonical name is
    ``RxyCode.RxyCode1_1_0.pkg`` and the bare name would load a second copy
    of the same files (splitting module singletons and ``isinstance``).
    The package alias plus a meta_path finder keep both spellings — including
    every submodule — the same object, for every package in
    ``_UNIFIED_TOP_LEVEL_PACKAGES``.
    """
    if not any(type(finder) is _BarePackageRedirectFinder for finder in sys.meta_path):
        sys.meta_path.insert(0, _BarePackageRedirectFinder())
    # The checkout root ``__init__.py`` pre-creates a distinct ``protocol``
    # module (and may have loaded ``protocol.version``) before this finder
    # is installed.  That file is outside this card's whitelist; rebind any
    # already-imported listed names so the package objects themselves are
    # not left split.
    for name in list(sys.modules):
        root = name.partition(".")[0]
        if root not in _UNIFIED_TOP_LEVEL_PACKAGES:
            continue
        try:
            canonical = importlib.import_module(_CANONICAL_PREFIX + name)
        except ImportError:
            continue
        sys.modules[name] = canonical
    if "core" in sys.modules:
        return
    try:
        sys.modules["core"] = importlib.import_module(_CANONICAL_PREFIX + "core")
    except ImportError:
        return


_bind_top_level_checkout_to_canonical_package()
_register_bare_package_aliases()

from .server import AppServer

__all__ = ["AppServer"]
