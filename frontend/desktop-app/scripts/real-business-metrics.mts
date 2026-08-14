import { relative, resolve } from 'node:path'

export interface UsageSample {
  input_tokens: number | null
  output_tokens: number | null
  cache_hit_tokens: number | null
  cache_miss_tokens: number | null
  reporting_status: 'reported' | 'partial' | 'not_reported'
}

export function isMeaningfulProtocolEvent(message: Record<string, any>): boolean {
  const method = String(message.method ?? '')
  if (!method.startsWith('event/') || method === 'event/heartbeat' || method === 'event/server_heartbeat') return false
  if (method !== 'event/progress') return true
  const text = String(message.params?.text ?? '').toLowerCase()
  return !(
    text.includes('waiting for model response') ||
    text.includes('build in progress') ||
    text.includes('\u6b63\u5728\u7b49\u5f85\u6a21\u578b\u54cd\u5e94')
  )
}

export function hasInFlightTool(
  messages: Array<Record<string, any>>,
  sessionId: string,
  atMs: number,
  untilMs?: number
): boolean {
  const open = new Set<string>()
  for (const message of messages) {
    const method = String(message.method ?? '')
    const sid = String(message.params?.session_id ?? '')
    const at = Number(message.__at_ms)
    if (sid !== sessionId || !Number.isFinite(at)) continue
    if (untilMs !== undefined && at >= untilMs) continue
    const callId = String(message.params?.call_id ?? '')
    if (!callId) continue
    if (method === 'event/tool_begin' && at <= atMs) open.add(callId)
    if (method === 'event/tool_end' && at <= atMs) open.delete(callId)
  }
  return open.size > 0
}

export interface UsageSummary {
  input_tokens: number | null
  output_tokens: number | null
  cache_hit_tokens: number | null
  cache_miss_tokens: number | null
  total_tokens: number | null
  reporting_status: UsageSample['reporting_status']
}

function sumKnown(values: Array<number | null>): number | null {
  const known = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  return known.length === 0 ? null : known.reduce((sum, value) => sum + value, 0)
}

export function aggregateUsage(samples: UsageSample[]): UsageSummary {
  const input_tokens = sumKnown(samples.map((sample) => sample.input_tokens))
  const output_tokens = sumKnown(samples.map((sample) => sample.output_tokens))
  const cache_hit_tokens = sumKnown(samples.map((sample) => sample.cache_hit_tokens))
  const cache_miss_tokens = sumKnown(samples.map((sample) => sample.cache_miss_tokens))
  return {
    input_tokens,
    output_tokens,
    cache_hit_tokens,
    cache_miss_tokens,
    total_tokens: input_tokens === null && output_tokens === null ? null : (input_tokens ?? 0) + (output_tokens ?? 0),
    reporting_status: samples.some((sample) => sample.reporting_status === 'not_reported')
      ? samples.some((sample) => sample.reporting_status !== 'not_reported') ? 'partial' : 'not_reported'
      : samples.some((sample) => sample.reporting_status === 'partial') ? 'partial' : 'reported'
  }
}

export function cacheHitRate(summary: UsageSummary): number | null {
  if (summary.input_tokens === null || summary.cache_hit_tokens === null || summary.input_tokens <= 0) return null
  return summary.cache_hit_tokens / summary.input_tokens
}

export function terminalOutcomeIssue(status: string, finalAnswer: string): string | null {
  if (status === 'succeeded' && finalAnswer.trim().length === 0) {
    return 'succeeded task has no non-empty Final Answer'
  }
  return null
}

export const requiredWebDeliverables = ['index.html', 'README.md', 'TEST-REPORT.md'] as const

export function missingWebDeliverables(files: string[]): string[] {
  const names = new Set(files.map((file) => file.replace(/\\/g, '/').split('/').pop() ?? file))
  return requiredWebDeliverables.filter((file) => !names.has(file))
}

export function playProbeUrl(argv: string[]): string | undefined {
  return argv.find((arg) => arg.startsWith('http://') || arg.startsWith('https://'))
}

export function staticFilePath(root: string, requestUrl: string): string | null {
  const rel = decodeURIComponent(String(requestUrl.split('?')[0] ?? '')).replace(/^[/\\]+/, '') || 'index.html'
  if (rel.split(/[/\\]/).includes('..')) return null
  const resolved = resolve(root, rel)
  const back = relative(resolve(root), resolved)
  if (back.startsWith('..') || back.split(/[/\\]/).includes('..')) return null
  return resolved
}

export function parseHudScore(text: string): number {
  const n = Number(String(text).replace(/[^0-9.-]/g, ''))
  return Number.isFinite(n) ? n : 0
}

export function gameEnteredPlayableState(state: string, score: number): boolean {
  if (parseHudScore(String(score)) > 0) return true
  if (Number(score) > 0) return true
  return /running|playing|\brun\b|运行|进行|游玩/i.test(state)
}

export interface LayoutElement {
  id: string
  left: number
  top: number
  right: number
  bottom: number
}

export interface LayoutSnapshot {
  viewport: { width: number; height: number }
  horizontalScroll: number
  elements: LayoutElement[]
}

export interface LayoutIssue {
  kind: 'overlap' | 'clipped' | 'horizontal_scroll' | 'composer_coverage'
  elements: string[]
  detail: string
}

const GEOMETRY_EPSILON = 0.5

function intersects(a: LayoutElement, b: LayoutElement): boolean {
  return a.left < b.right - GEOMETRY_EPSILON && a.right > b.left + GEOMETRY_EPSILON &&
    a.top < b.bottom - GEOMETRY_EPSILON && a.bottom > b.top + GEOMETRY_EPSILON
}

export function evaluateLayoutSnapshot(snapshot: LayoutSnapshot): { issues: LayoutIssue[] } {
  const issues: LayoutIssue[] = []
  if (snapshot.horizontalScroll > 0) {
    issues.push({ kind: 'horizontal_scroll', elements: [], detail: `horizontal scroll=${snapshot.horizontalScroll}` })
  }
  for (const element of snapshot.elements) {
    if (element.left < -GEOMETRY_EPSILON || element.top < -GEOMETRY_EPSILON ||
      element.right > snapshot.viewport.width + GEOMETRY_EPSILON ||
      element.bottom > snapshot.viewport.height + GEOMETRY_EPSILON) {
      issues.push({ kind: 'clipped', elements: [element.id], detail: `${element.id} exceeds viewport` })
    }
  }
  for (let i = 0; i < snapshot.elements.length; i += 1) {
    for (let j = i + 1; j < snapshot.elements.length; j += 1) {
      const a = snapshot.elements[i]!
      const b = snapshot.elements[j]!
      if (intersects(a, b)) {
        issues.push({ kind: 'overlap', elements: [a.id, b.id], detail: `${a.id} intersects ${b.id}` })
        if ((a.id === 'composer' && b.id === 'timeline') || (a.id === 'timeline' && b.id === 'composer')) {
          issues.push({ kind: 'composer_coverage', elements: [a.id, b.id], detail: 'composer covers timeline content' })
        }
      }
    }
  }
  return { issues }
}

export function timelineKinds(items: Array<{ kind: string }>): { valid: boolean; issue: string | null } {
  const kinds = items.map((item) => item.kind)
  const prompt = kinds.indexOf('prompt')
  const final = kinds.lastIndexOf('final')
  const tool = kinds.indexOf('tool')
  const toolResult = kinds.indexOf('tool_result')
  if (prompt < 0 || tool < 0 || toolResult < 0 || final < 0) return { valid: false, issue: 'missing required timeline item' }
  if (!(prompt < tool && tool < toolResult && toolResult < final)) return { valid: false, issue: `non-chronological timeline: ${kinds.join(' > ')}` }
  return { valid: true, issue: null }
}
