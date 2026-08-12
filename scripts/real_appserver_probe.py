#!/usr/bin/env python3
"""Run one real appserver prompt and record the complete JSON-RPC trace.

This is intentionally a test harness, not a replacement client.  It launches
the production stdio appserver, writes a single prompt, records stdout/stderr
with monotonic timestamps, and exits only after the corresponding RPC result
or the supplied deadline.  It is useful for diagnosing Desktop failures where
the renderer timeout hides the worker-side cause.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


def _record(handle: Any, elapsed: float, stream: str, line: str) -> None:
    handle.write(
        json.dumps(
            {"elapsed_seconds": round(elapsed, 3), "stream": stream, "line": line},
            ensure_ascii=False,
        )
        + "\n"
    )
    handle.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--stall-seconds", type=float, default=45.0)
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "RXYCODE_APPSERVER_STALL_SECONDS": str(args.stall_seconds),
            "RXYCODE_APPSERVER_HEARTBEAT_SECONDS": "5",
        }
    )
    process = subprocess.Popen(
        [args.python, "-m", "appserver"],
        cwd=workspace,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    started = time.monotonic()
    incoming: queue.Queue[tuple[str, str]] = queue.Queue()

    def read_stream(stream: Any, name: str) -> None:
        for raw in stream:
            incoming.put((name, raw.rstrip("\n")))

    for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
        threading.Thread(target=read_stream, args=(stream, name), daemon=True).start()

    def send(request_id: int, method: str, params: dict[str, Any]) -> None:
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        process.stdin.flush()

    session_id: str | None = None
    result: dict[str, Any] | None = None
    current_request = 1
    send(
        current_request,
        "initialize",
        {
            "client_name": "rxycode-real-probe",
            "client_version": "1",
            "protocol_version": "1.0.0",
            "capabilities": {},
        },
    )

    with output.open("w", encoding="utf-8") as trace:
        while time.monotonic() - started < args.timeout:
            try:
                stream_name, line = incoming.get(timeout=0.25)
            except queue.Empty:
                continue
            elapsed = time.monotonic() - started
            _record(trace, elapsed, stream_name, line)
            if stream_name != "stdout":
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("method") == "approval/request" and "id" in message:
                response = {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {
                        "request_id": str((message.get("params") or {}).get("request_id", "")),
                        "decision": "approved",
                    },
                }
                process.stdin.write(json.dumps(response, ensure_ascii=False) + "\n")
                process.stdin.flush()
                continue
            if message.get("id") != current_request:
                continue
            if current_request == 1 and "result" in message:
                current_request = 2
                send(current_request, "session/new", {"workspace_root": str(workspace)})
                continue
            if current_request == 2 and "result" in message:
                session_id = str((message.get("result") or {}).get("session_id", ""))
                if not session_id:
                    result = {"status": "failed", "error": "session/new returned no session_id"}
                    break
                current_request = 3
                send(
                    current_request,
                    "session/prompt",
                    {"session_id": session_id, "text": args.prompt, "timeout_seconds": args.timeout},
                )
                continue
            if current_request == 3 and ("result" in message or "error" in message):
                result = message
                break

        _record(
            trace,
            time.monotonic() - started,
            "summary",
            json.dumps(
                {
                    "session_id": session_id,
                    "result": result,
                    "timed_out": result is None,
                    "return_code": process.poll(),
                },
                ensure_ascii=False,
            ),
        )

    process.stdin.close()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=8)
    return 0 if result is not None and "result" in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
