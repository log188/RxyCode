"""Execution layer: scheduler, executor, and tool orchestrator."""

from .scheduler import TaskScheduler
from .tool_orchestrator import ToolOrchestrator

__all__ = ["TaskScheduler", "Executor", "ToolOrchestrator"]


def __getattr__(name):
    """Load the Graph executor only for callers that explicitly request it.

    Importing ``execution.evidence`` is part of the ordinary fast Desktop
    worker path.  The old eager ``Executor`` import pulled LangChain's agent
    factory and its torch/transformers dependency tree into every worker,
    adding roughly ten seconds before a first prompt could start.
    """
    if name == "Executor":
        from .executor import Executor

        return Executor
    raise AttributeError(name)
