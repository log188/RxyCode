"""Phase C C5 contract tests: uvloop event-loop selection with fallback.

RXYCODE_UVLOOP switch (category ③ performance, default 1):
- ``1`` (default): on non-Windows platforms try to install uvloop's event
  loop policy; a missing uvloop falls back to the default asyncio loop.
- ``0``: never touch uvloop; the default asyncio loop is used.
- Windows never imports uvloop (official support is Unix-only).

Both entry points (``appserver.__main__`` and ``appserver.agent_worker``)
install the same ``_configure_event_loop`` helper before ``asyncio.run``.
"""

from __future__ import annotations

import asyncio
import builtins
import importlib
import sys

import pytest

_ENTRY_MODULES = ["appserver.__main__", "appserver.agent_worker"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("RXYCODE_UVLOOP", raising=False)


def _import_spy(monkeypatch, module_name: str) -> list[str]:
    """Intercept imports of *module_name* and report the calls."""
    calls: list[str] = []
    real_import = builtins.__import__

    def spy(name, *args, **kwargs):
        if name == module_name or name.startswith(module_name + "."):
            calls.append(name)
            raise ImportError(f"{module_name} unavailable (spy)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", spy)
    return calls


@pytest.mark.parametrize("module_name", _ENTRY_MODULES)
def test_win32_never_imports_uvloop(module_name, monkeypatch):
    mod = importlib.import_module(module_name)
    monkeypatch.setattr(sys, "platform", "win32")
    calls = _import_spy(monkeypatch, "uvloop")
    assert mod._configure_event_loop() is None
    assert calls == [], "uvloop must not be imported on win32"


@pytest.mark.parametrize("module_name", _ENTRY_MODULES)
def test_switch_zero_keeps_default_loop_even_on_posix(module_name, monkeypatch):
    mod = importlib.import_module(module_name)
    monkeypatch.setenv("RXYCODE_UVLOOP", "0")
    monkeypatch.setattr(sys, "platform", "linux")
    calls = _import_spy(monkeypatch, "uvloop")
    policy_spy = _recording(monkeypatch)
    assert mod._configure_event_loop() is None
    assert calls == [], "switch 0 must not import uvloop"
    assert policy_spy.calls == [], "switch 0 must not install a policy"


@pytest.mark.parametrize("module_name", _ENTRY_MODULES)
def test_posix_import_error_falls_back_to_default_loop(module_name, monkeypatch):
    mod = importlib.import_module(module_name)
    monkeypatch.setattr(sys, "platform", "linux")
    calls = _import_spy(monkeypatch, "uvloop")
    policy_spy = _recording(monkeypatch)
    assert mod._configure_event_loop() is None
    assert calls == ["uvloop"], "uvloop import must be attempted on posix"
    assert policy_spy.calls == [], "ImportError must fall back silently"


@pytest.mark.parametrize("module_name", _ENTRY_MODULES)
def test_posix_installs_uvloop_policy_when_available(module_name, monkeypatch):
    mod = importlib.import_module(module_name)
    monkeypatch.setattr(sys, "platform", "linux")

    class _FakeEventLoopPolicy:
        pass

    fake_uvloop = type(
        "uvloop", (), {"EventLoopPolicy": _FakeEventLoopPolicy}
    )()
    monkeypatch.setitem(sys.modules, "uvloop", fake_uvloop)
    policy_spy = _recording(monkeypatch)
    assert mod._configure_event_loop() is None
    assert len(policy_spy.calls) == 1
    assert isinstance(policy_spy.calls[0], _FakeEventLoopPolicy), (
        "an EventLoopPolicy instance must be installed"
    )


@pytest.mark.parametrize("module_name", _ENTRY_MODULES)
def test_default_switch_is_one(module_name, monkeypatch):
    mod = importlib.import_module(module_name)
    monkeypatch.setattr(sys, "platform", "linux")
    assert mod._configure_event_loop() is None  # default env = enabled


def test_default_asyncio_loop_still_works_on_win32(monkeypatch):
    """The default loop remains usable on win32 (the host platform)."""
    monkeypatch.setattr(sys, "platform", "win32")

    async def probe() -> str:
        return "loop-ok"

    assert asyncio.run(probe()) == "loop-ok"


class _Recording:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def __call__(self, policy) -> None:
        self.calls.append(policy)


def _recording(monkeypatch) -> _Recording:
    rec = _Recording()
    monkeypatch.setattr(asyncio, "set_event_loop_policy", rec)
    return rec
