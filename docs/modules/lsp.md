# lsp/ - LSP Integration

## What Is This Module?
Language Server Protocol (LSP) client for code intelligence: diagnostics-based
analysis. **Experimental** — currently only diagnostics are implemented;
completions, references, and hover are not.

## Key Files
| File | Purpose |
|------|---------|
| client.py | `LSPClient` - starts a language server over stdio and processes `textDocument/publishDiagnostics` messages |
| client.py | `Diagnostic` dataclass - per-file diagnostic result |
| client.py | `create_lsp_client(language, workspace)` - factory; `LSP_SERVERS` config maps language -> server command (pyright-langserver / typescript-language-server / gopls) |

## Core Code: client.py (LSPClient)

**Capabilities:**
- Get diagnostics (errors, warnings) for a file
- Get a per-workspace diagnostics summary

**Key Methods:**
- start(workspace): Start the LSP server for a workspace
- stop(): Stop the LSP server
- open_file(uri): Notify the server a file is open
- notify_change(uri, text): Notify the server of a document change
- get_diagnostics(file_path) -> list[Diagnostic]: Get diagnostics for a file
- get_diagnostics_summary(workspace) -> dict: Aggregate diagnostics across the workspace

**Status:** Experimental — diagnostics only; no completions/references/hover.
