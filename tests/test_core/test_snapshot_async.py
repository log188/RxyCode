"""Regression tests for non-blocking Git snapshot capture."""

from __future__ import annotations

import asyncio

import pytest

from RxyCode.RxyCode1_1_0.core import snapshot as snapshot_module


@pytest.mark.asyncio
async def test_capture_async_keeps_event_loop_responsive(monkeypatch, tmp_path):
    """The pre-LLM snapshot must not run synchronous git on the appserver loop."""
    calls: list[tuple[str, ...]] = []

    async def fake_run(args, cwd, stdin_text=None):
        calls.append(tuple(args))
        await asyncio.sleep(0)
        return ""

    monkeypatch.setattr(snapshot_module, "_run_git_async", fake_run)
    snapshot = snapshot_module.GitSnapshot(repo_path=str(tmp_path))

    heartbeat = asyncio.Event()
    task = asyncio.create_task(snapshot.capture_async())
    asyncio.get_running_loop().call_soon(heartbeat.set)

    assert await task is True
    assert heartbeat.is_set()
    assert calls == [("status", "--porcelain"), ("diff",)]


@pytest.mark.asyncio
async def test_capture_async_times_out_without_blocking_follow_up_work(monkeypatch, tmp_path):
    """A hung git child is bounded and does not delay the next model step."""
    monkeypatch.setattr(snapshot_module, "GIT_TIMEOUT_S", 0.01)

    async def fake_run(*_args, **_kwargs):
        await asyncio.sleep(1)
        return ""

    monkeypatch.setattr(snapshot_module, "_run_git_async", fake_run)
    snapshot = snapshot_module.GitSnapshot(repo_path=str(tmp_path))

    started = asyncio.get_running_loop().time()
    assert await snapshot.capture_async() is False
    elapsed = asyncio.get_running_loop().time() - started
    assert elapsed < 0.2


@pytest.mark.asyncio
async def test_capture_async_does_not_repeat_a_failed_optional_snapshot(monkeypatch, tmp_path):
    """A failed optional snapshot must not add one timeout per tool round."""
    calls = 0

    async def fake_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise TimeoutError("git unavailable")

    monkeypatch.setattr(snapshot_module, "_run_git_async", fake_run)
    snapshot = snapshot_module.GitSnapshot(repo_path=str(tmp_path))

    assert await snapshot.capture_async() is False
    assert await snapshot.capture_async() is False
    assert calls == 1
