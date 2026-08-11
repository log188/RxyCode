"""B10: ACP（JSON-RPC over stdio）桥接适配器。

Claude Code ACP / Qwen Code ACP / Kimi Code ACP 语义：NDJSON 请求-响应。
复用 appserver/jsonrpc.py 的封装语义（逐行 JSON）。
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncIterator

from .base import AgentBridge, BridgeConfig

STDIN = asyncio.subprocess.PIPE
STDOUT = asyncio.subprocess.PIPE


def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    """luna R1-3: 杀死整个进程树（官方 CLI 会派生子孙进程）。

    Windows: taskkill /T /F（按 PID 递归）；POSIX: 进程组 killpg。
    """
    if os.name == "nt":
        try:
            import subprocess

            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=10,
            )
            return
        except Exception:
            pass
    # POSIX：进程组 kill（os.killpg 仅在非 Windows 存在）
    killpg = getattr(os, "killpg", None)
    if killpg is not None:
        try:
            killpg(os.getpgid(proc.pid), 9)  # pragma: no cover - POSIX only
            return
        except (ProcessLookupError, OSError):
            pass
    try:
        proc.kill()
    except ProcessLookupError:
        pass


class ACPBridge(AgentBridge):
    """ACP 适配器：spawn 官方 agent（--acp），NDJSON JSON-RPC 会话。"""

    def __init__(
        self,
        cfg: BridgeConfig | None = None,
        cmd: list[str] | None = None,
    ) -> None:
        super().__init__(cfg or BridgeConfig())
        self._cmd = cmd or ["claude", "--acp"]
        self._proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        """spawn 子进程并完成 ACP 握手（进程组隔离，便于整树 kill）。"""
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
        """发送 session/new_prompt 请求，流式消费 NDJSON 事件。"""
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise RuntimeError("bridge not started")
        req = {
            "jsonrpc": "2.0",
            "method": "session/new_prompt",
            "params": {"text": task},
            "id": 1,
        }
        proc.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
        await proc.stdin.drain()
        async for line in proc.stdout:
            try:
                msg = json.loads(line)
            except (ValueError, TypeError):
                continue
            method = msg.get("method")
            if method in ("agent_message_chunk", "agent_thought_chunk", "tool_call"):
                yield {"type": method, "content": msg.get("params", {})}
            elif method == "session/result":
                yield {"type": "result", "content": msg.get("params", {}).get("result", "")}
                return

    async def stop(self) -> None:
        """超时/预算超限时 kill 整树并回收（不留僵尸进程，luna R1-3）。"""
        proc = self._proc
        if proc is not None and proc.returncode is None:
            _kill_process_tree(proc)
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass

    def usage(self) -> dict:
        """本桥接 usage；按 B9 契约归一化（luna R1-1：桥接按模型读契约）。

        桥接 agent 是旁路子进程（官方 CLI 自行管理协议细节），本层只
        按 B9 cache_contract 的 usage_fields 语义回填命中/成本字段；
        未识别模型 → 空（CB8）。
        """
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
