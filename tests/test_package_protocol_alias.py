"""Regression: bare ``import protocol`` must resolve after package import.

RxyCode ships as the ``RxyCode.RxyCode1_1_0`` package; ``protocol`` is a
top-level subpackage of the checkout. Several modules use the bare
``from protocol.subagents import ...`` form, which only works when the repo
root is on ``sys.path``.  ``RxyCode.RxyCode1_1_0/__init__.py`` registers a
``sys.modules["protocol"]`` alias so the installed/editable package works from
any working directory.

These tests run in a subprocess so the repo root is NOT on sys.path — exactly
the scenario where the alias is required.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_SUBPROCESS = r"""
import importlib
import os
import sys

# Simulate an installed-package layout: repo root is NOT on sys.path.
# Instead expose the checkout as RxyCode.RxyCode1_1_0 via its parent dir
# (the editable-style top-level namespace) and confirm that importing the
# package registers the bare ``protocol`` alias.
repo = os.environ["RXYCODE_REPO_ROOT"]
repo_parent = os.path.dirname(repo)
sys.path.insert(0, repo_parent)  # makes ``RxyCode`` importable (parent layout)
sys.path.insert(0, os.path.join(repo, "_package_root"))

import RxyCode  # noqa: F401
import RxyCode.RxyCode1_1_0  # noqa: F401  (triggers alias registration)

protocol = sys.modules.get("protocol")
if protocol is None:
    print("RESULT:FAIL no-alias")
    raise SystemExit(1)
paths = list(getattr(protocol, "__path__", []) or [])
if not paths or not str(paths[0]).replace("\\", "/").endswith("/protocol"):
    print("RESULT:FAIL bad-path %r" % (paths,))
    raise SystemExit(1)

mod = importlib.import_module("protocol.subagents")
for symbol in ("AgentDefinition", "TaskRequest", "TaskResult", "ChildStatus"):
    if not hasattr(mod, symbol):
        print("RESULT:FAIL missing %s" % symbol)
        raise SystemExit(1)

from RxyCode.RxyCode1_1_0.tools.subagent_task_tool import subagent_task_tool
if subagent_task_tool.name != "task":
    print("RESULT:FAIL task tool name")
    raise SystemExit(1)

print("RESULT:OK")
"""


def test_bare_protocol_alias_registered_without_repo_root_on_path() -> None:
    env = dict(os.environ)
    env["RXYCODE_REPO_ROOT"] = str(REPO_ROOT)
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path.home()),
        timeout=120,
    )
    assert "RESULT:OK" in proc.stdout, (
        f"bare protocol alias failed\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
