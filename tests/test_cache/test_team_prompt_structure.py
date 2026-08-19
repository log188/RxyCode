"""F17 team prompt cache/role split."""

from __future__ import annotations

from RxyCode.RxyCode1_1_0.core.agents.team_prompt import (
    CACHE_BREAK_MARK,
    TEAM_CHARTER,
    assemble_member_prompt,
    render_member_prompt,
)


def test_cached_prefix_is_byte_stable_across_roles() -> None:
    tools = "read\ngrep\nls"
    task = "user goal + split"
    left_c, left_u = assemble_member_prompt(
        tools_block=tools,
        task_context=task,
        role_prompt="architect prompt",
        private_history="arch notes",
    )
    right_c, right_u = assemble_member_prompt(
        tools_block=tools,
        task_context=task,
        role_prompt="coder prompt",
        private_history="coder notes",
    )
    assert left_c == right_c
    assert TEAM_CHARTER in left_c
    assert left_u != right_u
    rendered = render_member_prompt(left_c, left_u)
    cached, uncached = rendered.split(CACHE_BREAK_MARK, 1)
    assert cached == left_c
    assert "architect prompt" in uncached
    assert "uuid" not in cached.lower()


def test_task_result_summary_is_compact() -> None:
    from RxyCode.RxyCode1_1_0.core.agents.team_prompt import compact_summary

    huge = "body " * 500
    short = compact_summary(huge, limit=400)
    assert len(short) <= 401
    assert huge not in short or len(huge) <= 400


def test_delegate_template_has_four_elements_and_workload() -> None:
    from RxyCode.RxyCode1_1_0.core.prompts.templates import DELEGATE_REQUEST_TEMPLATE

    text = DELEGATE_REQUEST_TEMPLATE.format(
        goal="g",
        expected_output="o",
        tools="read",
        context_refs="blackboard://plan",
    )
    assert "<GOAL>" in text
    assert "<OUTPUT>" in text
    assert "<TOOLS_AND_SOURCES>" in text
    assert "<BOUNDARY>" in text
    assert "3-10" in text


def test_cached_prefix_rejects_clock_and_ids() -> None:
    cached, _ = assemble_member_prompt(
        tools_block="tools",
        task_context="goal",
        role_prompt="role",
    )
    assert "2026-" not in cached
    assert "session" not in cached.lower()
