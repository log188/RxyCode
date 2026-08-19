"""FXC3: frozen S1 vs dynamic turn snapshot (user lane, not second system)."""

from __future__ import annotations

import re
from datetime import datetime
from types import SimpleNamespace

from RxyCode.RxyCode1_1_0.core.prompts.registry import (
    build_user_message,
    get_system_s1,
    get_system_s2,
)
from tests.conftest import REPO_ROOT


def test_s1_stable_across_clock(monkeypatch):
    a = get_system_s1(tools=True, variant="default")
    monkeypatch.setattr(
        "RxyCode.RxyCode1_1_0.core.prompts.registry.datetime",
        SimpleNamespace(now=lambda: datetime(2099, 1, 1, 0, 0, 0)),
    )
    b = get_system_s1(tools=True, variant="default")
    assert a == b
    assert "2026" not in a
    assert "2099" not in b
    assert re.search(r"\d{4}-\d{2}-\d{2}", a) is None


def test_s1_same_variant_byte_identical():
    a = get_system_s1(tools=False, variant="default")
    b = get_system_s1(tools=False, variant="default")
    assert a == b
    assert a == get_system_s1(variant="default")


def test_research_not_second_system():
    src = (REPO_ROOT / "core" / "agent_v2.py").read_text(encoding="utf-8")
    assert "SystemMessage(content=research_contract)" not in src


def test_s2_carries_research_not_s1():
    s1 = get_system_s1(tools=False, variant="default")
    s2 = get_system_s2(research_contract="External research is mandatory")
    assert "External research is mandatory" in s2
    assert "External research is mandatory" not in s1
    assert "[cwd:" not in s1
    assert "[session_created:" not in s1


def test_timestamp_stays_in_user_not_s1():
    s1 = get_system_s1(tools=False, variant="default")
    user = build_user_message("", "hello")
    assert re.search(r"\d{4}-\d{2}-\d{2}", s1) is None
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", user)
