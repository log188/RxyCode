#!/usr/bin/env node
/**
 * Phase4-D6 packaged smoke test.
 *
 * Spawns the packaged (win-unpacked) app with RXYCODE_DESKTOP_SMOKE=1 and
 * RXYCODE_REPO_DIR pointed at a nonexistent path, then asserts the
 * initialize handshake ran against the BUNDLED Python runtime (priority
 * rule: bundled runtime > dev fallback) and that no appserver child is
 * left behind. Proves the packaged app is self-contained: it must not
 * touch ../RxyCode-master or the dev machine's python.
 */
import { existsSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runSmokeRun } from './smoke-lib.mts'

const appDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const argIndex = process.argv.indexOf('--app')
const exe =
  argIndex >= 0
    ? resolve(process.argv[argIndex + 1])
    : process.platform === 'win32'
      ? join(appDir, 'dist', 'win-unpacked', 'rxycode-desktop.exe')
      : ''

if (exe === '') {
  console.error(
    'PACKAGED_SMOKE_ABORT default only supports Windows unpacked builds; pass --app <path-to-app-exe>'
  )
  process.exit(2)
}
if (!existsSync(exe)) {
  console.error(`PACKAGED_SMOKE_ABORT packaged app not found: ${exe}`)
  process.exit(2)
}

const stagedRuntime = join(appDir, 'build', 'runtime', `${process.platform}-${process.arch}`)
if (!existsSync(join(stagedRuntime, 'app', 'appserver', '__main__.py'))) {
  console.error(
    `PACKAGED_SMOKE_ABORT staged runtime missing at ${stagedRuntime}; run npm run runtime:prepare first`
  )
  process.exit(2)
}

const isolatedCwd = join(tmpdir(), 'rxycode-d6-packaged-smoke')
mkdirSync(isolatedCwd, { recursive: true })
const nonexistentRepo = join(isolatedCwd, 'no-such-repo')

runSmokeRun({
  exe,
  cwd: isolatedCwd,
  env: {
    RXYCODE_DESKTOP_SMOKE: '1',
    RXYCODE_REPO_DIR: nonexistentRepo
  },
  expectedRuntime: 'bundled',
  schemaDir: join(stagedRuntime, 'app')
})
  .then((code) => process.exit(code))
  .catch((error) => {
    console.error(`PACKAGED_SMOKE_ABORT ${String(error)}`)
    process.exit(1)
  })
