#!/usr/bin/env node
/**
 * Phase4-D1 headless smoke test (dev layout).
 *
 * Builds the app, launches Electron in smoke mode, asserts the initialize
 * handshake against the stub appserver, verifies a clean shutdown and that
 * no `python -m appserver` child process is left behind (DC5 orphan rule).
 */
import { existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runSmokeRun } from './smoke-lib.mts'

const appDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = process.env.RXYCODE_REPO_DIR ?? resolve(appDir, '..', 'RxyCode-master')
const electronExe =
  process.platform === 'win32'
    ? join(appDir, 'node_modules', 'electron', 'dist', 'electron.exe')
    : join(appDir, 'node_modules', '.bin', 'electron')

if (!existsSync(electronExe)) {
  console.error(`SMOKE_ABORT electron binary not found: ${electronExe}`)
  process.exit(2)
}

runSmokeRun({
  exe: electronExe,
  args: ['.'],
  cwd: appDir,
  env: { RXYCODE_DESKTOP_SMOKE: '1' },
  expectedRuntime: 'dev',
  schemaDir: repoRoot
})
  .then((code) => process.exit(code))
  .catch((error) => {
    console.error(`SMOKE_ABORT ${String(error)}`)
    process.exit(1)
  })
