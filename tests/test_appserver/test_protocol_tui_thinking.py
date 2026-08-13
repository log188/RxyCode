"""ProtocolTui thinking expand emits reasoning to the client."""

from __future__ import annotations

from appserver.tui import ProtocolTui
from protocol.notifications import ProgressUpdate, ReasoningSnapshot


def test_write_reasoning_silent_when_collapsed() -> None:
    emitted: list[object] = []
    tui = ProtocolTui("s1", emitted.append)
    tui.set_thinking_expanded(False)
    tui.write_reasoning("hidden thought")
    # Body stays collapsed, but the first reasoning chunk must still produce a
    # liveness event so the 120s watchdog does not treat thinking as a stall.
    assert len(emitted) == 1
    assert isinstance(emitted[0], ProgressUpdate)
    assert "思考" in emitted[0].text
    tui.write_reasoning(" more")
    assert len(emitted) == 1


def test_write_reasoning_emits_when_expanded() -> None:
    emitted: list[object] = []
    tui = ProtocolTui("s1", emitted.append)
    tui.set_thinking_expanded(True)
    tui.write_reasoning("visible thought")
    assert len(emitted) == 1
    assert isinstance(emitted[0], ReasoningSnapshot)
    assert emitted[0].text == "visible thought"
    assert emitted[0].snapshot is False


def test_expand_mid_run_pushes_accumulated_snapshot() -> None:
    emitted: list[object] = []
    tui = ProtocolTui("s1", emitted.append)
    tui.set_thinking_expanded(False)
    tui.write_reasoning("part1")
    tui.write_reasoning(" part2")
    assert all(not isinstance(item, ReasoningSnapshot) for item in emitted)

    tui.set_thinking_expanded(True)
    snapshots = [item for item in emitted if isinstance(item, ReasoningSnapshot)]
    assert len(snapshots) == 1
    assert snapshots[0].text == "part1 part2"
    assert snapshots[0].snapshot is True
