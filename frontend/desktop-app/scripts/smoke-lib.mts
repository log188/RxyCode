#!/usr/bin/env node
/**
 * Shared smoke runner (Phase4-D1 / D6).
 *
 * Spawns an Electron app in smoke mode (RXYCODE_DESKTOP_SMOKE=1) and
 * asserts the initialize handshake against the stub appserver, a clean
 * shutdown, and that no `python -m appserver` child is left behind (DC5).
 */
import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

export interface SmokeRunOptions {
  /** Electron (dev) or packaged app executable to spawn. */
  exe: string
  /** Working directory for the spawned app. */
  cwd: string
  /** Extra environment variables for the app. */
  env: NodeJS.ProcessEnv
  /** Which appserver source the app must report via SMOKE_RUNTIME. */
  expectedRuntime: 'dev' | 'bundled'
  /** Extra app args (dev electron needs the app path "."). */
  args?: string[]
  /** Directory containing protocol/schema.json for the expected protocol_version. */
  schemaDir: string
}

export async function runSmokeRun(options: SmokeRunOptions): Promise<number> {
  const schema = JSON.parse(
    readFileSync(join(options.schemaDir, 'protocol', 'schema.json'), 'utf8')
  ) as {
    protocol_version: string
  }
  const expectedProtocolVersion = schema.protocol_version

  const output: string[] = []
  let childPid: number | null = null
  let violations: number | null = null

  const app = spawn(options.exe, options.args ?? [], {
    cwd: options.cwd,
    env: { ...process.env, ...options.env },
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe']
  })

  app.stdout.setEncoding('utf8')
  app.stderr.setEncoding('utf8')

  app.stdout.on('data', (chunk: string) => {
    process.stdout.write(chunk)
    output.push(chunk)
    for (const match of chunk.matchAll(/SMOKE_CHILD_PID (\d+)/g)) {
      childPid = Number(match[1])
    }
    for (const match of chunk.matchAll(/SMOKE_VIOLATIONS (\d+)/g)) {
      violations = Number(match[1])
    }
  })

  app.stderr.on('data', (chunk: string) => {
    process.stderr.write(chunk)
  })

  const timeout = setTimeout(() => {
    console.error('SMOKE_ABORT timed out waiting for the smoke run')
    app.kill()
  }, 180_000)

  app.on('error', (error) => {
    clearTimeout(timeout)
    console.error(`SMOKE_ABORT failed to launch ${options.exe}: ${String(error)}`)
  })

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
  if (!all.includes('SMOKE_DONE')) failures.push('SMOKE_DONE marker missing')
  if (!all.includes(`SMOKE_RUNTIME ${options.expectedRuntime}`)) {
    failures.push(`SMOKE_RUNTIME ${options.expectedRuntime} marker missing`)
  }
  if (!all.includes('SMOKE_RESULT')) failures.push('SMOKE_RESULT marker missing')
  if (violations === null) failures.push('SMOKE_VIOLATIONS marker missing')
  if (violations !== null && violations > 0) {
    failures.push(`${violations} appserver stdout protocol violation(s)`)
  }
  if (childPid === null) failures.push('SMOKE_CHILD_PID marker missing')

  let result: { protocol_version?: unknown; server_name?: unknown } | null = null
  const resultMatch = all.match(/SMOKE_RESULT ({.*})/)
  if (resultMatch) {
    try {
      result = JSON.parse(resultMatch[1])
    } catch {
      failures.push('SMOKE_RESULT is not valid JSON')
    }
  }
  if (result) {
    if (result.protocol_version !== expectedProtocolVersion) {
      failures.push(
        `unexpected protocol_version ${String(result.protocol_version)} (expected ${expectedProtocolVersion})`
      )
    }
    if (result.server_name !== 'rxycode-appserver') {
      failures.push(`unexpected server_name ${String(result.server_name)}`)
    }
  }

  if (failures.length > 0) {
    console.error(`SMOKE_FAIL ${failures.join('; ')}`)
    return 1
  }

  const gone = await waitForExit(childPid, 20)
  if (!gone) {
    console.error(`SMOKE_FAIL orphaned appserver child still alive (pid ${childPid})`)
    return 1
  }
  console.log(`SMOKE_OK child pid ${childPid} exited, no orphan process left`)
  return 0
}

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
