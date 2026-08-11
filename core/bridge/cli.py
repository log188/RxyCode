"""B10: CLI 透传兜底桥接适配器（grok-build `grok agent stdio`、codex exec 等）。

官方 agent CLI 作为旁路子进程运行，官方 prompt 原样透传（不重写）。
事件流按 NDJSON 逐行解析（协议差异由各 agent 的 event schema 决定）。
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncIterator

from .acp import _kill_process_tree
from .base import AgentBridge, BridgeConfig

STDIN = asyncio.subprocess.PIPE
STDOUT = asyncio.subprocess.PIPE


class CLIBridge(AgentBridge):
    """CLI 兜底：spawn 任意官方 agent CLI，任务经 stdin 注入。"""

    def __init__(
        self,
        cfg: BridgeConfig | None = None,
        cmd: list[str] | None = None,
    ) -> None:
        super().__init__(cfg or BridgeConfig())
        self._cmd = cmd or ["grok", "agent", "stdio"]
        self._proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        kwargs: dict = {}
        if os.name != "nt":
            kwargs["start_new_session"] = True
        else:  # pragma: no cover - Windows 分支
            import subprocess as _sp

            kwargs["creationflags"] = getattr(
                _sp, "CREATE_NEW_PROCESS_GROUP", 0
            )
        self._proc = await asyncio.create_subprocess_exec(
            *self._cmd,
            stdin=STDIN,
            stdout=STDOUT,
            stderr=asyncio.subprocess.PIPE,
            **kwargs,
        )

    async def invoke(self, task: str) -> AsyncIterator[dict]:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise RuntimeError("bridge not started")
        req = {
            "type": "task_delegate",
            "target": task,
            "lineage": ["main-session-ref"],  # lineage-only，不复制主历史
        }
        proc.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
        await proc.stdin.drain()
        async for line in proc.stdout:
            try:
                yield json.loads(line)
            except (ValueError, TypeError):
                continue

    async def stop(self) -> None:
        proc = self._proc
        if proc is not None and proc.returncode is None:
            _kill_process_tree(proc)
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass

    def usage(self) -> dict:
        """本桥接 usage；按 B9 契约归一化（与 ACP 同语义）。"""
        model = self.cfg.model or ""
        provider = self.cfg.provider or ""
        if not model or not provider:
            return {}
        from RxyCode.RxyCode1_1_0.core.catalog import get_contract

        contract = get_contract(provider, model)
        if contract is None:
            return {}
        fields = contract.get("usage_fields") or {}
        return {
            "cached_field": fields.get("cached"),
            "cost_ticks_field": fields.get("cost_ticks"),
            "reasoning_field": fields.get("reasoning"),
            "cache_mode": contract.get("cache_mode"),
        }
