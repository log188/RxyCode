#!/usr/bin/env node
import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import {
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync
} from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { DesktopCdpHarness, desktopAppDir, repositoryDir, selectRendererTarget, waitFor, type CleanupProof } from './cdp-harness.mts'
import { buildBatchPrompts, buildMissingFileRepairPrompt, parseMissingFilenames, realBusinessScenarios, type RealBusinessScenario } from './real-business-scenarios.mts'
import {
  aggregateUsage,
  evaluateLayoutSnapshot,
  gameEnteredPlayableState,
  isMeaningfulProtocolEvent,
  missingWebDeliverables,
  terminalOutcomeIssue,
  hasInFlightTool,
  type UsageSample,
  type UsageSummary
} from './real-business-metrics.mts'

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
    const previousAt = Number(events[index - 1]!.__at_ms)
    if (gap > 10_000 && !hasInFlightTool(messages, sessionId, previousAt, Number(events[index]!.__at_ms))) gaps.push(gap)
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

function persistPlayProbe(source: string, batchDir: string, scenarioId: string): void {
  const destDir = join(batchDir, 'probes')
  mkdirSync(destDir, { recursive: true })
  for (const name of ['.rxy-play-probe.json', '.rxy-play-probe.png']) {
    const from = join(source, name)
    if (!existsSync(from)) continue
    cpSync(from, join(destDir, `${scenarioId}${name}`))
  }
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

async function stopActiveTask(harness: DesktopCdpHarness, sessionId: string): Promise<void> {
  await harness.evaluate('document.querySelector("[data-testid=\\"composer-stop\\"]")?.click()')
  try {
    await waitFor(async () => await harness.evaluate<boolean>(`(() => {
      const state = document.querySelector('[data-testid="session-${sessionId}"] .session-state')?.className ?? '';
      const terminal = /state-(failed|cancelled|timed_out|succeeded|queued)/.test(state);
      const stop = document.querySelector('[data-testid="composer-stop"]');
      return terminal && stop == null;
    })()`) ? true : null, 15_000, 'GUI stop before next prompt')
  } catch {
    // Cleanup still records pending RPCs. Do not hide a stuck Stop by waiting forever.
  }
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
    await stopActiveTask(harness, sessionId)
    try {
      await waitFor(async () => await harness.evaluate<boolean>(`(() => {
        const pending = document.querySelector('[data-testid="diagnostics-pending-rpc"]')?.textContent ?? '';
        return !/pending[^0-9]*[1-9]/i.test(pending);
      })()`) ? true : null, 10_000, 'GUI stop and RPC drain')
    } catch {
      // Cleanup still records pending RPCs and fails the run if the GUI stop
      // contract did not drain. Do not hide that defect by waiting forever.
    }
  }
  if (await harness.has('[data-testid="composer-stop"]')) {
    await stopAndDrain()
  }
  await waitFor(async () => await harness.evaluate<boolean>('!document.querySelector("[data-testid=\\"composer-input\\"]")?.disabled && !document.querySelector("[data-testid=\\"composer-stop\\"]")') ? true : null, 15_000, 'composer ready')
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
        const begun = new Set();
        const ended = new Set();
        let last = ${sentAt};
        for (const line of lines) {
          try {
            const message = JSON.parse(String(line));
            if (String(message.params?.session_id ?? '') !== ${JSON.stringify(sessionId)}) continue;
            if (typeof message.__at_ms !== 'number' || message.__at_ms < ${sentAt}) continue;
            const method = String(message.method);
            const callId = String(message.params?.call_id ?? '');
            if (method === 'event/tool_begin' && callId) begun.add(callId);
            if (method === 'event/tool_end' && callId) ended.add(callId);
            if (visible.has(method) &&
              !(method === 'event/progress' && /waiting for model response|build in progress|\u6b63\u5728\u7b49\u5f85\u6a21\u578b\u54cd\u5e94/i.test(String(message.params?.text ?? '')))) {
              last = message.__at_ms;
            }
          } catch {}
        }
        for (const callId of begun) {
          if (!ended.has(callId)) return Date.now();
        }
        return last;
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
  const source = [
    "const http=require('node:http'),fs=require('node:fs'),path=require('node:path');",
    `const root=${JSON.stringify(root)};`,
    "const s=http.createServer((q,r)=>{",
    "const rel=decodeURIComponent(String((q.url||'/').split('?')[0])).replace(/^[\\\\/]+/,'')||'index.html';",
    "if(rel.split(/[\\\\/]/).includes('..')){r.statusCode=403;return r.end('forbidden')}",
    "const p=path.resolve(root,rel);",
    "const back=path.relative(path.resolve(root),p);",
    "if(back.startsWith('..')||back.split(/[\\\\/]/).includes('..')){r.statusCode=403;return r.end('forbidden')}",
    "const ext=path.extname(p);",
    "const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json','.png':'image/png','.svg':'image/svg+xml','.csv':'text/csv; charset=utf-8','.md':'text/markdown; charset=utf-8'};",
    "if(types[ext]) r.setHeader('Content-Type', types[ext]);",
    "fs.createReadStream(p).on('error',()=>{r.statusCode=404;r.end('not found')}).pipe(r)",
    "});",
    "s.listen(0,'127.0.0.1',()=>console.log('PORT='+s.address().port));"
  ].join('')
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

function chromeBinary(): string {
  const candidates = [
    process.env.CHROME_PATH,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    join(process.env['PROGRAMFILES(X86)'] ?? '', 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
  ].filter((value): value is string => typeof value === 'string' && value.length > 0)
  const found = candidates.find((path) => existsSync(path))
  if (found === undefined) throw new Error('Chrome/Edge missing for generated page interaction probe')
  return found
}

const gamePlayExpression = `(() => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const readScore = () => {
    const el = document.querySelector('#score, #scoreVal, #hud-score, #hud-coins, #stat-score, [data-testid="score"]');
    const n = Number(String((el && el.textContent) || '0').replace(/[^0-9.-]/g, ''));
    return Number.isFinite(n) ? n : 0;
  };
  const overlayHidden = () => {
    const overlay = document.querySelector('#overlay-start, #screen-start, #screen-menu, #menu-screen, #overlay')
      || document.querySelector('#btn-start, [data-action="newgame"]')?.closest('.overlay, .screen');
    if (!(overlay instanceof HTMLElement)) return false;
    if (overlay.classList.contains('hidden')) return true;
    const style = getComputedStyle(overlay);
    return style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0;
  };
  const readState = () => ({
    score: readScore(),
    state: ((document.querySelector('#stateLabel, #state') || {}).textContent || ''),
    title: document.title,
    overlayHidden: overlayHidden()
  });
  const press = (key) => {
    window.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
    document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
  };
  return (async () => {
    const start = document.querySelector('#startBtn, #btn-start, #start-btn, [data-action="start"], [data-action="newgame"], button.big, button.primary, .btn-primary, #screen-start button.btn:not(.alt)')
      || Array.from(document.querySelectorAll('button')).find((button) => /开始|start|play|new\\s*game/i.test(button.textContent || '') && !/mute|help|pause|resume|restart|静音|帮助|暂停|继续|重新/.test(button.textContent || ''));
    if (start instanceof HTMLElement) {
      start.click();
      press('Enter');
      press(' ');
    }
    let snapshot = readState();
    const canvas = document.querySelector('canvas');
    const canvasPainted = () => {
      if (!(canvas instanceof HTMLCanvasElement)) return false;
      try {
        const ctx = canvas.getContext('2d');
        if (!ctx) return false;
        const sample = ctx.getImageData(0, 0, Math.min(canvas.width, 48), Math.min(canvas.height, 48)).data;
        for (let i = 0; i < sample.length; i += 4) {
          if (sample[i] > 8 || sample[i + 1] > 8 || sample[i + 2] > 8) return true;
        }
      } catch {}
      return false;
    };
    for (let i = 0; i < 24 && snapshot.score <= 0 && !/running|playing|run|\\u8fd0\\u884c|\\u8fdb\\u884c|\\u6e38\\u73a9/i.test(snapshot.state) && !snapshot.overlayHidden && !canvasPainted(); i += 1) {
      press(' '); press('ArrowUp'); press('ArrowRight');
      await sleep(250);
      snapshot = readState();
    }
    const started = snapshot.score > 0 || /running|playing|run|\\u8fd0\\u884c|\\u8fdb\\u884c|\\u6e38\\u73a9/i.test(snapshot.state) || snapshot.overlayHidden === true || canvasPainted();
    if (!started) return { ok: false, reason: start instanceof HTMLElement ? 'did not enter a running/playable state' : 'no start control', ...snapshot };
    for (let i = 0; i < 40 && !/over|end|fail|\\u7ed3\\u675f|\\u5931\\u8d25/i.test(snapshot.state); i += 1) {
      press(' '); press('ArrowUp'); press('ArrowRight');
      await sleep(250);
      snapshot = readState();
    }
    const restart = document.querySelector('#restartBtn, #btn-restart');
    if (restart instanceof HTMLElement) restart.click(); else press('r');
    await sleep(400);
    return { ok: true, ...snapshot, afterRestart: readState() };
  })();
})()`

const pagePlayExpression = `(() => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  return (async () => {
    const text = ((document.body && document.body.innerText) || '').trim();
    const control = document.querySelector('button, select, input, a[href]');
    if (control instanceof HTMLElement) control.click();
    await sleep(300);
    return { ok: text.length > 40, reason: text.length > 40 ? undefined : 'page has no usable content', title: document.title, textLength: text.length };
  })();
})()`

async function evaluateInChrome(url: string, expression: string, screenshotFile: string): Promise<Record<string, any>> {
  const profileDir = mkdtempSync(join(tmpdir(), 'rxy-chrome-play-'))
  const child = spawn(chromeBinary(), [
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    `--user-data-dir=${profileDir}`,
    '--remote-debugging-port=0',
    url
  ], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })
  let socket: WebSocket | null = null
  try {
    const activePortFile = join(profileDir, 'DevToolsActivePort')
    const debugPort = await waitFor(async () => {
      if (!existsSync(activePortFile)) return null
      const value = Number(readFileSync(activePortFile, 'utf8').split(/\r?\n/)[0])
      return Number.isInteger(value) && value > 0 ? value : null
    }, 20_000, 'Chrome DevToolsActivePort')
    const target = await waitFor(async () => {
      try {
        const pages = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json() as Array<{ type: string; url?: string; webSocketDebuggerUrl?: string }>
        return selectRendererTarget(pages)
      } catch {
        return null
      }
    }, 15_000, 'Chrome page target')
    socket = new WebSocket(target)
    await new Promise<void>((resolveOpen, rejectOpen) => {
      socket!.onopen = () => resolveOpen()
      socket!.onerror = () => rejectOpen(new Error('Chrome CDP websocket failed'))
    })
    let sequence = 0
    const pending = new Map<number, { resolve: (value: any) => void; reject: (error: Error) => void }>()
    socket.onmessage = (event) => {
      const message = JSON.parse(String(event.data)) as { id?: number; error?: unknown; result?: unknown }
      if (message.id === undefined) return
      const entry = pending.get(message.id)
      if (entry === undefined) return
      pending.delete(message.id)
      if (message.error !== undefined) entry.reject(new Error(JSON.stringify(message.error)))
      else entry.resolve(message.result)
    }
    const send = (method: string, params: unknown = {}, timeoutMs = 30_000): Promise<any> => new Promise((resolveSend, rejectSend) => {
      const id = ++sequence
      const timer = setTimeout(() => {
        pending.delete(id)
        rejectSend(new Error(`Chrome CDP timed out: ${method}`))
      }, timeoutMs)
      pending.set(id, {
        resolve: (value) => { clearTimeout(timer); resolveSend(value) },
        reject: (error) => { clearTimeout(timer); rejectSend(error) }
      })
      socket!.send(JSON.stringify({ id, method, params }))
    })
    await send('Runtime.enable')
    await send('Page.enable')
    await send('Page.navigate', { url })
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 800))
    const evaluated = await send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
      userGesture: true
    }, 35_000)
    if (evaluated.exceptionDetails !== undefined) {
      throw new Error(evaluated.exceptionDetails.text ?? 'page expression threw')
    }
    try {
      const image = await send('Page.captureScreenshot', { format: 'png' }, 10_000)
      if (typeof image.data === 'string') writeFileSync(screenshotFile, Buffer.from(image.data, 'base64'))
    } catch {}
    return evaluated.result?.value ?? {}
  } finally {
    try { socket?.close() } catch {}
    stopProcess(child)
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 400))
    try {
      rmSync(profileDir, { recursive: true, force: true })
    } catch {
      // Chrome may keep the profile directory locked on Windows. Probe
      // success must not depend on deleting that scratch directory.
    }
  }
}

async function playGeneratedWebPage(source: string, port: number, mode: 'game' | 'page' = 'game'): Promise<string | null> {
  const screenshotFile = join(source, '.rxy-play-probe.png')
  try {
    const parsed = await evaluateInChrome(
      `http://127.0.0.1:${port}/`,
      mode === 'page' ? pagePlayExpression : gamePlayExpression,
      screenshotFile
    ) as { ok?: boolean; score?: number; state?: string; reason?: string; overlayHidden?: boolean }
    writeFileSync(join(source, '.rxy-play-probe.json'), JSON.stringify(parsed, null, 2))
    if (parsed.ok !== true) {
      return `generated page is not playable: ${parsed.reason ?? 'unknown'} (state=${String(parsed.state ?? '')}, score=${String(parsed.score ?? 0)})`
    }
    if (mode === 'game' && !gameEnteredPlayableState(String(parsed.state ?? ''), Number(parsed.score ?? 0)) && parsed.overlayHidden !== true && Number(parsed.score ?? 0) <= 0) {
      return `generated page did not enter a running/playable state (state=${String(parsed.state ?? '')}, score=${String(parsed.score ?? 0)})`
    }
    return null
  } catch (caught) {
    const message = caught instanceof Error ? caught.message : String(caught)
    writeFileSync(join(source, '.rxy-play-probe.json'), JSON.stringify({ error: message }, null, 2))
    return `generated page interaction probe failed: ${message}`
  }
}

async function smokeArtifact(scenario: RealBusinessScenario, source: string): Promise<string | null> {
  if (!existsSync(source)) return 'output directory was not created'
  if (scenario.artifactKind === 'web') {
    const missing = missingWebDeliverables(listFiles(source))
    if (missing.length > 0) return `web artifact is incomplete; missing ${missing.join(', ')}`
    let server: { process: ChildProcess; port: number } | null = null
    try {
      server = await startStaticServer(source)
      const response = await fetch(`http://127.0.0.1:${server.port}/`)
      if (!response.ok) return `generated web server returned ${response.status}`
      if (scenario.id === 'T01' || scenario.id === 'T02') {
        const playError = await playGeneratedWebPage(source, server.port, 'game')
        if (playError !== null) return playError
      } else {
        const playError = await playGeneratedWebPage(source, server.port, 'page')
        if (playError !== null) return playError
      }
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
    const mainFile = javaFiles.find((file) => /public\s+static\s+void\s+main\s*\(/.test(readFileSync(join(source, file), 'utf8')))
    if (mainFile === undefined) return 'Java artifact has no main(String[]) entry point'
    const mainSource = readFileSync(join(source, mainFile), 'utf8')
    const pkg = mainSource.match(/^\s*package\s+([A-Za-z0-9_.]+)\s*;/m)
    const simple = mainFile.replace(/\\/g, '/').split('/').pop()!.replace(/\.java$/, '')
    const mainClass = pkg !== null ? `${pkg[1]}.${simple}` : simple
    const launched = spawn('java', ['-cp', source, mainClass], { cwd: source, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })
    try {
      await new Promise((resolve) => setTimeout(resolve, 2500))
      if (launched.exitCode !== null) {
        return `Swing process exited immediately with ${launched.exitCode}: ${String(launched.stderr?.read?.() ?? '')}`.slice(0, 500)
      }
    } finally {
      stopProcess(launched)
    }
  }
  return null
}

function buildArtifactRepairPrompt(scenario: RealBusinessScenario, validationError: string): string {
  return [
    `Artifact repair pass for ${scenario.id}. The previous turn was incomplete and failed validation. Work on the existing ${scenario.outputDir} only.`,
    `Validation failure: ${validationError}`,
    'Inspect every file currently present, identify the root cause, and implement the missing work now. Do not only explain or return a code snippet. Do not claim success without executing the real validation command.',
    `If the validation failure names missing files, call the write tool now with filePath inside ${scenario.outputDir} for each missing file. A table or Final Answer that lists the filename is not sufficient.`,
    scenario.artifactKind === 'web'
      ? 'For a web artifact, create a complete index.html entry point plus README.md and TEST-REPORT.md, start a local static server, and actually play the page. Fix JavaScript syntax/runtime errors so Start enters a running state, score can increase, collision or game-over can occur, and restart works. Do not claim success if the page stays on a menu or throws Uncaught SyntaxError.'
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
  files = copyTree(outputSource, outputTarget)
  persistPlayProbe(outputSource, batchDir, scenario.id)
  let terminalIssue = terminalOutcomeIssue(status, finalAnswer)
  let validationError = artifactError ?? terminalIssue
  const initialValidationError = validationError
  // A layout defect is a renderer regression, not an instruction to spend
  // more model/tool rounds repairing an artifact. If an artifact really is
  // invalid as well, allow one bounded repair pass and then revalidate.
  const layoutOnlyFailure = layout.issues.length > 0 && artifactError === null && terminalIssue === null
  const missingDocs = /missing /i.test(artifactError ?? '')
  const maxRepairAttempts = layoutOnlyFailure ? 0 : missingDocs ? 2 : 1
  if (validationError !== null) error = error ?? validationError
  for (let attempt = 1; validationError !== null && attempt <= maxRepairAttempts && !runAbortedByWatchdog; attempt += 1) {
    const missingFiles = parseMissingFilenames(validationError)
    const repairPrompt = missingFiles.length > 0
      ? buildMissingFileRepairPrompt(scenario.outputDir, missingFiles)
      : buildArtifactRepairPrompt(scenario, validationError)
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
      files = copyTree(outputSource, outputTarget)
      persistPlayProbe(outputSource, batchDir, scenario.id)
      terminalIssue = terminalOutcomeIssue(status, finalAnswer)
      validationError = artifactError ?? terminalIssue
      error = validationError
    } catch (caught) {
      artifactError = caught instanceof Error ? caught.message : String(caught)
    }
  }
  if (validationError !== null) error = validationError
  else if (layout.issues.length > 0) error = `layout issues: ${layout.issues.map((issue) => issue.kind).join(', ')}`
  else error = null
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
