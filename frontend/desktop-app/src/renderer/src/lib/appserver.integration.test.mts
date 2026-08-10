/**
 * Phase4-D2 integration test: ProtocolClient against the real stub
 * appserver over stdio JSON-RPC.
 *
 * Proves the exact flow the main window drives (DC1: no Python imports,
 * no HTTP): initialize -> session/new -> session/prompt -> final.
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { ProtocolClient } from '@rxycode/protocol-client'

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..')
const repoRoot = process.env.RXYCODE_REPO_DIR ?? resolve(appRoot, '..', '..')

interface StubPromptResult {
  run_id: string
  status: string
  text: string
}

function delay(ms: number): Promise<void> {
  return new Promise((resolveWait) => setTimeout(resolveWait, ms))
}

function startStubAppserver(): {
  child: ChildProcessWithoutNullStreams
  client: ProtocolClient
} {
  const child: ChildProcessWithoutNullStreams = spawn('python', ['-m', 'appserver'], {
    cwd: repoRoot,
    env: {
      ...process.env,
      RXYCODE_APPSERVER_STUB: '1',
      PYTHONUNBUFFERED: '1',
      PYTHONIOENCODING: 'utf-8'
    },
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true
  })
  child.stdout.setEncoding('utf8')
  child.stderr.setEncoding('utf8')

  const client = new ProtocolClient((line) => {
    child.stdin.write(`${line}\n`)
  })

  let buffer = ''
  child.stdout.on('data', (chunk: string) => {
    buffer += chunk
    const lines = buffer.split(/\r?\n/)
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (line.trim() !== '') {
        void client.handleLine(line)
      }
    }
  })
  return { child, client }
}

test('stub appserver supports initialize, session/new and session/prompt over protocol-client', async () => {
  const { child, client } = startStubAppserver()
  const notifications: Array<{ method: string; params: unknown }> = []
  client.onNotification = (method, params) => {
    notifications.push({ method, params })
  }
  try {
    const initialized = await client.requestWithTimeout<{
      protocol_version: string
      server_name: string
    }>('initialize', {
      client_name: 'rxycode-desktop-test',
      client_version: '0.0.0-test',
      protocol_version: '1.0.0',
      capabilities: {}
    })
    assert.equal(initialized.protocol_version, '1.0.0')
    assert.equal(initialized.server_name, 'rxycode-appserver')

    const created = await client.requestWithTimeout<{
      session_id: string
      workspace_root: string
    }>('session/new', { workspace_root: repoRoot })
    assert.ok(created.session_id)
    assert.equal(created.workspace_root, repoRoot)

    const result = await client.requestWithTimeout<StubPromptResult>(
      'session/prompt',
      { session_id: created.session_id, text: 'hello from d2 test' },
      30_000
    )
    assert.equal(result.status, 'succeeded')
    assert.equal(result.text, 'stub:hello from d2 test')
    assert.ok(
      notifications.some(
        (notification) =>
          notification.method === 'event/final' &&
          (notification.params as { text?: string })?.text === 'stub:hello from d2 test'
      ),
      'expected event/final with the stub answer'
    )
  } finally {
    client.rejectAllPending(new Error('test teardown'))
    try {
      await client.requestWithTimeout('shutdown', { reason: 'd2 integration test teardown' }, 5_000)
    } catch {
      // Best-effort shutdown; kill below covers the exit path.
    }
    child.kill()
    await delay(300)
  }
})

test('EOF shutdown while a prompt is pending never resolves the pending prompt', async () => {
  const { child, client } = startStubAppserver()
  try {
    await client.requestWithTimeout('initialize', {
      client_name: 'rxycode-desktop-test',
      client_version: '0.0.0-test',
      protocol_version: '1.0.0',
      capabilities: {}
    })
    const created = await client.requestWithTimeout<{ session_id: string }>('session/new', {
      workspace_root: repoRoot
    })

    // A hanging prompt keeps an id pending in the renderer client. The main
    // process must never answer it: it only closes stdin (EOF) on shutdown
    // and owns no JSON-RPC id space of its own.
    const promptPromise = client.requestWithTimeout(
      'session/prompt',
      { session_id: created.session_id, text: 'hang:blocked' },
      60_000
    )
    await delay(400)

    child.stdin.end()
    await delay(500)

    let settled = false
    promptPromise.then(
      () => {
        settled = true
      },
      () => {
        settled = true
      }
    )
    await delay(100)
    assert.equal(
      settled,
      false,
      'pending prompt must not be resolved by shutdown traffic (no shared id space)'
    )

    client.rejectAllPending(new Error('test teardown'))
    await assert.rejects(promptPromise, /test teardown/)
  } finally {
    client.rejectAllPending(new Error('test teardown'))
    child.kill()
    await delay(300)
  }
})

function startFakeAppserver(): {
  child: ChildProcessWithoutNullStreams
  client: ProtocolClient
} {
  const child: ChildProcessWithoutNullStreams = spawn(
    process.execPath,
    [join(appRoot, 'scripts', 'fake-appserver.mjs')],
    {
      cwd: appRoot,
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true
    }
  )
  child.stdout.setEncoding('utf8')
  child.stderr.setEncoding('utf8')

  const client = new ProtocolClient((line) => {
    child.stdin.write(`${line}\n`)
  })

  let buffer = ''
  child.stdout.on('data', (chunk: string) => {
    buffer += chunk
    const lines = buffer.split(/\r?\n/)
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (line.trim() !== '') {
        void client.handleLine(line)
      }
    }
  })
  return { child, client }
}

test('fake appserver approval round trip resolves an approved decision', async () => {
  const { child, client } = startFakeAppserver()
  const serverRequests: Array<{ request_id: string; risk_level: string; action: string }> = []
  client.onServerRequest = async (method, params) => {
    assert.equal(method, 'approval/request')
    const request = params as { request_id: string; risk_level: string; action: string }
    serverRequests.push(request)
    return { request_id: request.request_id, decision: 'approved' }
  }
  try {
    await client.requestWithTimeout('initialize', {
      client_name: 'rxycode-desktop-test',
      client_version: '0.0.0-test',
      protocol_version: '1.0.0',
      capabilities: {}
    })
    const created = await client.requestWithTimeout<{ session_id: string }>('session/new', {
      workspace_root: appRoot
    })
    const result = await client.requestWithTimeout<StubPromptResult>(
      'session/prompt',
      { session_id: created.session_id, text: 'approval demo' },
      30_000
    )
    assert.equal(result.status, 'succeeded')
    assert.equal(serverRequests.length, 1)
    assert.equal(serverRequests[0]?.risk_level, 'WRITE')
    assert.match(serverRequests[0]?.action ?? '', /^bash: write approval-demo-\d+\.txt$/)
  } finally {
    client.rejectAllPending(new Error('test teardown'))
    try {
      await client.requestWithTimeout('shutdown', { reason: 'd4 integration teardown' }, 5_000)
    } catch {
      // Best-effort shutdown; kill below covers the exit path.
    }
    child.kill()
    await delay(300)
  }
})

test('fake appserver preserves an asynchronously resolved approval decision', async () => {
  const { child, client } = startFakeAppserver()
  const toolEnds: Array<{ ok?: boolean }> = []
  client.onNotification = (method, params) => {
    if (method === 'event/tool_end') toolEnds.push(params as { ok?: boolean })
  }
  client.onServerRequest = async (method, params) => {
    assert.equal(method, 'approval/request')
    const request = params as { request_id: string }
    // This mirrors the desktop UI: the callback remains pending while the
    // user reads the dialog, then resolves after an explicit decision.
    await delay(80)
    return { request_id: request.request_id, decision: 'approved' }
  }
  try {
    await client.requestWithTimeout('initialize', {
      client_name: 'rxycode-desktop-test',
      client_version: '0.0.0-test',
      protocol_version: '1.0.0',
      capabilities: {}
    })
    const created = await client.requestWithTimeout<{ session_id: string }>('session/new', {
      workspace_root: appRoot
    })
    const result = await client.requestWithTimeout<StubPromptResult>(
      'session/prompt',
      { session_id: created.session_id, text: 'approval demo' },
      30_000
    )
    assert.equal(result.status, 'succeeded')
    assert.ok(toolEnds.some((event) => event.ok === true), 'approved action must finish successfully')
  } finally {
    client.rejectAllPending(new Error('test teardown'))
    child.kill()
    await delay(300)
  }
})
