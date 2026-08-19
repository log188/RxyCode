"""Load config/bridge_workers.json. H13 may later fill model/cache_contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BridgeWorkerSpec:
    worker_id: str
    command: list[str]
    ws_url: str | None = None
    secret_ref: str | None = None
    model: str | None = None
    cache_contract: dict[str, Any] | None = None


def load_bridge_workers(path: Path | None = None) -> list[BridgeWorkerSpec]:
    target = path or Path(__file__).resolve().parents[3] / "config" / "bridge_workers.json"
    if not target.exists():
        return []
    raw = json.loads(target.read_text(encoding="utf-8"))
    rows = raw.get("workers") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise ValueError("bridge_workers.json must contain a workers list")
    specs: list[BridgeWorkerSpec] = []
    for item in rows:
        if not isinstance(item, dict) or not item.get("worker_id"):
            raise ValueError("each worker needs worker_id")
        command = item.get("command") or []
        if not isinstance(command, list):
            raise ValueError("command must be a list")
        specs.append(
            BridgeWorkerSpec(
                worker_id=str(item["worker_id"]),
                command=[str(part) for part in command],
                ws_url=item.get("ws_url"),
                secret_ref=item.get("secret_ref"),
                model=item.get("model"),
                cache_contract=item.get("cache_contract")
                if isinstance(item.get("cache_contract"), dict)
                else None,
            )
        )
    return specs
