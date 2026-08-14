#!/usr/bin/env node
import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, readdirSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { DesktopCdpHarness, repositoryDir, waitFor, type CleanupProof } from './cdp-harness.mts'
import { buildBatchPrompts, realBusinessScenarios, type RealBusinessScenario } from './real-business-scenarios.mts'
import { aggregateUsage, evaluateLayoutSnapshot, isMeaningfulProtocolEvent, terminalOutcomeIssue, type UsageSample, type UsageSummary } from './real-business-metrics.mts'

type Batch = 'A' | 'B'
type ProtocolMessage = Record<string, any> & { __at_ms?: number }

interface RealBusinessResult {
  id: string
  batch: Batch
  title: string
  prompt: string
  model: string
  provider: string
  gateway: string
  session_id: string
  status: string
  final_answer: string
  output_dir: string
  files: string[]
  artifact_kind: string
  usage: UsageSummary
  timing: {
    wall_ms: number
    visible_feedback_ms: number | null
    first_event_ms: number | null
    first_token_ms: number | null
    final_ms: number | null
    silent_gaps_ms: number[]
  }
  approvals: string[]
  tools: string[]
  skill_events: string[]
  mcp_events: string[]
  layout: { issues: Array<{ kind: string; elements: string[]; detail: string }> }
  layout_snapshot?: {
    viewport: { width: number; height: number }
    horizontalScroll: number
    elements: Array<{ id: string; left: number; top: number; right: number; bottom: number }>
  } | null
  screenshots: string[]
  protocol_file: string
  dom_file: string
  cleanup: CleanupProof | null
  defects: string[]
  repair_attempts: string[]
  error: string | null
}

function failureResult(
  scenario: RealBusinessScenario,
  batch: Batch,
  prompt: string,
  sessionId: string,
  model: string,
  gateway: string,
  batchDir: string,
  error: unknown
): RealBusinessResult {
  const message = error instanceof Error ? error.message : String(error)
  return {
    id: scenario.id,
    batch,
    title: scenario.title,
    prompt,
    model,
    provider: 'deepseek',
    gateway,
    session_id: sessionId,
    status: 'failed',
    final_answer: '',
    output_dir: join(batchDir, 'outputs', scenario.outputDir),
    files: [],
    artifact_kind: scenario.artifactKind,
    usage: {
      input_tokens: null,
      output_tokens: null,
      cache_hit_tokens: null,
      cache_miss_tokens: null,
      total_tokens: null,
      reporting_status: 'not_reported'
    },
    timing: {
      wall_ms: 0,
      visible_feedback_ms: null,
      first_event_ms: null,
      first_token_ms: null,
      final_ms: null,
      silent_gaps_ms: []
    },
    approvals: [],
    tools: [],
    skill_events: [],
    mcp_events: [],
    layout: { issues: [] },
    layout_snapshot: null,
    screenshots: [],
    protocol_file: join(batchDir, 'events', `${scenario.id}.ndjson`),
    dom_file: join(batchDir, 'dom', `${scenario.id}.json`),
    cleanup: null,
    defects: ['scenario runner exception prevented complete evidence collection'],
    repair_attempts: [],
    error: message
  }
}

const scriptDir = dirname(fileURLToPath(import.meta.url))
const defaultArtifactRoot = resolve(scriptDir, '..', '..', '..', 'artifacts')
const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
const artifactRoot = resolve(
  process.argv.find((arg) => arg.startsWith('--artifacts='))?.slice('--artifacts='.length) ??
    join(defaultArtifactRoot, `rxycode-gui-real-e2e-${timestamp}`)
)
const only = new Set((process.argv.find((arg) => arg.startsWith('--only='))?.slice('--only='.length) ?? '').split(',').filter(Boolean))
const batchArg = (process.argv.find((arg) => arg.startsWith('--batch='))?.slice('--batch='.length) ?? 'both').toUpperCase()
const batches: Batch[] = batchArg === 'A' || batchArg === 'B' ? [batchArg as Batch] : ['A', 'B']
const selected = realBusinessScenarios.filter((scenario) => only.size === 0 || only.has(scenario.id))
const prompts = buildBatchPrompts()

function parseProtocol(lines: string[]): ProtocolMessage[] {
  return lines.flatMap((line) => {
    try { return [JSON.parse(line) as ProtocolMessage] } catch { return [] }
  })
}

function countKnownApproval(messages: ProtocolMessage[]): string[] {
  return messages.filter((message) => String(message.method ?? '').includes('approval'))
    .map((message) => String(message.method))
}

function protocolUsage(messages: ProtocolMessage[]): UsageSummary {
  const samples: UsageSample[] = messages
    .filter((message) => message.method === 'event/token_usage' || message.method === 'event/final')
    .map((message) => {
      const params = message.params ?? {}
      const input = typeof params.input_tokens === 'number' ? params.input_tokens : null
      const hit = typeof params.cache_hit_tokens === 'number' ? params.cache_hit_tokens : null
      const miss = typeof params.cache_miss_tokens === 'number'
        ? params.cache_miss_tokens
        : input !== null && hit !== null ? Math.max(0, input - hit) : null
      return {
        input_tokens: input,
        output_tokens: typeof params.output_tokens === 'number' ? params.output_tokens : null,
        cache_hit_tokens: hit,
        cache_miss_tokens: miss,
        reporting_status: params.reporting_status === 'reported' || params.reporting_status === 'partial'
          ? params.reporting_status
          : input !== null || hit !== null ? 'partial' : 'not_reported'
      }
    })
  return aggregateUsage(samples.length > 1 ? [samples.at(-1)!] : samples)
}

function getGateway(messages: ProtocolMessage[]): string {
  // JSON-RPC responses do not repeat the request method. Identify the model
  // catalog response by its result shape rather than looking for a missing
  // `method` field.
  const model = messages.findLast((message) => Array.isArray(message.result?.models))?.result
  const entry = model?.models?.find((item: any) => item.id === 'deepseek/deepseek-v4-flash')
  return typeof entry?.base_url === 'string' ? entry.base_url.replace(/\/$/, '') : ''
}

function getOfficialModelEntry(messages: ProtocolMessage[]): Record<string, any> | null {
  const model = messages.findLast((message) => Array.isArray(message.result?.models))?.result
  const entry = model?.models?.find((item: any) => item.id === 'deepseek/deepseek-v4-flash')
  return entry !== null && typeof entry === 'object' ? entry as Record<string, any> : null
}

function eventTiming(messages: ProtocolMessage[], startedAt: number, sessionId: string): RealBusinessResult['timing'] {
  const events = messages.filter((message) =>
    typeof message.__at_ms === 'number' &&
    Number(message.__at_ms) >= startedAt &&
    String(message.params?.session_id ?? '') === sessionId &&
    isMeaningfulProtocolEvent(message)
  )
  const eventTimes = events.map((message) => Number(message.__at_ms) - startedAt)
  const firstEvent = events.find((message) => String(message.method ?? '').startsWith('event/'))
  const firstToken = events.find((message) => {
    const method = String(message.method ?? '').toLowerCase()
    // Progress, tool summaries and reasoning snapshots are visible events but
    // are not the first answer token.  Measure the first actual assistant
    // message delta so the GUI performance gate cannot report 0ms merely
    // because the appserver announced "Analyzing your request".
    return method === 'event/message_delta'
  })
  const final = events.findLast((message) => message.method === 'event/final')
  const gaps: number[] = []
  for (let index = 1; index < eventTimes.length; index += 1) {
    const gap = eventTimes[index]! - eventTimes[index - 1]!
    if (gap > 10_000) gaps.push(gap)
  }
  const timing: RealBusinessResult['timing'] = {
    wall_ms: Math.max(0, Date.now() - startedAt),
    visible_feedback_ms: null,
    first_event_ms: firstEvent?.__at_ms === undefined ? null : Math.max(0, Number(firstEvent.__at_ms) - startedAt),
    first_token_ms: firstToken?.__at_ms === undefined ? null : Math.max(0, Number(firstToken.__at_ms) - startedAt),
    final_ms: final?.__at_ms === undefined ? null : Math.max(0, Number(final.__at_ms) - startedAt),
    silent_gaps_ms: gaps
  }
  return timing
}

function copyTree(source: string, target: string): string[] {
  const files: string[] = []
  if (!existsSync(source)) return files
  mkdirSync(target, { recursive: true })
  for (const entry of readdirSync(source, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name === '.git' || entry.name === 'target') continue
    const from = join(source, entry.name)
    const to = join(target, entry.name)
    if (entry.isDirectory()) files.push(...copyTree(from, to))
    else {
      cpSync(from, to)
      files.push(relative(target, to))
    }
  }
  return files
}

function listFiles(root: string): string[] {
  const output: string[] = []
  if (!existsSync(root)) return output
  const walk = (directory: string): void => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      if (entry.name === 'node_modules' || entry.name === '.git' || entry.name === 'target') continue
      const path = join(directory, entry.name)
      if (entry.isDirectory()) walk(path)
      else output.push(relative(root, path))
    }
  }
  walk(root)
  return output.sort()
}

async function selectOfficialModelInSettings(harness: DesktopCdpHarness): Promise<void> {
  const modelId = 'deepseek/deepseek-v4-flash'
  await harness.waitForSelector('[data-testid="open-settings"]', 60_000)
  await harness.evaluate('document.querySelector("[data-testid=\\"open-settings\\"]")?.click()')
  await harness.waitForSelector('[data-testid="settings-dialog"]', 10_000)
  await harness.evaluate('document.querySelector("[data-tab=\\"model\\"]")?.click()')
  await waitFor(
    async () => await harness.evaluate<boolean>(`Boolean(document.querySelector('[data-testid="model-row"][data-model-id=${JSON.stringify(modelId)}]'))`) ? true : null,
    60_000,
    'official DeepSeek model in GUI model center'
  )
  const alreadyActive = await harness.evaluate<boolean>(`Boolean(document.querySelector('[data-testid="model-row"][data-model-id=${JSON.stringify(modelId)}].active'))`)
  if (!alreadyActive) {
    await harness.evaluate(`document.querySelector('[data-testid="model-row"][data-model-id=${JSON.stringify(modelId)}] [data-testid="model-activate"]')?.click()`)
    await waitFor(
      async () => await harness.evaluate<boolean>(`(() => {
        const dialog = document.querySelector('[data-testid="settings-dialog"]')
        const row = document.querySelector('[data-testid="model-row"][data-model-id=${JSON.stringify(modelId)}]')
        return dialog === null || row?.classList.contains('active')
      })()`) ? true : null,
      45_000,
      'activate official DeepSeek model in GUI'
    )
  }
  // Selecting the global default closes the settings page when there is no
  // active task. Close it explicitly as well so the next click is measured
  // from the normal task surface.
  await harness.evaluate('document.querySelector("[data-testid=\\"settings-dialog\\"] .settings-close")?.click()')
  await waitFor(async () => await harness.evaluate<boolean>('!Boolean(document.querySelector("[data-testid=\\"settings-dialog\\"]"))') ? true : null, 5_000, 'close model center after GUI selection')
}

async function createSession(harness: DesktopCdpHarness): Promise<string> {
  await waitFor(async () => {
    const state = await harness.evaluate<{ ready: boolean; status: string; error: string; button: string }>(`(() => {
      const button = document.querySelector('[data-testid="new-session"]');
      const status = document.querySelector('.connection-status')?.textContent?.trim() ?? 'unknown';
      const error = document.querySelector('.error-banner')?.textContent?.trim() ?? '';
      return {
        ready: button instanceof HTMLButtonElement && !button.disabled,
        status,
        error,
        button: button instanceof HTMLButtonElement ? String(button.disabled) : 'missing'
      };
    })()`)
    if (state.error !== '' || /crashed|stopped/i.test(state.status)) {
      throw new Error(`appserver was not ready for a new task (status=${state.status}, button=${state.button}, error=${state.error || 'none'})`)
    }
    return state.ready ? true : null
  }, 60_000, 'appserver protocol ready for new task')
  const previous = await harness.evaluate<number>('document.querySelectorAll(".session-item").length')
  await harness.evaluate(`(() => {
    const button = document.querySelector('[data-testid="new-session"]');
    if (!(button instanceof HTMLButtonElement) || button.disabled) throw new Error('new task button is not enabled after protocol readiness');
    button.click();
  })()`)
  await waitFor(async () => {
    const count = await harness.evaluate<number>('document.querySelectorAll(".session-item").length')
    return count > previous ? true : null
  }, 30_000, 'create real business task')
  return harness.evaluate<string>('document.querySelector(".session-item.active .session-id")?.textContent?.trim() ?? ""')
}

async function assertOfficialModel(harness: DesktopCdpHarness): Promise<{ model: string; gateway: string }> {
  const modelId = 'deepseek/deepseek-v4-flash'
  await harness.waitForSelector('[data-testid="composer-model"]', 60_000)
  await waitFor(async () => await harness.evaluate<boolean>(`Boolean(document.querySelector('[data-testid="composer-model"] option[value=${JSON.stringify(modelId)}]'))`) ? true : null, 60_000, 'official DeepSeek model option')
  await waitFor(async () => await harness.evaluate<boolean>(`document.querySelector('[data-testid="composer-model"]')?.value === ${JSON.stringify(modelId)}`) ? true : null, 45_000, 'apply official DeepSeek model in GUI')
  const lines = parseProtocol(await harness.evaluate<string[]>('window.__rxyRealProtocol ?? []'))
  const entry = getOfficialModelEntry(lines)
  const gateway = getGateway(lines)
  if (entry?.provider_id !== 'deepseek' || gateway !== 'https://api.deepseek.com/v1') {
    throw new Error(`official DeepSeek selection did not resolve to deepseek/https://api.deepseek.com/v1 (provider=${String(entry?.provider_id ?? 'missing')}, gateway=${gateway || 'missing'})`)
  }
  return { model: modelId, gateway }
}

async function setPermission(harness: DesktopCdpHarness, mode: 'auto_edit' | 'full_auto'): Promise<void> {
  await harness.waitForSelector('[data-testid="composer-permission-mode"]', 10_000)
  await harness.evaluate(`(() => {
    const select = document.querySelector('[data-testid="composer-permission-mode"]');
    if (!(select instanceof HTMLSelectElement)) throw new Error('permission selector missing');
    select.value = ${JSON.stringify(mode)};
    select.dispatchEvent(new Event('change', { bubbles: true }));
  })()`)
  if (mode === 'full_auto') {
    await waitFor(async () => (await harness.has('#full-auto-title')) ? true : null, 5_000, 'full access confirmation')
    await harness.evaluate('document.querySelector(".danger-action")?.click()')
  }
  await waitFor(async () => await harness.evaluate<boolean>(`document.querySelector('[data-testid="composer-permission-mode"]')?.value === ${JSON.stringify(mode)}`) ? true : null, 5_000, `permission mode ${mode}`)
}

async function submitPrompt(
  harness: DesktopCdpHarness,
  prompt: string,
  sessionId: string,
  timeoutMs: number,
  screenshotsDir: string,
  approvals: string[]
): Promise<{ finalCount: number; beforeFinalCount: number; visibleFeedbackMs: number; sentAt: number }> {
  const stopAndDrain = async (): Promise<void> => {
    await harness.evaluate('document.querySelector("[data-testid=\\"composer-stop\\"]")?.click()')
    try {
      await waitFor(async () => await harness.evaluate<boolean>(`(() => {
        const state = document.querySelector('[data-testid="session-${sessionId}"] .session-state')?.className ?? '';
        const terminal = /state-(failed|cancelled|timed_out|succeeded)/.test(state);
        const pending = document.querySelector('[data-testid="diagnostics-pending-rpc"]')?.textContent ?? '';
        return terminal && !/pending[^0-9]*[1-9]/i.test(pending);
      })()`) ? true : null, 10_000, 'GUI stop and RPC drain')
    } catch {
      // Cleanup still records pending RPCs and fails the run if the GUI stop
      // contract did not drain. Do not hide that defect by waiting forever.
    }
  }
  await waitFor(async () => await harness.evaluate<boolean>('!document.querySelector("[data-testid=\\"composer-input\\"]")?.disabled') ? true : null, 10_000, 'composer ready')
  const beforeFinalCount = await harness.evaluate<number>('document.querySelectorAll("[data-testid=\\"final-answer\\"]").length')
  const sentAt = Date.now()
  await harness.typePrompt(prompt)
  await harness.pressKey('Enter')
  await waitFor(async () => (await harness.has('[data-testid="running-indicator"]') || await harness.has('[data-testid^="timeline-tool-"]')) ? true : null, 5_000, 'visible task feedback')
  const visibleFeedbackMs = Date.now() - sentAt
  let finalCount = await harness.evaluate<number>('document.querySelectorAll("[data-testid=\\"final-answer\\"]").length')
  const deadline = Date.now() + timeoutMs
  let approvalStateStartedAt: number | null = null
  let queuedStateStartedAt: number | null = null
  while (Date.now() < deadline) {
    if (await harness.has('.approval-dialog .approve')) {
      const path = await harness.screenshot(join(screenshotsDir, `approval-${approvals.length + 1}.png`))
      approvals.push(`approved via Desktop dialog; screenshot=${path}`)
      await harness.evaluate('document.querySelector(".approval-dialog .approve")?.click()')
      try {
        await waitFor(async () => !(await harness.has('.approval-dialog .approve')) ? true : null, 5_000, 'approval decision closes dialog')
      } catch (caught) {
        await stopAndDrain()
        throw new Error(`approval decision did not close the dialog: ${caught instanceof Error ? caught.message : String(caught)}`)
      }
    }
    finalCount = await harness.evaluate<number>('document.querySelectorAll("[data-testid=\\"final-answer\\"]").length')
    const state = await harness.evaluate<string | null>(`(() => {
      const node = document.querySelector('[data-testid="session-${sessionId}"] .session-state');
      const value = node?.className ?? '';
      return value.match(/state-(queued|running|approval|succeeded|failed|cancelled|timed_out)/)?.[1] ?? null;
    })()`)
    if (state !== null && !['queued', 'running', 'approval'].includes(state)) return { finalCount, beforeFinalCount, visibleFeedbackMs, sentAt }
    if (state === 'approval') {
      approvalStateStartedAt ??= Date.now()
      if (Date.now() - approvalStateStartedAt > 15_000) {
        await stopAndDrain()
        throw new Error('approval state remained active without a visible decision dialog')
      }
    } else {
      approvalStateStartedAt = null
    }
    if (state === 'queued') {
      queuedStateStartedAt ??= Date.now()
      if (Date.now() - queuedStateStartedAt > 30_000) {
        await stopAndDrain()
        throw new Error('task remained queued for more than 30s after submission')
      }
    } else {
      queuedStateStartedAt = null
    }
    if (state === 'running') {
      const firstModelActivityAt = await harness.evaluate<number | null>(`(() => {
        const lines = Array.isArray(window.__rxyRealProtocol) ? window.__rxyRealProtocol : [];
        const activity = new Set(['event/message_delta', 'event/tool_begin', 'event/tool_end', 'event/progress', 'event/plan', 'event/step', 'event/recovery_started', 'event/recovery_attempt']);
        for (const line of lines) {
          try {
            const message = JSON.parse(String(line));
            if (activity.has(String(message.method)) &&
              String(message.params?.session_id ?? '') === ${JSON.stringify(sessionId)} &&
              !(String(message.method) === 'event/progress' && /waiting for model response|build in progress|正在等待模型响应/i.test(String(message.params?.text ?? ''))) &&
              typeof message.__at_ms === 'number' && message.__at_ms >= ${sentAt}) return message.__at_ms;
          } catch {}
        }
        return null;
      })()`)
      if (firstModelActivityAt === null && Date.now() - sentAt > 30_000) {
        await stopAndDrain()
        throw new Error(`first model activity exceeded 30s (${Date.now() - sentAt}ms); stopped through GUI`)
      }
      const lastVisibleEventAt = await harness.evaluate<number>(`(() => {
        const lines = Array.isArray(window.__rxyRealProtocol) ? window.__rxyRealProtocol : [];
        const visible = new Set(['event/message_delta', 'event/tool_begin', 'event/tool_end', 'event/progress', 'event/plan', 'event/step', 'event/error', 'event/final', 'event/recovery_started', 'event/recovery_attempt', 'event/recovery_resolved', 'event/recovery_exhausted']);
        for (let index = lines.length - 1; index >= 0; index -= 1) {
          try {
            const message = JSON.parse(String(lines[index]));
            if (visible.has(String(message.method)) &&
              String(message.params?.session_id ?? '') === ${JSON.stringify(sessionId)} &&
              typeof message.__at_ms === 'number' &&
              message.__at_ms >= ${sentAt} &&
              !(String(message.method) === 'event/progress' && /waiting for model response|build in progress|\u6b63\u5728\u7b49\u5f85\u6a21\u578b\u54cd\u5e94/i.test(String(message.params?.text ?? '')))) return message.__at_ms;
          } catch {}
        }
        return ${sentAt};
      })()`)
      const silentForMs = Date.now() - lastVisibleEventAt
      if (silentForMs > 30_000) {
        await stopAndDrain()
        throw new Error(`visible task event silent for ${silentForMs}ms; stopped through GUI`)
      }
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 500))
  }
  await stopAndDrain()
  throw new Error(`task timed out after ${timeoutMs}ms; stopped through GUI`)
}

async function startStaticServer(root: string): Promise<{ process: ChildProcess; port: number }> {
  const source = `const http=require('node:http'),fs=require('node:fs'),path=require('node:path');const root=${JSON.stringify(root)};const s=http.createServer((q,r)=>{const p=path.join(root,q.url==='/'?'index.html':q.url);if(!p.startsWith(root)){r.statusCode=403;return r.end()}fs.createReadStream(p).on('error',()=>{r.statusCode=404;r.end('not found')}).pipe(r)});s.listen(0,'127.0.0.1',()=>console.log('PORT='+s.address().port));`
  const child = spawn(process.execPath, ['-e', source], { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })
  return await new Promise<{ process: ChildProcess; port: number }>((resolveServer, rejectServer) => {
    let buffer = ''
    const timer = setTimeout(() => {
      cleanup()
      rejectServer(new Error('generated web server did not announce a port within 10s'))
    }, 10_000)
    const onData = (chunk: Buffer | string): void => {
      buffer += chunk.toString()
      const match = buffer.match(/PORT=(\d+)/)
      if (match !== null) {
        cleanup()
        resolveServer({ process: child, port: Number(match[1]) })
      }
    }
    const onExit = (code: number | null): void => {
      cleanup()
      rejectServer(new Error(`generated web server exited before ready (code=${code ?? 'unknown'})`))
    }
    const cleanup = (): void => {
      clearTimeout(timer)
      child.stdout?.off('data', onData)
      child.off('exit', onExit)
    }
    child.stdout?.on('data', onData)
    child.once('exit', onExit)
  })
}

function stopProcess(child: ChildProcess): void {
  if (child.pid === undefined) return
  if (process.platform === 'win32') spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' })
  else child.kill('SIGTERM')
}

async function smokeArtifact(scenario: RealBusinessScenario, source: string): Promise<string | null> {
  if (!existsSync(source)) return 'output directory was not created'
  if (scenario.artifactKind === 'web') {
    if (!existsSync(join(source, 'index.html'))) return 'web artifact has no index.html'
    let server: { process: ChildProcess; port: number } | null = null
    try {
      server = await startStaticServer(source)
      const response = await fetch(`http://127.0.0.1:${server.port}/`)
      if (!response.ok) return `generated web server returned ${response.status}`
    } finally {
      if (server !== null) stopProcess(server.process)
    }
  }
  if (scenario.id === 'T05') {
    const javaFiles = listFiles(source).filter((file) => file.endsWith('.java'))
    if (javaFiles.length === 0) return 'Java artifact has no .java source'
    const required = ['README.md', 'DEVELOPMENT.md', 'TEST-REPORT.md']
    const missing = required.filter((file) => !existsSync(join(source, file)))
    if (missing.length > 0) return `Java artifact is incomplete; missing ${missing.join(', ')}`
    const compile = spawnSync('javac', ['-encoding', 'UTF-8', ...javaFiles], { cwd: source, windowsHide: true, encoding: 'utf8', timeout: 120_000 })
    if (compile.status !== 0) return `javac failed: ${String(compile.stderr).slice(0, 1000)}`
  }
  return null
}

function buildArtifactRepairPrompt(scenario: RealBusinessScenario, validationError: string): string {
  return [
    `Artifact repair pass for ${scenario.id}. The previous turn was incomplete and failed validation. Work on the existing ${scenario.outputDir} only.`,
    `Validation failure: ${validationError}`,
    'Inspect every file currently present, identify the root cause, and implement the missing work now. Do not only explain or return a code snippet. Do not claim success without executing the real validation command.',
    scenario.artifactKind === 'web'
      ? 'For a web artifact, create a complete index.html entry point, start a local static server, and exercise the required interactions before reporting success.'
      : scenario.artifactKind === 'java-swing'
        ? 'For the Java artifact, compile every Java source with javac -encoding UTF-8 and launch the real Swing window before reporting success.'
        : 'For this application artifact, run the smallest real build and smoke test available; do not substitute a description for execution.',
    `The required visible checkpoints are: ${scenario.visualCheckpoints.join(', ')}. Verify them if the environment supports them and record unavailable capabilities honestly.`,
    'This is a local artifact repair pass. Do not call or use websearch, webfetch, browsing, internet, or external research. Use only the existing workspace and local tools; this prohibition is intentional even if the validation text contains words such as current, status, or source.',
    'Keep all files inside the requested Txx directory. End with a non-empty Final Answer listing the files changed, commands actually executed, results, and remaining risks.'
  ].join('\n\n')
}

function buildArtifactRepairPromptLegacy(scenario: RealBusinessScenario, validationError: string): string {
  return [
    `Artifact repair pass for ${scenario.id}. Inspect the existing ${scenario.outputDir}, fix the root cause now, and run the real validation command. Do not only explain, do not claim success without executing, and do not write outside this Txx directory. End with a non-empty Final Answer listing files, commands, actual results, and remaining risks.`,
    `这是对 ${scenario.id} 的真实验收修复轮，不是让你解释问题。你刚才生成的 ${scenario.outputDir} 未通过验收：`,
    validationError,
    '请立即检查当前工作区中已经生成的全部文件，定位根因并直接修复。不要只返回代码片段，不要声称“应该可以”。必须实际执行与产物类型对应的验证命令，直到验证命令成功：Java 必须对所有源码使用 javac -encoding UTF-8 编译；网页必须启动并检查入口；其他项目必须运行最小构建/测试。修复后重新检查文件清单、README 和 TEST-REPORT，并在 Final Answer 中明确列出实际修复、实际命令、实际结果和仍未完成的风险。不要写入任何其他 Txx 目录或用户目录。'
  ].join('\n\n')
}

async function runScenario(
  harness: DesktopCdpHarness,
  scenario: RealBusinessScenario,
  batch: Batch,
  prompt: string,
  sessionId: string,
  model: string,
  gateway: string,
  batchDir: string
): Promise<RealBusinessResult> {
  const startedAt = Date.now()
  const approvals: string[] = []
  const screenshots: string[] = []
  const outputSource = join(harness.workspaceDir, scenario.outputDir)
  const outputTarget = join(batchDir, 'outputs', scenario.outputDir)
  let error: string | null = null
  let files: string[] = []
  let finalAnswer = ''
  let status = 'unknown'
  let visibleFeedbackMs: number | null = null
  let promptSentAt: number | null = null
  let runAbortedByWatchdog = false
  let layout: RealBusinessResult['layout'] = { issues: [] }
  let layoutSnapshot: RealBusinessResult['layout_snapshot'] = null
  const repairAttempts: string[] = []
  const screenshotErrors: string[] = []
  const captureEvidence = async (relativePath: string): Promise<void> => {
    try {
      screenshots.push(await harness.screenshot(relativePath))
    } catch (caught) {
      screenshotErrors.push(caught instanceof Error ? caught.message : String(caught))
    }
  }
  try {
    await captureEvidence(join('screenshots', `${scenario.id}-before.png`))
    const sent = await submitPrompt(harness, prompt, sessionId, scenario.timeoutMs, join(batchDir, 'screenshots', scenario.id), approvals)
    promptSentAt = sent.sentAt
    visibleFeedbackMs = sent.visibleFeedbackMs
    const finalCount = sent.finalCount
    const statusAfterSubmit = await harness.evaluate<string>(`(() => document.querySelector('[data-testid="session-${sessionId}"] .session-state')?.className.match(/state-(queued|running|approval|succeeded|failed|cancelled|timed_out)/)?.[1] ?? 'unknown')()`)
    if (statusAfterSubmit === 'succeeded') {
      await waitFor(async () => await harness.evaluate<boolean>(`document.querySelectorAll('[data-testid="final-answer"]').length > ${sent.beforeFinalCount}`) ? true : null, 5_000, `${scenario.id} final answer render`)
    }
    finalAnswer = await harness.evaluate<string>('Array.from(document.querySelectorAll("[data-testid=\\"final-answer\\"] .timeline-prose")).at(-1)?.textContent ?? ""')
    status = await harness.evaluate<string>(`(() => document.querySelector('[data-testid="session-${sessionId}"] .session-state')?.className.match(/state-(queued|running|approval|succeeded|failed|cancelled|timed_out)/)?.[1] ?? 'unknown')()`)
    await captureEvidence(join('screenshots', `${scenario.id}-terminal.png`))
    const snapshot = await harness.evaluate<any>(`(() => {
      // .timeline is inside a scroll container. Its document rect moves when
      // the transcript auto-scrolls and must not be compared with the fixed
      // header as if they were sibling layout boxes.
      const names = ['.chat-area', '[data-testid="composer"]', '.task-header', '.session-panel'];
      const elements = names.flatMap((selector) => { const node = document.querySelector(selector); if (!(node instanceof HTMLElement)) return []; const r = node.getBoundingClientRect(); return [{id: selector, left:r.left, top:r.top, right:r.right, bottom:r.bottom}]; });
      return { viewport:{width:innerWidth,height:innerHeight}, horizontalScroll:document.documentElement.scrollWidth-document.documentElement.clientWidth, elements };
    })()`)
    layoutSnapshot = snapshot
    layout = evaluateLayoutSnapshot(snapshot)
    if (layout.issues.length > 0) error = `layout issues: ${layout.issues.map((issue) => issue.kind).join(', ')}`
  } catch (caught) {
    error = caught instanceof Error ? caught.message : String(caught)
    // A watchdog stop is already a terminal performance finding. Sending
    // artifact-repair prompts after stopping the run would create additional
    // model/tool traffic, approvals, and misleading timing evidence. Repair
    // is only valid after a completed run whose artifact failed validation.
    runAbortedByWatchdog = /stopped through GUI|first model activity|silent interval|remained queued|approval state/i.test(error)
    try {
      status = await harness.evaluate<string>(`(() => document.querySelector('[data-testid="session-${sessionId}"] .session-state')?.className.match(/state-(queued|running|approval|succeeded|failed|cancelled|timed_out)/)?.[1] ?? 'unknown')()`)
      finalAnswer = await harness.evaluate<string>('Array.from(document.querySelectorAll("[data-testid=\\"final-answer\\"] .timeline-prose")).at(-1)?.textContent ?? ""')
    } catch {}
    await captureEvidence(join('screenshots', `${scenario.id}-failure.png`))
  }
  files = copyTree(outputSource, outputTarget)
  let artifactError = await smokeArtifact(scenario, outputSource)
  let terminalIssue = terminalOutcomeIssue(status, finalAnswer)
  let validationError = artifactError ?? terminalIssue
  const initialValidationError = validationError
  // A layout defect is a renderer regression, not an instruction to spend
  // more model/tool rounds repairing an artifact. If an artifact really is
  // invalid as well, allow one bounded repair pass and then revalidate.
  const layoutOnlyFailure = layout.issues.length > 0 && artifactError === null && terminalIssue === null
  const maxRepairAttempts = layoutOnlyFailure ? 0 : 1
  if (validationError !== null) error = error ?? validationError
  for (let attempt = 1; validationError !== null && attempt <= maxRepairAttempts && !runAbortedByWatchdog; attempt += 1) {
    const repairPrompt = buildArtifactRepairPrompt(scenario, validationError)
    repairAttempts.push(repairPrompt)
    try {
      await submitPrompt(
        harness,
        repairPrompt,
        sessionId,
        Math.min(scenario.timeoutMs, 15 * 60 * 1000),
        join(batchDir, 'screenshots', scenario.id, `repair-${attempt}`),
        approvals
      )
      finalAnswer = await harness.evaluate<string>('Array.from(document.querySelectorAll("[data-testid=\\"final-answer\\"] .timeline-prose")).at(-1)?.textContent ?? ""')
      status = await harness.evaluate<string>(`(() => document.querySelector('[data-testid="session-${sessionId}"] .session-state')?.className.match(/state-(queued|running|approval|succeeded|failed|cancelled|timed_out)/)?.[1] ?? 'unknown')()`)
      files = copyTree(outputSource, outputTarget)
      artifactError = await smokeArtifact(scenario, outputSource)
      terminalIssue = terminalOutcomeIssue(status, finalAnswer)
      validationError = artifactError ?? terminalIssue
      if (validationError === null && error === initialValidationError) error = null
    } catch (caught) {
      artifactError = caught instanceof Error ? caught.message : String(caught)
    }
  }
  if (validationError !== null) error = error ?? validationError
  const allLines = await harness.evaluate<string[]>('window.__rxyRealProtocol ?? []')
  const messages = parseProtocol(allLines)
  // The performance clock starts at Enter/submit, not at the optional
  // preflight screenshot. A bounded CDP screenshot timeout must be reported
  // separately and cannot become a false first-token delay.
  const timing = eventTiming(messages, promptSentAt ?? startedAt, sessionId)
  // The prompt submission path records this before any model work. Keep it
  // separate from first-event timing so renderer latency is measurable.
  timing.visible_feedback_ms = visibleFeedbackMs
  const defects: string[] = []
  for (const screenshotError of screenshotErrors) defects.push(`screenshot evidence failed: ${screenshotError}`)
  if (screenshotErrors.length > 0) error = error ?? 'required GUI screenshot evidence was unavailable'
  if (timing.first_event_ms !== null && timing.first_event_ms > 15_000) defects.push(`first event ${timing.first_event_ms}ms exceeds 15s performance gate`)
  if (timing.first_event_ms !== null && timing.first_event_ms > 30_000) defects.push(`first event ${timing.first_event_ms}ms exceeds 30s hard-fail gate`)
  if (timing.first_token_ms !== null && timing.first_token_ms > 8_000) defects.push(`first token ${timing.first_token_ms}ms exceeds 8s target`)
  if (timing.first_token_ms !== null && timing.first_token_ms > 15_000) defects.push(`first token ${timing.first_token_ms}ms exceeds 15s performance gate`)
  if (timing.first_token_ms !== null && timing.first_token_ms > 30_000) defects.push(`first token ${timing.first_token_ms}ms exceeds 30s hard-fail gate`)
  for (const gap of timing.silent_gaps_ms) defects.push(`silent interval ${gap}ms exceeds 10s observation threshold`)
  const tools = await harness.evaluate<string[]>(`Array.from(document.querySelectorAll('[data-testid^="timeline-tool-"] .activity-label')).map((node) => node.textContent ?? '')`)
  const skillEvents = messages.filter((message) => String(message.method ?? '').toLowerCase().includes('skill')).map((message) => String(message.method))
  const mcpEvents = messages.filter((message) => String(message.method ?? '').toLowerCase().includes('mcp')).map((message) => String(message.method))
  if (scenario.id === 'T03' && skillEvents.length === 0 && !tools.some((tool) => tool.toLowerCase().includes('skill'))) defects.push('T03 did not expose a Skill search/load event')
  if (timing.first_token_ms !== null && timing.first_token_ms > 30_000) error = error ?? 'first token exceeded 30s hard-fail gate'
  if (timing.silent_gaps_ms.some((gap) => gap > 30_000)) error = error ?? 'silent interval exceeded 30s hard-fail gate'
  const protocolFile = join(batchDir, 'events', `${scenario.id}.ndjson`)
  mkdirSync(dirname(protocolFile), { recursive: true })
  writeFileSync(protocolFile, allLines.join('\n') + '\n')
  const domFile = join(batchDir, 'dom', `${scenario.id}.json`)
  mkdirSync(dirname(domFile), { recursive: true })
  writeFileSync(domFile, JSON.stringify(await harness.domSnapshot(), null, 2))
  return {
    id: scenario.id,
    batch,
    title: scenario.title,
    prompt,
    model,
    provider: 'deepseek',
    gateway,
    session_id: sessionId,
    status,
    final_answer: finalAnswer,
    output_dir: outputTarget,
    files,
    artifact_kind: scenario.artifactKind,
    usage: protocolUsage(messages),
    timing,
    approvals,
    tools,
    skill_events: skillEvents,
    mcp_events: mcpEvents,
    layout,
    layout_snapshot: layoutSnapshot,
    screenshots,
    protocol_file: protocolFile,
    dom_file: domFile,
    cleanup: null,
    defects,
    repair_attempts: repairAttempts,
    error
  }
}

async function runBatch(batch: Batch): Promise<{ results: RealBusinessResult[]; cleanup: CleanupProof[] }> {
  const batchDir = join(artifactRoot, `batch-${batch}`)
  mkdirSync(batchDir, { recursive: true })
  const results: RealBusinessResult[] = []
  const cleanups: CleanupProof[] = []
  if (batch === 'A') {
    for (const scenario of selected) {
      const harness = new DesktopCdpHarness({
        artifactDir: batchDir,
        fakeAppserver: false,
        workspaceMode: 'empty',
        width: 1440,
        height: 900,
      extraEnv: { RXYCODE_SUBAGENTS: '1', RXYCODE_SUBAGENTS_TASK: '1', RXYCODE_SUBAGENTS_MENTION: '1', RXYCODE_SUBAGENTS_CHILD_TASKS: '1' }
      })
      let cleanup: CleanupProof | null = null
      const prompt = prompts.independent.find((item) => item.id === scenario.id)?.prompt ?? scenario.prompt
      let sessionId = ''
      let selectedModel = { model: 'deepseek/deepseek-v4-flash', gateway: 'https://api.deepseek.com/v1' }
      try {
        await harness.start()
        await harness.evaluate(`(() => { window.__rxyRealProtocol=[]; window.__rxyCdAppserverLogs=[]; window.api.appserver.onLog((line)=>window.__rxyCdAppserverLogs.push(String(line))); window.api.appserver.onLine((line)=>{try{const m=JSON.parse(line);m.__at_ms=Date.now();window.__rxyRealProtocol.push(JSON.stringify(m))}catch{}}) })()`)
        await selectOfficialModelInSettings(harness)
        sessionId = await createSession(harness)
        selectedModel = await assertOfficialModel(harness)
        await setPermission(harness, 'auto_edit')
        try {
          results.push(await runScenario(harness, scenario, batch, prompt, sessionId, selectedModel.model, selectedModel.gateway, batchDir))
        } catch (caught) {
          results.push(failureResult(scenario, batch, prompt, sessionId, selectedModel.model, selectedModel.gateway, batchDir, caught))
        }
      } catch (caught) {
        results.push(failureResult(scenario, batch, prompt, sessionId, selectedModel.model, selectedModel.gateway, batchDir, caught))
      } finally {
        cleanup = await harness.cleanup()
        cleanups.push(cleanup)
        const last = results.at(-1)
        if (last !== undefined && last.id === scenario.id) last.cleanup = cleanup
      }
    }
  } else {
    const harness = new DesktopCdpHarness({
      artifactDir: batchDir,
      fakeAppserver: false,
      workspaceMode: 'empty',
      width: 1440,
      height: 900,
      extraEnv: { RXYCODE_SUBAGENTS: '1', RXYCODE_SUBAGENTS_TASK: '1', RXYCODE_SUBAGENTS_MENTION: '1', RXYCODE_SUBAGENTS_CHILD_TASKS: '1' }
    })
    const defaultModel = 'deepseek/deepseek-v4-flash'
    const defaultGateway = 'https://api.deepseek.com/v1'
    const sequentialPrompts = new Map(prompts.sequential.map((item) => [item.id, item.prompt]))
    let sessionId = ''
    let selectedModel = { model: defaultModel, gateway: defaultGateway }
    try {
      await harness.start()
      await harness.evaluate(`(() => { window.__rxyRealProtocol=[]; window.__rxyCdAppserverLogs=[]; window.api.appserver.onLog((line)=>window.__rxyCdAppserverLogs.push(String(line))); window.api.appserver.onLine((line)=>{try{const m=JSON.parse(line);m.__at_ms=Date.now();window.__rxyRealProtocol.push(JSON.stringify(m))}catch{}}) })()`)
      await selectOfficialModelInSettings(harness)
      sessionId = await createSession(harness)
      selectedModel = await assertOfficialModel(harness)
      await setPermission(harness, 'full_auto')
      for (const scenario of selected) {
        const prompt = sequentialPrompts.get(scenario.id) ?? scenario.prompt
        try {
          results.push(await runScenario(harness, scenario, batch, prompt, sessionId, selectedModel.model, selectedModel.gateway, batchDir))
        } catch (caught) {
          results.push(failureResult(scenario, batch, prompt, sessionId, selectedModel.model, selectedModel.gateway, batchDir, caught))
        }
      }
    } catch (caught) {
      for (const scenario of selected) {
        const prompt = sequentialPrompts.get(scenario.id) ?? scenario.prompt
        results.push(failureResult(scenario, batch, prompt, sessionId, selectedModel.model, selectedModel.gateway, batchDir, caught))
      }
    } finally {
      const cleanup = await harness.cleanup()
      cleanups.push(cleanup)
      for (const result of results) result.cleanup = cleanup
    }
  }
  writeFileSync(join(batchDir, 'results.json'), JSON.stringify({ batch, results, cleanup: cleanups }, null, 2))
  return { results, cleanup: cleanups }
}

async function main(): Promise<void> {
  mkdirSync(artifactRoot, { recursive: true })
  const all: RealBusinessResult[] = []
  const cleanup: CleanupProof[] = []
  for (const batch of batches) {
    const completed = await runBatch(batch)
    all.push(...completed.results)
    cleanup.push(...completed.cleanup)
  }
  writeFileSync(join(artifactRoot, 'real-business-results.json'), JSON.stringify({
    generated_at: new Date().toISOString(),
    repository: repositoryDir,
    model: 'deepseek/deepseek-v4-flash',
    gateway: 'https://api.deepseek.com/v1',
    batches,
    results: all,
    cleanup
  }, null, 2))
  const failures = all.filter((result) => result.error !== null || result.status !== 'succeeded' || (result.cleanup !== null && !result.cleanup.passed))
  console.log(JSON.stringify({ artifactRoot, count: all.length, failures: failures.map((item) => ({ id: item.id, batch: item.batch, error: item.error, status: item.status })) }, null, 2))
  if (failures.length > 0) process.exitCode = 1
}

void main().catch((error) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error))
  process.exitCode = 1
})
