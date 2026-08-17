"""rxycode gui command tests (Phase 4 desktop quick entry).

The gui command must:
- resolve the desktop executable from: explicit --desktop-dir, then
  ~/.rxycode/desktop, then PATH (rxycode-desktop).
- fall back to launching frontend/desktop-app with npm run dev when no
  packaged desktop is found.
- never touch the CLI path (rxycode stays the CLI entry).
"""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from RxyCode.RxyCode1_1_0 import main


def test_resolve_desktop_exe_explicit_dir(tmp_path, monkeypatch):
    exe = tmp_path / "rxycode-desktop.exe"
    exe.write_text("", encoding="utf-8")
    exe.chmod(0o755)  # packaged builds are executable; os.access(X_OK) gates resolution
    resolved = main._resolve_desktop_executable(desktop_dir=str(tmp_path))
    assert resolved == str(exe)


def test_resolve_desktop_exe_default_dir(monkeypatch, tmp_path):
    home = tmp_path / "home"
    desktop = home / ".rxycode" / "desktop"
    desktop.mkdir(parents=True)
    exe = desktop / "rxycode-desktop.exe"
    exe.write_text("", encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    resolved = main._resolve_desktop_executable()
    assert resolved == str(exe)


def test_resolve_desktop_exe_missing_returns_none(monkeypatch, tmp_path):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    assert main._resolve_desktop_executable() is None


def test_resolve_desktop_exe_posix_name(monkeypatch, tmp_path):
    desktop = tmp_path / ".rxycode" / "desktop"
    desktop.mkdir(parents=True)
    exe = desktop / "rxycode-desktop"
    exe.write_text("", encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    resolved = main._resolve_desktop_executable()
    assert resolved == str(exe)


def test_gui_without_packaged_or_sources_points_to_release(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "_resolve_desktop_executable", lambda d=None: None)
    monkeypatch.setattr(main, "_frontend_dir", lambda: str(tmp_path))

    with pytest.raises(click.ClickException) as exc:
        main.gui.callback(desktop_dir=None)

    message = str(exc.value)
    assert "does not include the Electron app" in message
    assert f"releases/tag/v{main.__version__}" in message
    assert "RXYCODE_DESKTOP_DIR" in message


def test_gui_falls_back_to_dev_without_packaged_build(monkeypatch, tmp_path):
    """No packaged desktop -> dev fallback must spawn npm in desktop-app."""
    import subprocess

    spawned: list[list[str]] = []

    def _fake_popen(cmd, **kwargs):
        spawned.append(cmd)
        return type("P", (), {"wait": lambda self: 0, "terminate": lambda self: None})()

    monkeypatch.setattr(main, "_resolve_desktop_executable", lambda d=None: None)
    monkeypatch.setattr(main, "_npm_executable", lambda: "/fake/npm")
    monkeypatch.setattr(subprocess, "Popen", _fake_popen)

    # Invoke the underlying command callback (the click-wrapped object is a
    # Command instance; its .callback is the plain function).
    main.gui.callback(desktop_dir=str(tmp_path / "missing"))
    assert spawned and spawned[0][-2:] == ["run", "dev"]


@pytest.mark.parametrize("command", ["GUI", "Gui", "gUi"])
def test_gui_subcommand_is_case_insensitive(monkeypatch, command):
    """Desktop launch aliases must not alter option values or command behavior."""
    import subprocess

    spawned: list[list[str]] = []

    def _fake_popen(cmd, **kwargs):
        spawned.append(cmd)
        return type("P", (), {"wait": lambda self: 0, "terminate": lambda self: None})()

    monkeypatch.setattr(main, "_resolve_desktop_executable", lambda d=None: None)
    monkeypatch.setattr(main, "_npm_executable", lambda: "/fake/npm")
    monkeypatch.setattr(subprocess, "Popen", _fake_popen)

    result = CliRunner().invoke(main.cli, [command])

    assert result.exit_code == 0, result.output
    assert spawned and spawned[0][-2:] == ["run", "dev"]
