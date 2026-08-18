"""RxyCode 1.2.10 - LangGraph-based agent."""

from __future__ import annotations

import builtins as _builtins
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys as _sys
import types as _types

__version__ = "1.2.10"

__all__ = ["__version__", "unify_bare_package_aliases"]

_CANONICAL_PREFIX = "RxyCode.RxyCode1_1_0"
_BARE_PACKAGES = frozenset(
    {
        "appserver",
        "cache",
        "config",
        "core",
        "evals",
        "execution",
        "history",
        "log",
        "lsp",
        "mcp",
        "memory",
        "planning",
        "protocol",
        "rag",
        "recovery",
        "scheduler",
        "synthesis",
        "tools",
        "utils",
        "validation",
    }
)
_BARE_MODULES = frozenset({"api_server"})


def _is_bare_name(name: str) -> bool:
    if name in _BARE_MODULES:
        return True
    return name.split(".", 1)[0] in _BARE_PACKAGES


def unify_bare_package_aliases() -> None:
    """Point bare names at already-imported versioned modules.

    ``from core import providers`` uses the ``core.providers`` attribute when
    ``sys.modules["core"]`` is the versioned package, but
    ``from core.providers.anthropic import …`` looks up the bare key
    ``core.providers``.  Those must be the same object so ``isinstance``,
    monkeypatches, and process singletons apply.

    ``appserver`` is only filled when missing: ``python -m appserver`` and
    tests that patch ``appserver.server`` need the top-level package loader.
    """
    prefix = f"{_CANONICAL_PREFIX}."
    items = [
        (key, module)
        for key, module in _sys.modules.items()
        if key.startswith(prefix) and _is_bare_name(key[len(prefix) :])
    ]
    items.sort(key=lambda item: item[0].count("."))
    for key, module in items:
        short = key[len(prefix) :]
        parent_name, _, child = short.rpartition(".")
        parent = _sys.modules.get(parent_name)
        if short == "appserver" or short.startswith("appserver."):
            _sys.modules.setdefault(short, module)
            if parent is not None and child and not hasattr(parent, child):
                setattr(parent, child, module)
            continue
        _sys.modules[short] = module
        if parent is not None and child:
            setattr(parent, child, module)


class _ReuseLoader(importlib.abc.Loader):
    """Reuse a canonical module object for a bare import name."""

    def __init__(self, module: _types.ModuleType) -> None:
        self._module = module

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> _types.ModuleType:
        return self._module

    def exec_module(self, module: _types.ModuleType) -> None:
        return

    def get_code(self, fullname: str):
        spec = getattr(self._module, "__spec__", None)
        loader = getattr(spec, "loader", None) if spec is not None else None
        get_code = getattr(loader, "get_code", None)
        if get_code is None:
            return None
        return get_code(getattr(self._module, "__name__", fullname))


class _BareChildAliasFinder(importlib.abc.MetaPathFinder):
    """When ``core`` already *is* the versioned package, load ``core.foo`` from it.

    Does not intercept ``appserver`` or ``__main__`` so ``python -m appserver``
    and ``sys.modules['core.agent_v2'] = Fake`` keep working.
    """

    _mark = "_rxycode_bare_child_alias"

    def find_spec(self, fullname, path, target=None):  # noqa: ANN001
        if fullname.startswith("RxyCode") or not _is_bare_name(fullname):
            return None
        if fullname == "appserver" or fullname.startswith("appserver."):
            return None
        if fullname.rsplit(".", 1)[-1] == "__main__":
            return None
        canonical_name = f"{_CANONICAL_PREFIX}.{fullname}"
        parent_name, sep, _child = fullname.rpartition(".")
        if sep:
            parent = _sys.modules.get(parent_name)
            parent_mod_name = getattr(parent, "__name__", "") or ""
            if parent is None or not (
                parent_mod_name == _CANONICAL_PREFIX
                or parent_mod_name.startswith(f"{_CANONICAL_PREFIX}.")
            ):
                return None
        elif canonical_name not in _sys.modules:
            return None
        try:
            module = importlib.import_module(canonical_name)
        except ImportError:
            return None
        spec = importlib.util.spec_from_loader(
            fullname,
            _ReuseLoader(module),
            origin=getattr(module, "__file__", None),
            is_package=hasattr(module, "__path__"),
        )
        if spec is not None and hasattr(module, "__path__"):
            spec.submodule_search_locations = list(module.__path__)
        return spec


def _install_canonical_import_mirror() -> None:
    if not any(
        getattr(finder, "_mark", None) == _BareChildAliasFinder._mark
        for finder in _sys.meta_path
    ):
        _sys.meta_path.insert(0, _BareChildAliasFinder())
    current = _builtins.__import__
    if getattr(current, "_rxycode_bare_alias_mirror", False):
        return

    def _import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        module = current(name, globals, locals, fromlist, level)
        imported = name if isinstance(name, str) else ""
        mod_name = getattr(module, "__name__", "") or ""
        if (
            mod_name == _CANONICAL_PREFIX
            or mod_name.startswith(f"{_CANONICAL_PREFIX}.")
            or imported == _CANONICAL_PREFIX
            or imported.startswith(f"{_CANONICAL_PREFIX}.")
        ):
            unify_bare_package_aliases()
        return module

    _import._rxycode_bare_alias_mirror = True  # type: ignore[attr-defined]
    _builtins.__import__ = _import


def _register_bare_protocol_alias() -> None:
    """Make ``import protocol`` resolve to this package's protocol subpackage.

    Several modules (``core/subagents/*``, ``tools/subagent_task_tool.py``,
    ``appserver/*``) use the bare ``from protocol.subagents import ...`` form.
    Under a source checkout that works because the repo root is on ``sys.path``;
    under an installed/editable package the protocol package lives at
    ``RxyCode.RxyCode1_1_0.protocol`` and the bare name is missing.  Registering
    the alias here means ``rxycode`` works from any working directory.
    """
    _install_canonical_import_mirror()
    try:
        protocol = importlib.import_module(f"{_CANONICAL_PREFIX}.protocol")
    except ImportError:
        unify_bare_package_aliases()
        return
    _sys.modules["protocol"] = protocol
    unify_bare_package_aliases()


_register_bare_protocol_alias()
