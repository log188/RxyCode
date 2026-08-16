"""Fast Desktop startup must not import the full Graph executor stack."""

import importlib
import sys


def test_execution_evidence_import_does_not_eagerly_import_executor():
    # Save current state — executor may have been imported by earlier tests.
    had_evidence = "RxyCode.RxyCode1_1_0.execution.evidence" in sys.modules

    # Force re-import of evidence in a clean state to test the boundary.
    if had_evidence:
        mod = sys.modules.pop("RxyCode.RxyCode1_1_0.execution.evidence")
    else:
        mod = None

    # Temporarily remove executor if it was pre-existing so we can detect
    # whether evidence re-import brings it in.
    saved_executor = sys.modules.pop("RxyCode.RxyCode1_1_0.execution.executor", None)
    try:
        from RxyCode.RxyCode1_1_0.execution import evidence  # noqa: F401
        assert "RxyCode.RxyCode1_1_0.execution.executor" not in sys.modules, (
            "importing evidence should not eagerly import executor"
        )
    finally:
        # Restore the saved executor module if it was there before.
        if saved_executor is not None:
            sys.modules["RxyCode.RxyCode1_1_0.execution.executor"] = saved_executor
        if mod is not None:
            sys.modules["RxyCode.RxyCode1_1_0.execution.evidence"] = mod
