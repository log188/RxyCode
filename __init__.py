"""RxyCode 1.2.9 - LangGraph-based agent."""

import sys as _sys
import types as _types
from pathlib import Path as _Path

__version__ = "1.2.9"

__all__ = ["__version__"]


def _register_bare_protocol_alias() -> None:
    """Make ``import protocol`` resolve to this package's protocol subpackage.

    Several modules (``core/subagents/*``, ``tools/subagent_task_tool.py``,
    ``appserver/*``) use the bare ``from protocol.subagents import ...`` form.
    Under a source checkout that works because the repo root is on ``sys.path``;
    under an installed/editable package the protocol package lives at
    ``RxyCode.RxyCode1_1_0.protocol`` and the bare name is missing.  Registering
    the alias here means ``rxycode`` works from any working directory.
    """
    if "protocol" in _sys.modules:
        return
    protocol_dir = _Path(__file__).resolve().parent / "protocol"
    init_file = protocol_dir / "__init__.py"
    module = _types.ModuleType("protocol")
    module.__path__ = [str(protocol_dir)]
    module.__package__ = "protocol"
    module.__file__ = str(init_file)
    _sys.modules["protocol"] = module
    # Execute the real protocol/__init__.py against the alias so exports such
    # as PROTOCOL_VERSION are populated, not just the subpackage path.
    if init_file.exists():
        try:
            import io as _io

            source = init_file.read_text(encoding="utf-8")
            code = compile(source, str(init_file), "exec")
            exec(code, module.__dict__)  # noqa: S102
        except Exception:
            # If protocol/__init__.py cannot execute (e.g. partial checkout),
            # keep the path alias so subpackage imports still resolve.
            pass


_register_bare_protocol_alias()

