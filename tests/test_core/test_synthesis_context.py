from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2


def test_final_synthesis_uses_compact_tool_free_context():
    agent = AgentV2.__new__(AgentV2)
    messages = [
        SystemMessage(content="system contract"),
        HumanMessage(content="Build the requested artifact."),
        AIMessage(content="I created files and ran checks.", tool_calls=[
            {"name": "write", "args": {}, "id": "call-1", "type": "tool_call"}
        ]),
        ToolMessage(content="[wrote README.md]", tool_call_id="call-1"),
        HumanMessage(content="Finalize this task now. Do not call tools."),
    ]

    compact = agent._build_synthesis_messages(messages)

    assert len(compact) == 2
    assert isinstance(compact[0], SystemMessage)
    assert isinstance(compact[1], HumanMessage)
    assert "Build the requested artifact." in compact[1].content
    assert "[wrote README.md]" in compact[1].content
    assert not any(getattr(message, "tool_calls", None) for message in compact)
