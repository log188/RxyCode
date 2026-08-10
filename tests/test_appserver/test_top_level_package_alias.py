"""Top-level appserver startup must not import a sibling RxyCode checkout."""

import subprocess
import sys
from pathlib import Path


def test_top_level_appserver_binds_canonical_imports_to_its_own_checkout():
    root = Path(__file__).resolve().parents[2]
    probe = (
        "import appserver, inspect, core.agent_v2 as agent; "
        "print(inspect.getfile(agent.register_builtin_tools)); "
        "print(inspect.signature(agent.register_builtin_tools))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    lines = completed.stdout.splitlines()
    assert Path(lines[0]).resolve().is_relative_to(root)
    assert "subagents_enabled" in lines[1]


def test_top_level_worker_uses_the_same_approval_broker_module_as_agent_core():
    root = Path(__file__).resolve().parents[2]
    probe = (
        "import appserver; "
        "from appserver.agent_worker import set_approval_broker as worker_setter; "
        "from RxyCode.RxyCode1_1_0.core.safety.approval import set_approval_broker as core_setter; "
        "print(worker_setter is core_setter)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "True"
