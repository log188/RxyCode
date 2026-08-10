"""Regression coverage for the appserver's per-prompt TUI bridge."""

from RxyCode.RxyCode1_1_0.utils import tui as canonical_tui

from appserver.runtime import (
    bind_prompt_context,
    install_tui_context_hook,
    reset_prompt_context,
)


def test_canonical_agent_tui_module_reads_the_bound_protocol_tui():
    """AgentV2 imports the canonical package path, not top-level ``utils``.

    The appserver must therefore install its context-aware ``get_tui`` hook on
    that exact module object, otherwise tool/progress events never reach the
    client and an active prompt is incorrectly declared stalled.
    """
    sentinel = object()
    install_tui_context_hook()
    tokens = bind_prompt_context("session-tui-bridge", sentinel)
    try:
        assert canonical_tui.get_tui() is sentinel
    finally:
        reset_prompt_context(tokens)
