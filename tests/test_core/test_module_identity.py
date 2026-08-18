"""RL4: bare ``core.X`` and dotted ``RxyCode.RxyCode1_1_0.core.X`` are one object."""

from __future__ import annotations

import importlib
import sys

import pytest

CANONICAL = "RxyCode.RxyCode1_1_0.core"
SUBMODULES = (
    "agent_v2",
    "safety.approval",
    "session_runtime",
)


def _pair(submodule: str) -> tuple[str, str]:
    return f"core.{submodule}", f"{CANONICAL}.{submodule}"


@pytest.mark.parametrize("order", ("flat_first", "dotted_first"))
@pytest.mark.parametrize("submodule", SUBMODULES)
def test_bare_and_dotted_core_submodules_are_one_object(order: str, submodule: str) -> None:
    import appserver  # noqa: F401 — registers the bare-core alias / finder

    flat_name, dotted_name = _pair(submodule)
    first, second = (
        (flat_name, dotted_name) if order == "flat_first" else (dotted_name, flat_name)
    )
    importlib.import_module(first)
    importlib.import_module(second)

    flat = sys.modules[flat_name]
    dotted = sys.modules[dotted_name]
    assert flat is dotted

    parent = importlib.import_module(CANONICAL)
    attr = parent
    for part in submodule.split("."):
        attr = getattr(attr, part)
    assert attr is dotted


def test_approval_broker_singleton_is_shared_across_spellings() -> None:
    import appserver  # noqa: F401

    importlib.import_module("core.safety.approval")
    importlib.import_module(f"{CANONICAL}.safety.approval")
    from core.safety.approval import get_approval_broker, set_approval_broker

    dotted = importlib.import_module(f"{CANONICAL}.safety.approval")
    marker = object()
    set_approval_broker(marker)
    try:
        assert dotted.get_approval_broker() is marker
        assert get_approval_broker() is marker
    finally:
        set_approval_broker(None)
