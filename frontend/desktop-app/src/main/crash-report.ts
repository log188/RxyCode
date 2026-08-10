/**
 * Sanitized crash reporting (Phase4-D7).
 *
 * Captures Desktop crashes (renderer gone, child process gone, main
 * uncaught errors) into local diagnostic bundles that contain only app
 * version / platform / protocol state / sanitized log summary. API keys,
 * full prompts and tool input/output never leave the process and are
 * scrubbed before anything is written. Upload only happens after the user
 * explicitly enables consent (default off); the toggle takes effect
 * immediately.
 *
 * The module is framework-agnostic: Electron pieces (userData dir, native
 * crashReporter, uploader) are injected so unit tests can run without a
 * real app.
 */
import { EventEmitter } from 'node:events'
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

export const CRASH_DIAGNOSTIC_SCHEMA = 'rxycode.crash-diagnostic.v1'
export const CRASH_CONSENT_FILE = 'crash-report-consent.json'

export interface CrashAppInfo {
  version: string
  electron: string
  chrome: string
  node: string
  platform: string
  arch: string
}

export interface CrashProtocolInfo {
  protocolVersion: string | null
  appserverStatus: string | null
  appserverExit: { code: number | null; signal: string | null } | null
  protocolViolations: number
  appserverPid: number | null
}

export interface CrashDiagnosticContext {
  app: CrashAppInfo
  protocol: CrashProtocolInfo
  /** Last stderr log lines from the appserver manager (sanitized on write). */
  logSummary: readonly string[]
}

export interface CrashDiagnostic {
  schema: typeof CRASH_DIAGNOSTIC_SCHEMA
  id: string
  capturedAt: string
  source: string
  detail: Record<string, unknown>
  app: CrashAppInfo
  protocol: CrashProtocolInfo
  logs: string[]
}

export interface CrashReportSummary {
  id: string
  capturedAt: string
  source: string
  path: string
}

export interface CrashReportManagerOptions {
  /** Directory used for the consent file and crash-reports/ (userData). */
  userDataDir: string
  /** Live diagnostic context (app/protocol state, log summary). */
  context: () => CrashDiagnosticContext
  /** Upload endpoint; uploads only happen with consent. */
  uploadUrl?: string | null
  /** Injectable uploader (defaults to fetch POST). */
  upload?: (payload: CrashDiagnostic) => Promise<void>
  /** Called once per capture; index.ts uses this to kill the appserver (DC5). */
  onCrash?: () => void
  now?: () => Date
  randomId?: () => string
  maxLogLines?: number
}

export interface CrashReportManager {
  on(event: 'captured', listener: (summary: CrashReportSummary) => void): CrashReportManager
  getConsent(): boolean
  setConsent(enabled: boolean): void
  capture(source: string, detail?: Record<string, unknown>): CrashDiagnostic | null
  listReports(): CrashReportSummary[]
}

const MAX_LOG_LINE_LENGTH = 500

/**
 * Scrub secret-shaped text before it can land in a diagnostic bundle.
 * Order matters: key/value patterns run before the generic long-token
 * pattern so field names stay readable.
 */
export function redactSecrets(input: string): string {
  return input
    .replace(/((?:api[_-]?key|apikey)["']?\s*[:=]\s*["']?)[A-Za-z0-9._-]{8,}/gi, '$1<redacted>')
    .replace(/(sk-[A-Za-z0-9_-]{8,})/g, 'sk-<redacted>')
    .replace(/((?:authorization|x-api-key)\s*[:=]\s*)[^\r\n]*/gi, '$1<redacted>')
    .replace(/((?:token|secret|password|passwd)["']?\s*[:=]\s*["']?)[^\s,;]{4,}/gi, '$1<redacted>')
    .replace(/(\bBearer\s+)[A-Za-z0-9._-]{8,}/gi, '$1<redacted>')
    .replace(/\b[A-Za-z0-9+/_-]{48,}\b/g, '<redacted-token>')
}

export function truncateLine(line: string): string {
  if (line.length <= MAX_LOG_LINE_LENGTH) return line
  const excess = line.length - MAX_LOG_LINE_LENGTH
  return `${line.slice(0, MAX_LOG_LINE_LENGTH)}?<truncated ${excess} chars>`
}

export function redactLine(line: string): string {
  return truncateLine(redactSecrets(line))
}

/** Deep-copy detail values, redacting every string so no secret survives. */
export function sanitizeDetail(detail: Record<string, unknown>): Record<string, unknown> {
  const sanitized: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(detail)) {
    if (typeof value === 'string') {
      sanitized[key] = truncateLine(redactSecrets(value))
    } else if (typeof value === 'object' && value !== null) {
      sanitized[key] = sanitizeDetail(value as Record<string, unknown>)
    } else {
      sanitized[key] = value
    }
  }
  return sanitized
}

async function defaultUpload(uploadUrl: string, payload: CrashDiagnostic): Promise<void> {
  const response = await fetch(uploadUrl, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!response.ok) {
    throw new Error(`crash report upload failed with HTTP ${response.status}`)
  }
}

export function createCrashReportManager(options: CrashReportManagerOptions): CrashReportManager {
  const emitter = new EventEmitter()
  const reportsDir = join(options.userDataDir, 'crash-reports')
  const consentFile = join(options.userDataDir, CRASH_CONSENT_FILE)
  const maxLogLines = options.maxLogLines ?? 20
  const now = options.now ?? ((): Date => new Date())
  const randomId = options.randomId ?? ((): string => crypto.randomUUID())

  function readConsent(): boolean {
    try {
      const raw = readFileSync(consentFile, 'utf8')
      const parsed = JSON.parse(raw) as { enabled?: unknown }
      return parsed.enabled === true
    } catch {
      return false
    }
  }

  let consentEnabled = readConsent()

  const manager: CrashReportManager = {
    on: (event, listener) => {
      emitter.on(event, listener)
      return manager
    },
    getConsent: () => consentEnabled,
    setConsent(enabled) {
      consentEnabled = enabled
      try {
        mkdirSync(options.userDataDir, { recursive: true })
        writeFileSync(consentFile, JSON.stringify({ enabled }, null, 2), 'utf8')
      } catch {
        // Consent still applies for this session; persistence is best-effort.
      }
    },
    capture(source, detail = {}) {
      let context: CrashDiagnosticContext
      try {
        context = options.context()
      } catch {
        context = {
          app: {
            version: 'unknown',
            electron: 'unknown',
            chrome: 'unknown',
            node: 'unknown',
            platform: 'unknown',
            arch: 'unknown'
          },
          protocol: {
            protocolVersion: null,
            appserverStatus: null,
            appserverExit: null,
            protocolViolations: 0,
            appserverPid: null
          },
          logSummary: []
        }
      }
      const id = randomId()
      const capturedAt = now().toISOString()
      const diagnostic: CrashDiagnostic = {
        schema: CRASH_DIAGNOSTIC_SCHEMA,
        id,
        capturedAt,
        source,
        detail: sanitizeDetail(detail),
        app: { ...context.app },
        protocol: {
          ...context.protocol,
          appserverExit: context.protocol.appserverExit
            ? { ...context.protocol.appserverExit }
            : null
        },
        logs: context.logSummary.slice(-maxLogLines).map(redactLine)
      }
      try {
        mkdirSync(reportsDir, { recursive: true })
        const filePath = join(reportsDir, `crash-${capturedAt.replace(/[:.]/g, '-')}-${id}.json`)
        writeFileSync(filePath, JSON.stringify(diagnostic, null, 2), 'utf8')
        const summary: CrashReportSummary = { id, capturedAt, source, path: filePath }
        emitter.emit('captured', summary)
        if (consentEnabled && options.uploadUrl) {
          const upload =
            options.upload ??
            ((payload: CrashDiagnostic) => defaultUpload(options.uploadUrl!, payload))
          void upload(diagnostic).catch(() => {
            // Upload is best-effort; the local bundle is already written.
          })
        }
        options.onCrash?.()
        return diagnostic
      } catch (error) {
        // Never let crash reporting itself take the app down.
        console.error('crash-report write failed', error)
        return null
      }
    },
    listReports() {
      if (!existsSync(reportsDir)) return []
      return readdirSync(reportsDir)
        .filter((name) => name.endsWith('.json'))
        .map((name) => {
          const path = join(reportsDir, name)
          try {
            const parsed = JSON.parse(readFileSync(path, 'utf8')) as Partial<CrashDiagnostic>
            return {
              id: parsed.id ?? name,
              capturedAt: parsed.capturedAt ?? '',
              source: parsed.source ?? 'unknown',
              path
            }
          } catch {
            return { id: name, capturedAt: '', source: 'unreadable', path }
          }
        })
        .sort((a, b) => b.capturedAt.localeCompare(a.capturedAt))
    }
  }
  return manager
}
