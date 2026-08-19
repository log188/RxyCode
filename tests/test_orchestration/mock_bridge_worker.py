"""Stdio mock worker: speak the six F16 methods, then exit."""

from __future__ import annotations

import json
import sys
import time


def main() -> int:
    hang = "--hang" in sys.argv
    for line in sys.stdin:
        raw = json.loads(line)
        method = raw.get("method")
        params = raw.get("params") or {}
        task_id = params.get("task_id") or "t"
        if method == "abort":
            return 0
        if hang:
            time.sleep(30)
            continue
        if method != "task_delegate":
            continue
        def emit(name: str, payload: dict) -> None:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "method": name, "params": payload}) + "\n")
            sys.stdout.flush()

        emit(
            "plan",
            {"task_id": task_id, "steps": ["do"], "files": ["out.txt"], "est_tokens": 10, "ack": True},
        )
        emit(
            "progress",
            {
                "task_id": task_id,
                "status": "running",
                "stage": "implement",
                "percent": 50,
                "eta_s": 1,
                "notes": "working",
            },
        )
        emit(
            "tool_call",
            {
                "task_id": task_id,
                "tool": "write",
                "args": {"path": "out.txt"},
                "status": "done",
                "result_ref": "out.txt",
            },
        )
        emit(
            "result",
            {
                "task_id": task_id,
                "ok": True,
                "summary": "done",
                "artifact_paths": ["out.txt"],
                "tokens_used": 12,
                "duration_s": 0.2,
            },
        )
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
