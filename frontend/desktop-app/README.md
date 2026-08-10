# @rxycode/desktop-app

RxyCode Desktop shell: Electron + Vite + React (Phase 4 D1).

The Electron **main** process spawns `python -m appserver` as a stdio
JSON-RPC child process (repo root as cwd), keeps protocol data on the child's
stdout only, forwards stderr as logs, and kills the child on quit so no orphan
process is left behind.

The **renderer** never imports Python and never calls HTTP; it only talks to
the main process through the preload bridge (`window.api.appserver`).

## Commands

```powershell
npm install
npm run dev            # development (HMR)
npm run typecheck      # tsc for main/preload/renderer
npm run build          # typecheck + electron-vite build
npm run smoke          # build + headless initialize handshake against stub appserver (dev)
npm run runtime:prepare # stage self-contained Python runtime + vendored RxyCode (Phase4-D6)
npm run runtime:verify  # validate the staged runtime
npm run build:win       # Windows package with embedded runtime (also build:mac / build:linux)
npm run packaged-smoke  # handshake against the packaged app (must report SMOKE_RUNTIME bundled)
npm run smoke:update    # real electron-updater check+download against a local feed (Phase4-D7)
npm run smoke:crash     # real renderer crash -> sanitized diagnostic + no orphan appserver (Phase4-D7)
```

Update & crash reporting (Phase4-D7) live in the settings page "更新与诊断"
tab: checking/downloading/installing updates is fully manual, crash-report
consent defaults to off and diagnostic bundles are sanitized (no keys,
prompts or tool input/output). Dev-mode update checks use `dev-app-update.yml`
(packaged builds use the generated `app-update.yml`); point
`RXYCODE_UPDATE_FEED_URL` at a local generic feed for dev/smoke testing and
`RXYCODE_CRASH_REPORT_URL` to enable crash uploads after consent. Both smoke
scripts spawn real processes and must run outside the sandbox.

Runtime priority (D6): bundled `resources/runtime/` python wins; dev fallback
uses `python -m appserver` from `../RxyCode-master` or `RXYCODE_REPO_DIR`.

Platform status (D6): Windows is verified on this machine; macOS/Linux
configs are ready but the build must run on CI / the respective platform.

## Known limitations (Phase 4 MVP)

This is an honest status of what the Phase 4 desktop MVP does NOT do yet.
The app is usable for chat/streaming/approval/workspace flows; the items
below are explicitly out of scope or blocked by backend protocol gaps.

1. **Model / API Key management are live via appserver JSON-RPC**
   (`models/*`, `credentials/*`): the Settings page lists models (with the
   Phase 3 limit summary when the backend provides it), switches the active
   model, tests connections, deletes models, and stores/clears API keys.
   Keys are stored by the backend credential_store (Windows DPAPI) and never
   echoed to the renderer. Servers without the new methods fall back to the
   BLOCKED panel automatically (method-not-found detection).
2. **No subagent UI yet**: the desktop shell does not consume Phase B
   subagent events (`child_session/*`), `@agent` mention, `/children`,
   `/child`, `/parent` or `agent/invoke`. The OpenTUI frontend has those;
   desktop will pick them up in a follow-up.
3. **macOS / Linux packages are not yet verified on real machines**; CI
   matrix jobs are configured but must run (Linux snap needs snapcraft,
   macOS unsigned builds need `CSC_IDENTITY_AUTO_DISCOVERY=false`).
4. **Orphan-guard scripts are skipped inside packaged asar builds**; the
   dev/unpacked paths are covered. Production-package process cleanup still
   needs a packaged-app verification (D6 follow-up).
5. **API Key storage**: when credential management lands it must use the OS
   keychain (DC4), not renderer localStorage.
6. **Protocol client**: the desktop app depends on the shared
   `frontend/protocol-client` package (single source of truth); schema
   changes regenerate both OpenTUI and desktop types.

Smoke mode runs with `RXYCODE_DESKTOP_SMOKE=1` and
`RXYCODE_APPSERVER_STUB=1`, so it never touches the LLM or user config.

## CI (Phase4-D8)

`.github/workflows/ci.yml` (GitHub Actions, on push / pull request / manual
dispatch) runs:

- `test` (ubuntu-latest): `npm run typecheck` + `npm test`. Checks out the
  backend repo read-only as `../RxyCode-master` (same sibling layout as local)
  and resolves the appserver package via `PYTHONPATH`; the checkout is never
  modified.
- `build` (windows-latest / macos-latest / ubuntu-latest): runs the D6 scripts
  `build:win` / `build:mac` / `build:linux` and uploads the `dist/` artifacts.
  Each job stages its platform runtime from the CI Python (setup-python) after
  installing `requirements.txt` plus `setuptools wheel`.

Before the first real CI run, fill in the `RXYCODE_MASTER_REPO` placeholder in
the workflow (e.g. `xin-yi33/RxyCode`, branch `main`). Windows is verified on
this machine; macOS/Linux builds are validated by CI (pending first real run).
