"""RL7: _kill_process_tree must verify death and fall back visibly."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from RxyCode.RxyCode1_1_0.core.bridge import acp as acp_mod


class _FakeProc:
    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid
        self.returncode: int | None = None
        self.killed = False

    def kill(self) -> None:
        self.killed = True
        self.returncode = 1


def test_taskkill_success_does_not_need_fallback(monkeypatch):
    proc = _FakeProc()

    def fake_run(*_args, **_kwargs):
        proc.returncode = 0
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(acp_mod.os, "name", "nt")
    monkeypatch.setattr("subprocess.run", fake_run)
    acp_mod._kill_process_tree(proc)
    assert proc.returncode == 0
    assert proc.killed is False


def test_taskkill_failure_falls_back_to_kill(monkeypatch):
    proc = _FakeProc()

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(acp_mod.os, "name", "nt")
    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr(acp_mod, "_os_pid_alive", lambda _pid: False)
    acp_mod._kill_process_tree(proc)
    assert proc.killed is True


def test_both_fail_logs_and_raises(monkeypatch, caplog):
    proc = _FakeProc()

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=1)

    def fake_kill() -> None:
        return None

    monkeypatch.setattr(acp_mod.os, "name", "nt")
    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr(proc, "kill", fake_kill)
    monkeypatch.setattr(acp_mod, "_os_pid_alive", lambda _pid: True)
    with caplog.at_level("ERROR", logger=acp_mod.__name__):
        with pytest.raises(RuntimeError, match="failed to kill process tree"):
            acp_mod._kill_process_tree(proc)
    assert any("still alive" in rec.getMessage() for rec in caplog.records)
