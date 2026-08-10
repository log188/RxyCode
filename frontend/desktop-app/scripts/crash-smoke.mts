#!/usr/bin/env node
/**
 * Crash smoke (Phase4-D7).
 *
 * Launches the packaged (win-unpacked) app in crash-sim mode: the renderer
 * is forcefully crashed after the window loads, the main process must
 * capture a sanitized diagnostic bundle, kill the appserver tree (DC5) and
 * exit cleanly. The script asserts the bundle invariants (required fields,
 * no secret-shaped content) and that the appserver child is not orphaned.
 *
 * Prerequisite: `npm run build:unpack` (win-unpacked). This script spawns
 * real processes and must run outside the sandbox (taskkill-based tree
 * kill is blocked inside it).
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const EXE = join(ROOT, 'dist', 'win-unpacked', 'rxycode-desktop.exe')
const REPO_DIR = resolve(ROOT, '..', 'RxyCode-master')

function waitForExit(pid: number | null, attempts: number): Promise<boolean> {
  return new Promise((resolveExit) => {
    const probe = (): void => {
      if (attempts <= 0) return resolveExit(false)
      attempts -= 1
      try {
        process.kill(pid, 0)
      } catch (error) {
        if (error && error.code === 'ESRCH') return resolveExit(true)
      }
      setTimeout(probe, 500)
    }
    probe()
  })
}

const SECRET_PATTERNS: RegExp[] = [
  /sk-[A-Za-z0-9_-]{8,}/,
  /api[_-]?key["']?\s*[:=]\s*["']?[A-Za-z0-9._-]{8,}/i,
  /(?:authorization|x-api-key)\s*[:=]\s*[^\s,;]{4,}/i,
  /\bBearer\s+[A-Za-z0-9._-]{8,}/i,
  /\b[A-Za-z0-9+/_-]{48,}\b/
]

async function main(): Promise<number> {
  if (!existsSync(EXE)) {
    console.error(`CRASH_SMOKE_ABORT missing ${EXE}; run "npm run build:unpack" first`)
    return 1
  }
  const userData = mkdtempSync(join(tmpdir(), 'rxycode-crash-smoke-'))
  const output: string[] = []
  const app = spawn(EXE, [], {
    cwd: userData,
    env: {
      ...process.env,
      RXYCODE_DESKTOP_CRASH_SIM: 'render-gone',
      RXYCODE_DESKTOP_USER_DATA: userData,
      RXYCODE_APPSERVER_STUB: '1',
      RXYCODE_REPO_DIR: REPO_DIR
    },
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe']
  })
  app.stdout.setEncoding('utf8')
  app.stdout.on('data', (chunk: string) => {
    process.stdout.write(chunk)
    output.push(chunk)
  })
  app.stderr.on('data', (chunk: string) => {
    process.stderr.write(chunk)
  })

  const timeout = setTimeout(() => {
    console.error('CRASH_SMOKE_ABORT timed out waiting for the crash smoke run')
    app.kill()
  }, 180_000)

  const exitCode = await new Promise<number>((resolveExit) => {
    app.on('exit', (code) => {
      clearTimeout(timeout)
      resolveExit(code ?? -1)
    })
  })

  const all = output.join('')
  const failures: string[] = []
  if (exitCode !== 0) failures.push(`app exit code ${exitCode}`)
  if (all.includes('SMOKE_FAILED')) failures.push('SMOKE_FAILED marker present')
  const source = all.match(/CRASH_SOURCE (\S+)/)
  const reason = all.match(/CRASH_REASON (\S+)/)
  const reportFile = all.match(/CRASH_REPORT_FILE (\S+)/)
  const childPid = all.match(/SMOKE_CHILD_PID (\d+)/)
  if (source === null || source[1] !== 'render-process-gone') {
    failures.push('CRASH_SOURCE render-process-gone marker missing')
  }
  if (reason === null || reason[1] === '') failures.push('CRASH_REASON marker missing')
  if (reportFile === null) failures.push('CRASH_REPORT_FILE marker missing')
  if (childPid === null) failures.push('SMOKE_CHILD_PID marker missing')

  let diagnosticText: string | null = null
  if (reportFile !== null && existsSync(reportFile[1])) {
    diagnosticText = readFileSync(reportFile[1], 'utf8')
    let diagnostic: {
      schema?: unknown
      source?: unknown
      app?: { version?: unknown; platform?: unknown }
      protocol?: { protocolVersion?: unknown }
      logs?: unknown
    }
    try {
      diagnostic = JSON.parse(diagnosticText) as typeof diagnostic
    } catch {
      failures.push('crash diagnostic is not valid JSON')
      diagnostic = {}
    }
    if (diagnostic.schema !== 'rxycode.crash-diagnostic.v1') {
      failures.push(`crash diagnostic schema mismatch: ${String(diagnostic.schema)}`)
    }
    if (diagnostic.source !== 'render-process-gone') {
      failures.push(`crash diagnostic source mismatch: ${String(diagnostic.source)}`)
    }
    if (typeof diagnostic.app?.version !== 'string' || diagnostic.app.version === '') {
      failures.push('crash diagnostic missing app.version')
    }
    if (diagnostic.protocol?.protocolVersion !== '1.0.0') {
      failures.push(
        `crash diagnostic protocolVersion mismatch: ${String(diagnostic.protocol?.protocolVersion)}`
      )
    }
    if (!Array.isArray(diagnostic.logs)) failures.push('crash diagnostic logs must be an array')
  } else {
    failures.push(`crash diagnostic file missing: ${reportFile !== null ? reportFile[1] : 'n/a'}`)
  }

  if (diagnosticText !== null) {
    for (const pattern of SECRET_PATTERNS) {
      if (pattern.test(diagnosticText)) {
        failures.push(`crash diagnostic contains secret-shaped content (${String(pattern)})`)
      }
    }
  }

  if (failures.length > 0) {
    console.error(`CRASH_SMOKE_FAIL ${failures.join('; ')}`)
    rmSync(userData, { recursive: true, force: true })
    return 1
  }

  const gone = await waitForExit(childPid !== null ? Number(childPid[1]) : null, 20)
  if (!gone) {
    console.error(
      `CRASH_SMOKE_FAIL orphaned appserver child still alive (pid ${childPid !== null ? childPid[1] : 'n/a'})`
    )
    rmSync(userData, { recursive: true, force: true })
    return 1
  }
  console.log(
    `CRASH_SMOKE_OK diagnostic ${reportFile !== null ? reportFile[1] : 'n/a'} sanitized, no orphan appserver`
  )
  rmSync(userData, { recursive: true, force: true })
  return 0
}

main()
  .then((code) => process.exit(code))
  .catch((error) => {
    console.error(`CRASH_SMOKE_FAILED ${String(error)}`)
    process.exit(1)
  })
