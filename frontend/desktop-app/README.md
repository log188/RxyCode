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
