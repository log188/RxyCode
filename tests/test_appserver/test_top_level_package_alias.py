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
