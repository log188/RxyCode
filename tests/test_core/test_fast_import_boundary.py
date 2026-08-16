"""Fast Desktop startup must not import the full Graph executor stack."""

import sys

from RxyCode.RxyCode1_1_0.execution import evidence


def test_execution_evidence_import_does_not_eagerly_import_executor():
    assert evidence is not None
    assert "RxyCode.RxyCode1_1_0.execution.executor" not in sys.modules
