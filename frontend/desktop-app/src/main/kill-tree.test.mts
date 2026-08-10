import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { killProcessTree } from './appserver.ts'

function delay(ms: number): Promise<void> {
  return new Promise((resolveWait) => setTimeout(resolveWait, ms))
}

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

async function waitForExit(pid: number, attempts = 30, intervalMs = 300): Promise<boolean> {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (!isAlive(pid)) return true
    await delay(intervalMs)
  }
  return !isAlive(pid)
}

test('killProcessTree terminates the direct child and its descendants', async () => {
  const child = spawn(
    'python',
    [
      '-c',
      [
        'import subprocess, time, sys',
        'p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])',
        'print(p.pid, flush=True)',
        'time.sleep(120)'
      ].join('\n')
    ],
    {
      stdio: ['ignore', 'pipe', 'ignore'],
      windowsHide: true,
      detached: process.platform !== 'win32'
    }
  )

  const grandchildPid = await new Promise<number>((resolvePid, rejectPid) => {
    const timer = setTimeout(
      () => rejectPid(new Error('timed out waiting for grandchild pid')),
      10_000
    )
    let buffer = ''
    child.stdout.setEncoding('utf8')
    child.stdout.on('data', (chunk: string) => {
      buffer += chunk
      const newline = buffer.indexOf('\n')
      if (newline < 0) return
      clearTimeout(timer)
      resolvePid(Number(buffer.slice(0, newline).trim()))
    })
    child.on('error', (error) => {
      clearTimeout(timer)
      rejectPid(error)
    })
  })

  try {
    const childPid = child.pid
    if (childPid === undefined) throw new Error('child pid unavailable')
    await killProcessTree(childPid)
    assert.equal(await waitForExit(childPid), true, 'direct child must exit after killProcessTree')
    assert.equal(isAlive(grandchildPid), false, 'descendant must exit after killProcessTree')
  } finally {
    if (child.pid !== undefined && isAlive(child.pid)) child.kill('SIGKILL')
    if (isAlive(grandchildPid)) {
      try {
        process.kill(grandchildPid, 'SIGKILL')
      } catch {
        // best-effort cleanup
      }
    }
  }
})
