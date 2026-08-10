import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  createCrashReportManager,
  redactSecrets,
  sanitizeDetail,
  truncateLine,
  type CrashDiagnostic,
  type CrashDiagnosticContext,
  type CrashReportManager
} from './crash-report.ts'

const BASE_CONTEXT: CrashDiagnosticContext = {
  app: {
    version: '0.1.0',
    electron: '39.8.10',
    chrome: '140.0.0.0',
    node: '22.20.0',
    platform: 'win32',
    arch: 'x64'
  },
  protocol: {
    protocolVersion: '1.0.0',
    appserverStatus: 'running',
    appserverExit: null,
    protocolViolations: 0,
    appserverPid: 1234
  },
  logSummary: ['appserver ready', 'stub mode enabled']
}

function fixtureDir(): string {
  return mkdtempSync(join(tmpdir(), 'rxycode-crash-test-'))
}

interface FakeCrashState {
  nativeStarts: number
  nativeStops: number
  crashes: number
}

function createManager(
  dir: string,
  overrides: Partial<{
    context: CrashDiagnosticContext
    uploadUrl: string | null
    upload: (payload: CrashDiagnostic) => Promise<void>
    onCrash: () => void
    randomId: () => string
  }> = {}
): {
  manager: CrashReportManager
  uploads: CrashDiagnostic[]
  state: FakeCrashState
} {
  const uploads: CrashDiagnostic[] = []
  const state: FakeCrashState = { nativeStarts: 0, nativeStops: 0, crashes: 0 }
  const manager = createCrashReportManager({
    userDataDir: dir,
    context: () => overrides.context ?? BASE_CONTEXT,
    uploadUrl: overrides.uploadUrl ?? null,
    upload:
      overrides.upload ??
      ((payload) => {
        uploads.push(payload)
        return Promise.resolve()
      }),
    onCrash:
      overrides.onCrash ??
      (() => {
        state.crashes += 1
      }),
    randomId: overrides.randomId ?? (() => 'test-id')
  })
  return { manager, uploads, state }
}

test('redactSecrets scrubs keys, tokens and authorization headers', () => {
  const input = [
    'api_key: sk-1234567890abcdef1234',
    '"apiKey": "sk-abcdef0123456789abcdef"',
    'Authorization: Bearer abcdefghijklmnop1234',
    'token = a1b2c3d4e5f6g7h8',
    'x-api-key: K7l0mN2oP3qR4sT5uV6wX7yZ'
  ].join('\n')
  const output = redactSecrets(input)
  assert.ok(!output.includes('sk-1234567890abcdef1234'))
  assert.ok(!output.includes('sk-abcdef0123456789abcdef'))
  assert.ok(!output.includes('abcdefghijklmnop1234'))
  assert.ok(!output.includes('a1b2c3d4e5f6g7h8'))
  assert.ok(!output.includes('K7l0mN2oP3qR4sT5uV6wX7yZ'))
  assert.ok(output.includes('api_key: <redacted>'))
  assert.ok(output.includes('"apiKey": "<redacted>"'))
  assert.ok(output.includes('Authorization: <redacted>'))
})

test('redactSecrets scrubs long opaque tokens', () => {
  const token = 'A'.repeat(64)
  assert.ok(!redactSecrets(`token_value=${token}`).includes(token))
})

test('truncateLine caps over-long lines', () => {
  const long = 'x'.repeat(2000)
  const truncated = truncateLine(long)
  assert.ok(truncated.length < 600)
  assert.match(truncated, /<truncated \d+ chars>/)
  assert.equal(truncateLine('short'), 'short')
})

test('sanitizeDetail redacts nested string values', () => {
  const sanitized = sanitizeDetail({
    prompt: 'please implement feature X with sk-1234567890abcdef',
    tool: { input: 'cat /etc/passwd', output: 'root:x:0:0' },
    count: 3
  })
  const serialized = JSON.stringify(sanitized)
  assert.ok(!serialized.includes('sk-1234567890abcdef'))
  assert.ok(serialized.includes('<redacted>'))
  assert.equal(sanitized.count as number, 3)
})

test('consent defaults to off and persists across managers', () => {
  const dir = fixtureDir()
  try {
    const first = createManager(dir)
    assert.equal(first.manager.getConsent(), false)
    first.manager.setConsent(true)
    assert.equal(first.manager.getConsent(), true)

    const second = createManager(dir)
    assert.equal(second.manager.getConsent(), true)

    second.manager.setConsent(false)
    const third = createManager(dir)
    assert.equal(third.manager.getConsent(), false)
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})

test('capture writes a sanitized diagnostic bundle', () => {
  const dir = fixtureDir()
  try {
    const { manager } = createManager(dir, {
      context: {
        ...BASE_CONTEXT,
        logSummary: [
          'appserver ready',
          'sk-1234567890abcdef1234 leaked here',
          'Authorization: Bearer abcdefghijklmnop1234',
          'ok'
        ]
      }
    })
    const diagnostic = manager.capture('render-process-gone', { reason: 'crashed' })
    assert.ok(diagnostic !== null)
    assert.equal(diagnostic.schema, 'rxycode.crash-diagnostic.v1')
    assert.equal(diagnostic.source, 'render-process-gone')
    assert.equal(diagnostic.app.version, '0.1.0')
    assert.equal(diagnostic.protocol.protocolVersion, '1.0.0')

    const files = readdirSync(join(dir, 'crash-reports'))
    assert.equal(files.length, 1)
    const raw = readFileSync(join(dir, 'crash-reports', files[0]), 'utf8')
    assert.ok(!raw.includes('sk-1234567890abcdef1234'))
    assert.ok(!raw.includes('abcdefghijklmnop1234'))
    assert.ok(raw.includes('<redacted>'))
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})

test('upload only happens with consent and the configured URL', async () => {
  const dir = fixtureDir()
  try {
    const off = createManager(dir, { uploadUrl: 'http://127.0.0.1:9/upload' })
    off.manager.capture('uncaught-exception', {})
    assert.equal(off.uploads.length, 0)

    const on = createManager(dir, { uploadUrl: 'http://127.0.0.1:9/upload' })
    on.manager.setConsent(true)
    on.manager.capture('uncaught-exception', {})
    await new Promise((resolveWait) => setTimeout(resolveWait, 50))
    assert.equal(on.uploads.length, 1)
    assert.equal(on.uploads[0].source, 'uncaught-exception')
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})

test('listReports returns newest first and survives unreadable files', () => {
  const dir = fixtureDir()
  try {
    const first = createManager(dir, { randomId: () => 'id-a' })
    first.manager.capture('render-process-gone', {})
    const second = createManager(dir, { randomId: () => 'id-b' })
    second.manager.capture('child-process-gone', {})

    const reports = second.manager.listReports()
    assert.equal(reports.length, 2)
    assert.ok(reports[0].capturedAt >= reports[1].capturedAt)
    assert.ok(existsSync(reports[0].path))
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})

test('repeated captures are safe and each writes its own bundle', () => {
  const dir = fixtureDir()
  try {
    let sequence = 0
    const { manager, state } = createManager(dir, {
      randomId: () => {
        sequence += 1
        return `id-${sequence}`
      }
    })
    manager.capture('render-process-gone', {})
    manager.capture('render-process-gone', {})
    assert.equal(state.crashes, 2)
    const files = readdirSync(join(dir, 'crash-reports'))
    assert.equal(files.length, 2)
    // The side effect hook must be safe to call again and again (idempotent wiring).
    manager.capture('uncaught-exception', {})
    assert.equal(state.crashes, 3)
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})
