"""Bare and dotted spellings of every split top-level package are one object."""

from __future__ import annotations

import importlib
import sys

import pytest

CANONICAL_PREFIX = "RxyCode.RxyCode1_1_0"
CORE = f"{CANONICAL_PREFIX}.core"

# Frozen table from the §1.6 split-set script on fix2@fb92730
# (config / execution / memory / protocol / tools) plus core (RL4).
# Not a directory scan — that would swallow tests / scripts / docs.
PAIRS = (
    ("core", "agent_v2"),
    ("core", "safety.approval"),
    ("core", "session_runtime"),
    ("core", "session"),
    ("config", "settings"),
    ("execution", "executor"),
    ("memory", "manager"),
    ("protocol", "notifications"),
    ("tools", "registry"),
)


def _names(package: str, submodule: str) -> tuple[str, str]:
    suffix = f"{package}.{submodule}"
    return suffix, f"{CANONICAL_PREFIX}.{suffix}"


@pytest.mark.parametrize("order", ("flat_first", "dotted_first"))
@pytest.mark.parametrize("package,submodule", PAIRS, ids=[f"{p}.{s}" for p, s in PAIRS])
def test_bare_and_dotted_submodules_are_one_object(
    order: str, package: str, submodule: str
) -> None:
    import appserver  # noqa: F401 — registers the bare-package alias / finder

    flat_name, dotted_name = _names(package, submodule)
    first, second = (
        (flat_name, dotted_name) if order == "flat_first" else (dotted_name, flat_name)
    )
    importlib.import_module(first)
    importlib.import_module(second)

    flat = sys.modules[flat_name]
    dotted = sys.modules[dotted_name]
    assert flat is dotted

    parent = importlib.import_module(f"{CANONICAL_PREFIX}.{package}")
    attr = parent
    for part in submodule.split("."):
        attr = getattr(attr, part)
    assert attr is dotted


def test_approval_broker_singleton_is_shared_across_spellings() -> None:
    import appserver  # noqa: F401

    importlib.import_module("core.safety.approval")
    importlib.import_module(f"{CORE}.safety.approval")
    from core.safety.approval import get_approval_broker, set_approval_broker

    dotted = importlib.import_module(f"{CORE}.safety.approval")
    marker = object()
    set_approval_broker(marker)
    try:
        assert dotted.get_approval_broker() is marker
        assert get_approval_broker() is marker
    finally:
        set_approval_broker(None)
