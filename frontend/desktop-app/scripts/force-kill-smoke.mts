#!/usr/bin/env node
/**
 * Phase4-D3 DC5 regression: force-kill Electron and prove the stub
 * appserver child is not left behind as an orphan.
 *
 * Runs Electron in keepalive smoke mode (stub appserver, hidden window).
 * Phase 1 kills ONLY the Electron main process (taskkill /F without /T
 * on Windows, SIGKILL on POSIX) and asserts the appserver exits -- this
 * proves the Job Object / orphan guard, not just tree-kill propagation.
 * Phase 2 sweeps any residual Electron child processes so the test
 * leaves the machine clean.
 */
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

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

readFileSync(join(repoRoot, 'protocol', 'schema.json'), 'utf8')

let childPid: number | null = null
let ready = false
let output = ''

const electron = spawn(electronExe, ['.'], {
  cwd: appDir,
  env: {
    ...process.env,
    RXYCODE_DESKTOP_SMOKE: '1',
    RXYCODE_DESKTOP_KEEPALIVE: '1',
    RXYCODE_APPSERVER_STUB: '1'
  },
  windowsHide: true,
  stdio: ['ignore', 'pipe', 'pipe']
})

electron.stdout.setEncoding('utf8')
electron.stderr.setEncoding('utf8')

electron.stdout.on('data', (chunk: string) => {
  output += chunk
  process.stdout.write(chunk)
  for (const match of chunk.matchAll(/SMOKE_CHILD_PID (\d+)/g)) {
    childPid = Number(match[1])
  }
  if (output.includes('SMOKE_READY')) ready = true
})

electron.stderr.on('data', (chunk: string) => {
  process.stderr.write(chunk)
})

const overallTimeout = setTimeout(() => {
  console.error('SMOKE_ABORT timed out waiting for the keepalive Electron run')
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/pid', String(electron.pid), '/T', '/F'], { stdio: 'ignore' })
  } else {
    try {
      process.kill(electron.pid, 'SIGKILL')
    } catch {
      // already gone
    }
  }
  process.exit(1)
}, 120_000)

electron.on('error', (error) => {
  clearTimeout(overallTimeout)
  console.error(`SMOKE_ABORT failed to launch Electron: ${String(error)}`)
  process.exit(1)
})

electron.on('exit', (code) => {
  if (!ready) {
    clearTimeout(overallTimeout)
    console.error(`SMOKE_FAIL Electron exited before SMOKE_READY (code ${String(code)})`)
    process.exit(1)
  }
})

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolveWait) => setTimeout(resolveWait, ms))
}

async function waitForExit(pid: number, attempts: number): Promise<boolean> {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (!isAlive(pid)) return true
    await delay(500)
  }
  return !isAlive(pid)
}

function killElectronMainOnly(pid: number): void {
  if (process.platform === 'win32') {
    const killed = spawnSync('taskkill', ['/pid', String(pid), '/F'], { stdio: 'ignore' })
    if (killed.status !== 0) {
      console.error(`SMOKE_FAIL taskkill main-only returned ${String(killed.status)}`)
      process.exit(1)
    }
  } else {
    try {
      process.kill(pid, 'SIGKILL')
    } catch {
      // already gone
    }
  }
}

function electronChildren(pid: number): number[] {
  if (process.platform === 'win32') {
    const listed = spawnSync(
      'powershell.exe',
      [
        '-NoProfile',
        '-Command',
        `Get-CimInstance Win32_Process -Filter "ParentProcessId = ${pid}" | ForEach-Object { $_.ProcessId }`
      ],
      { encoding: 'utf8', windowsHide: true }
    )
    return (listed.stdout ?? '')
      .split(/\r?\n/)
      .map((line) => Number(line.trim()))
      .filter((childPid) => Number.isInteger(childPid) && childPid > 0)
  }
  const listed = spawnSync('pgrep', ['-P', String(pid)], { encoding: 'utf8' })
  return (listed.stdout ?? '')
    .split(/\r?\n/)
    .map((line) => Number(line.trim()))
    .filter((childPid) => Number.isInteger(childPid) && childPid > 0)
}

async function cleanupElectronTree(pid: number): Promise<void> {
  if (process.platform === 'win32') {
    // The main pid is usually already dead; a tree kill also covers any
    // late-reparented stragglers that still answer to the old pid.
    spawnSync('taskkill', ['/pid', String(pid), '/T', '/F'], { stdio: 'ignore' })
  } else {
    try {
      process.kill(pid, 'SIGKILL')
    } catch {
      // already gone
    }
  }
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const children = electronChildren(pid)
    if (children.length === 0) return
    for (const childPid of children) {
      if (process.platform === 'win32') {
        spawnSync('taskkill', ['/pid', String(childPid), '/T', '/F'], { stdio: 'ignore' })
      } else {
        spawnSync('pkill', ['-P', String(childPid)], { stdio: 'ignore' })
        try {
          process.kill(childPid, 'SIGKILL')
        } catch {
          // already gone
        }
      }
    }
    await delay(500)
  }
  const remaining = electronChildren(pid)
  if (remaining.length > 0) {
    console.error(`SMOKE_FAIL residual Electron child processes remain: ${remaining.join(',')}`)
    process.exit(1)
  }
}

async function run(): Promise<void> {
  const deadline = Date.now() + 90_000
  while (!ready || childPid === null) {
    if (Date.now() > deadline) {
      console.error('SMOKE_FAIL keepalive markers never arrived')
      process.exit(1)
    }
    await delay(200)
  }

  console.log(`SMOKE_FORCE_KILL_TARGET electron ${electron.pid} appserver ${childPid}`)
  killElectronMainOnly(electron.pid)

  const gone = await waitForExit(childPid, 20)
  if (!gone) {
    console.error(
      `SMOKE_FAIL appserver survived main-only Electron kill (guard not effective, pid ${childPid})`
    )
    process.exit(1)
  }
  console.log(`SMOKE_GUARD_OK appserver ${childPid} exited after main-only Electron kill`)

  await cleanupElectronTree(electron.pid)
  clearTimeout(overallTimeout)
  console.log('SMOKE_FORCE_KILL_OK no orphan appserver, Electron children cleaned up')
  process.exit(0)
}

void run()
