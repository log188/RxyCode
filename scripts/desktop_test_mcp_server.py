"""Minimal local MCP echo service used by the Desktop real-E2E suite.

It never accesses the network or user files.  The Desktop test temporarily
registers it through the normal ``mcpServers`` configuration path, then restores
the user's configuration after the scenario completes.
"""

from __future__ import annotations

import json
import sys


def emit(message: dict) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


for raw in sys.stdin:
    request = json.loads(raw)
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        emit(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "desktop-test-echo", "version": "1"},
                },
            }
        )
    elif method == "tools/list":
        emit(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "Return an exact non-sensitive test marker.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"text": {"type": "string"}},
                                "required": ["text"],
                                "additionalProperties": False,
                            },
                            "annotations": {"readOnlyHint": True},
                        }
                    ]
                },
            }
        )
    elif method == "tools/call":
        text = str(request.get("params", {}).get("arguments", {}).get("text", ""))
        emit(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": f"desktop-test-echo:{text}"}],
                    "isError": False,
                },
            }
        )
