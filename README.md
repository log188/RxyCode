<!-- README_SYNC: source=working-tree; updated=2026-08-16 -->
<div align="center">

**English** · [简体中文](./README.zh-CN.md)

# RxyCode

**A local plan-and-execute coding agent for developers — OpenTUI, Desktop GUI, and a safety gate in front of every tool call.**

[⭐ Star this repo](https://github.com/xin-yi33/RxyCode) if you want to keep a local coding agent that plans, runs tools, and asks before risky writes.

[![Version](https://img.shields.io/badge/version-1.2.10-blue.svg)](https://github.com/xin-yi33/RxyCode/releases/tag/v1.2.10)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/xin-yi33/RxyCode/actions/workflows/ci.yml/badge.svg)](https://github.com/xin-yi33/RxyCode/actions/workflows/ci.yml)
[![Issues](https://img.shields.io/github/issues/xin-yi33/RxyCode)](https://github.com/xin-yi33/RxyCode/issues)
[![Stars](https://img.shields.io/github/stars/xin-yi33/RxyCode?style=social)](https://github.com/xin-yi33/RxyCode/stargazers)

</div>

<div align="center">
  <img src="docs/images/gui-shell.png" alt="RxyCode Desktop chat shell" width="800">
</div>

RxyCode is a Python coding agent with a headless core (`Session` over `AgentV2`) and three frontends: **OpenTUI** (default terminal UI), **Desktop** (`rxycode gui`), and an **Ink** fallback. Complex work goes through a LangGraph plan → decompose → execute → validate → synthesize pipeline. Simple questions take a fast path. Isolated child agents, MCP, and 30+ tools sit behind a risk-classified safety gate.

## Why this instead of a linear ReAct loop

These are the differences that change how you work, each pointing at code:

| Difference | What you get | Where |
|---|---|---|
| Verification before “done” | A validator checks tool results against the original goal before the agent reports success | `validation/` |
| Plan-and-execute, not a single tool loop | Hierarchical decomposition, dependency-aware parallel execution, then synthesis | `planning/`, `execution/`, `synthesis/`, `core/graph.py` |
| Safety gate on every tool | READ / WRITE / DANGER classification, write whitelist, approval dialogs, audit log | `core/safety/` |
| Two real surfaces | OpenTUI over stdio JSON-RPC, plus Desktop Plan / Goal / `+` menu | `frontend/opentui-app/`, `frontend/desktop-app/`, `appserver/` |
| Isolated child agents | Independent session, tools, permissions, and budget — not a recursive call of the primary agent | `core/subagents/` |
| Headless core | `Session.prompt()` has no I/O of its own; TUI and GUI only subscribe to protocol events | `core/session.py` |

## Quick start

### Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | Backend runtime |
| Bun | latest | Auto-installed by the one-command installer when missing (OpenTUI) |
| Node.js | 20+ | Desktop GUI, Ink fallback (`RXYCODE_TUI=ink`) |
| OpenAI-compatible API key | — | Any provider you configure (OpenAI, DeepSeek, OpenCode Go, …) |

### Option 1: One-command install

**Windows PowerShell:**

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/xin-yi33/RxyCode/v1.2.10/install.ps1 | iex"
rxycode
```

**macOS / Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/xin-yi33/RxyCode/v1.2.10/install.sh | sh
rxycode
```

The installer bootstraps `uv` if needed, creates an isolated tool environment, and installs the pinned **`v1.2.10`** release.

**Downloads:** only the latest release (**`v1.2.10`**) publishes installable wheel/sdist assets. Older GitHub Releases keep notes but do not offer binary downloads.

### Option 2: Run once with uv

```bash
uvx --from "git+https://github.com/xin-yi33/RxyCode.git@v1.2.10" rxycode
```

### Option 3: Permanent install

```bash
uv tool install --force "git+https://github.com/xin-yi33/RxyCode.git@v1.2.10"
rxycode
```

### Option 4: From source

```bash
git clone https://github.com/xin-yi33/RxyCode.git
cd RxyCode
python -m pip install -e .
rxycode
```

### Option 5: Docker

```bash
cp .env.example .env   # Set OPENAI_API_KEY and RXYCODE_API_TOKEN
docker compose up -d api       # API server (loopback only)
docker compose run --rm tui    # Interactive TUI (needs TTY)
```

### First launch

| Command | What opens |
|---------|------------|
| `rxycode` or `python -m RxyCode` | Default **OpenTUI** (Bun + `frontend/opentui-app/`) |
| `rxycode --version` | Package version, no runtime init |
| `rxycode gui` | **Desktop** Electron app (`frontend/desktop-app/`) |
| `rxycode --api` | API server only (`api_server.py`, HTTP + SSE) |
| `RXYCODE_TUI=ink rxycode` | Ink fallback TUI |

1. Run `rxycode`. The TUI opens even with no model configured.
2. If the model list is empty, OpenTUI shows a welcome hint and opens `/addmodel` (credentials are masked).
3. If at least one model is already in `~/.RxyCode/config.yaml`, there is no extra hint.
4. Type a natural-language task. For Desktop, use `rxycode gui` and the Composer at the bottom.

## How the CLI works

OpenTUI is the default CLI. It talks to the core over **stdio JSON-RPC**: the frontend spawns `python -m appserver`, which hosts `Session` → `AgentV2`. You type a task; the agent streams tokens, tool calls, approval requests, and a final answer.

**Demo task recorded for this README:** in an empty directory outside this repo, ask RxyCode to write a single-file `click-counter.html` — a large button, a click count, and a compact layout. The run should finish in a few minutes. You should see the prompt, tool calls (`write` / `read`), an approval if the safety gate asks, and the HTML file on disk.

The recording below is a real run of that task: a visible terminal titled **RxyCode CLI 1.2.10** starts `python -m appserver`, sends the prompt over ProtocolClient, streams tool calls and progress, then writes `click-counter.html`.

<p align="center">
  <video controls width="800" poster="docs/images/cli-demo-cover.png" src="docs/assets/cli-demo.mp4">
    <a href="docs/assets/cli-demo.mp4">CLI demo video (mp4)</a>
  </video>
</p>

<p align="center">
  <a href="docs/assets/cli-demo.mp4"><img src="docs/images/cli-demo-cover.png" alt="CLI demo cover: write tool finishes click-counter.html" width="800"></a>
</p>

Same transport without the TUI (useful for scripts and the Desktop CLI harness):

```text
python -m appserver
        │  stdio JSON-RPC
        ▼
ProtocolClient  →  session/new  →  session/prompt
```

The in-tree harness is `frontend/desktop-app/scripts/real-business-cli-harness.mts`. It is a test/ops tool, not an extra user command.

## Desktop GUI

`rxycode gui` launches the Electron app. Composer sits at the bottom of the task pane. The `+` button opens:

| Menu item | What it does |
|-----------|----------------|
| 文件和文件夹 | Attach a local file; the path is written into the prompt |
| 在项目中使用 | Pick a workspace and start a new chat |
| 目标 | Open the Goal dialog (Escape or overlay click closes it) |
| 计划模式 | Toggle Plan mode (agent stays on the plan document) |

Plan cards offer **是，实施此计划**, a **补充说明** field, and **跳过**. Permission labels in the UI are 更改前询问 / 自动编辑 / 完全访问. Switching to 完全访问 asks for confirmation (Escape cancels). Settings → 更新与诊断 shows product version **1.2.10**.

<p align="center">
  <img src="docs/images/gui-plus-menu.png" alt="Composer plus menu: attach, workspace, goal, plan" width="800">
</p>
<p align="center">
  <img src="docs/images/gui-goal-dialog.png" alt="Goal dialog" width="800">
</p>
<p align="center">
  <img src="docs/images/gui-plan-card.png" alt="Plan card with Build, Revise, and Skip" width="800">
</p>

## Architecture

```
OpenTUI (frontend/opentui-app)     Desktop (frontend/desktop-app)
        │ stdio JSON-RPC                    │ stdio JSON-RPC
        └──────────────┬────────────────────┘
                       ▼
              python -m appserver
                       │
                       ▼
              Session (core/session.py)
                       │
                       ▼
              AgentV2 (core/agent_v2.py)
                 ├── simple query  →  fast path + cache
                 ├── multi-task    →  isolated child agents
                 ├── compose       →  Plan + Build
                 └── complex       →  LangGraph:
                       goal_planner → decomposer → executor
                            → ToolOrchestrator + core/safety
                            → validator → synthesizer

Ink fallback: RXYCODE_TUI=ink → api_server.py (HTTP + SSE) → same Session
```

`Session` is transport-agnostic: it emits protocol events; it does not draw UI. `appserver` maps those events to stdout JSON-RPC. `api_server.py` maps the same events to SSE for Ink.

## Modes

| Surface | How | Behavior |
|---------|-----|----------|
| Build | `/build` (TUI) or Desktop default | Plan → decompose → execute → validate → synthesize |
| Plan | `/plan` or Desktop 计划模式 | Read-only analysis and a plan document; no file edits until you Build |
| Compose | `/compose` | Plan + build with a shorter pipeline |

## Configuration

Stored at `~/.RxyCode/config.yaml`. The active model's `base_url` is the one you selected — RxyCode does not silently rewrite it to another provider.

```yaml
cache:
  enabled: true
  prompt_prefix_cache: true   # Provider-side KV cache
  ttl: 3600

# Example: OpenCode Go
models:
  opencode-go/deepseek-v4-flash:
    model_name: deepseek-v4-flash
    provider_id: opencode-go
    provider_name: OpenCode Go
    api_key_env: OPENCODE_GO_API_KEY   # or api_key_secret, stored outside the repo
    base_url: https://opencode.ai/zen/go/v1
    max_tokens: 8192
    temperature: 0.7
```

Use `/addmodel` in OpenTUI for a guided wizard. Do not put API keys in the repo, README, or screenshots.

## Safety boundary

Before a tool runs, `core/safety/` classifies it:

- **READ** — inspect only (`read`, `grep`, `glob`, `webfetch`, …)
- **WRITE** — reversible side effects (`write`, `edit`, most `bash`)
- **DANGER** — destructive or installer-like commands; bash can escalate by pattern (`rm -rf /`, `git push --force`, …)

Writes outside the whitelist are blocked. The TUI and Desktop raise an approval dialog; the audit log is `~/.RxyCode/logs/audit.jsonl` with sensitive keys redacted. Default Desktop permission is 更改前询问.

## Commands and shortcuts (OpenTUI)

| Command | Description |
|---------|-------------|
| `/help` | All commands |
| `/addmodel` | Add a model (masked credentials) |
| `/models` / `/model <name>` | List / switch models |
| `/build` `/plan` `/compose` | Work mode |
| `/clear` | Clear conversation context |
| `/memory add/list/search` | Memory |
| `/queue add/run` | Task queue |
| `/cache` | Cache stats |
| `/language` | UI language |
| `/thinking` | Thinking panel |
| `/children` `/child` `/parent` | Isolated child-agent tree (when subagents are on) |

| Shortcut | Action |
|----------|--------|
| `Tab` | Switch work mode |
| `Ctrl+P` | Command palette |
| `Ctrl+T` | Toggle thinking |
| `Esc` | Cancel |
| `Ctrl+C` | Copy / cancel stream / clear input; twice within 2s to quit |

## Testing

Do not treat a badge count as a live census. Recorded baselines live in [CHANGELOG.md](CHANGELOG.md) (for example 10412 on v1.2.8, 10840 on v1.2.9) and [docs/modules/tests.md](docs/modules/tests.md). CI is [`.github/workflows/ci.yml`](https://github.com/xin-yi33/RxyCode/actions/workflows/ci.yml).

```bash
# Frontend
cd frontend && npm test
cd frontend/opentui-app && bun test

# Backend (deterministic; no paid live models)
python -m pytest tests -m "not live and not pty and not serial" -n 2 --dist loadscope -q
python -m pytest tests -m "serial and not live and not pty" -n 0 -q

# Packaging contract used by the installers
python -m pytest tests/unit/test_packaging_contract.py tests/unit/test_installers.py -q
```

Live provider tests are opt-in and skipped without keys. This tree also ran a local GUI/CLI real-business suite **T01–T08**; **T09 was skipped**.

## Version history

| Version | Date | Highlights |
|---------|------|------------|
| [v1.2.10](https://github.com/xin-yi33/RxyCode/releases/tag/v1.2.10) | 2026-08 | Desktop Plan / Goal / `+` menu; plan card Build/Revise/Skip; CLI `appserver` + ProtocolClient harness; T01–T08 local real-business run (T09 skipped) |
| [v1.2.9](https://github.com/xin-yi33/RxyCode/releases/tag/v1.2.9) | 2026-08 | Isolated subagents (Phase C): independent child sessions; `@agent` mention, Task tool, `subtask=true`; OpenTUI child tree; upstream-reuse audit; 10840 tests recorded in CHANGELOG, evals GATE 94.7% |
| [v1.2.8](https://github.com/xin-yi33/RxyCode/releases/tag/v1.2.8) | 2026-08 | Model adaptation: DeepSeek v4, Doubao (ark), Anthropic Claude 5 family; exact capability isolation; 10412 tests recorded in CHANGELOG |
| [v1.2.7](https://github.com/xin-yi33/RxyCode/releases/tag/v1.2.7) | 2026-08 | Completed answers no longer discarded by failed read-only probes; smarter web-research queries; Doubao provider |
| [v1.2.6](https://github.com/xin-yi33/RxyCode/releases/tag/v1.2.6) | 2026-08 | webfetch decoding, MCP mis-routing, Windows shell/encoding, web search hardening |
| [v1.2.5](https://github.com/xin-yi33/RxyCode/releases/tag/v1.2.5) | 2026-08 | DeepSeek / Qwen / Claude adaptation; lazy imports; explicit request routing; stdio transport |
| [v1.2.4](https://github.com/xin-yi33/RxyCode/releases/tag/v1.2.4) | 2026-08 | Add-model polish; eval harness; typed protocol + TypeScript client |
| [v1.2.3](https://github.com/xin-yi33/RxyCode/releases/tag/v1.2.3) | 2026-07 | 10 provider presets, auto discovery, batch add |
| [v1.2.2](https://github.com/xin-yi33/RxyCode/releases/tag/v1.2.2) | 2026-07 | Auto-install Bun + OpenTUI deps; empty-model `/addmodel` |
| [v1.2.1](https://github.com/xin-yi33/RxyCode/releases/tag/v1.2.1) | 2026-07 | Ship OpenTUI sources in the wheel |
| [v1.2.0](https://github.com/xin-yi33/RxyCode/releases/tag/v1.2.0) | 2026-07 | OpenTUI default TUI (Ink fallback) |
| [v1.1.0](https://github.com/xin-yi33/RxyCode/releases/tag/v1.1.0) | 2026-07 | Ink TUI, SSE, Docker, CI, one-command installers |
| [v1.0.0](https://github.com/xin-yi33/RxyCode/releases/tag/v1.0.0) | 2026-06 | LangGraph rewrite: plan-and-execute, tools, tiered memory |
| [v0.3.3](https://github.com/xin-yi33/RxyCode/releases/tag/v0.3.3) | 2025-12 | Initial release: ReAct + verification + MCP |

Full notes: [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE) © RxyCode contributors

If RxyCode is useful, [star the repo](https://github.com/xin-yi33/RxyCode) so you can find it again. Bugs and ideas: [Issues](https://github.com/xin-yi33/RxyCode/issues).
