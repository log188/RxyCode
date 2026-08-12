export interface UsageMetrics {
  source: 'token_event' | 'final' | 'prompt_result' | 'not_reported'
  input_tokens: number | null
  output_tokens: number | null
  cache_hit_tokens: number | null
  cache_hit_rate: number | null
  reporting_status: 'reported' | 'partial' | 'not_reported'
}

export function emptyUsage(): UsageMetrics {
  return {
    source: 'not_reported',
    input_tokens: null,
    output_tokens: null,
    cache_hit_tokens: null,
    cache_hit_rate: null,
    reporting_status: 'not_reported'
  }
}

function token(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function reportingStatus(values: Array<Record<string, unknown>>): UsageMetrics['reporting_status'] {
  if (values.length === 0) return 'not_reported'
  if (values.every((value) => value.reporting_status === 'reported')) return 'reported'
  const hasAnyValue = values.some((value) =>
    ['input_tokens', 'output_tokens', 'cache_hit_tokens', 'cache_write_tokens']
      .some((key) => token(value[key]) !== null)
  )
  return hasAnyValue ? 'partial' : 'not_reported'
}

function sumKnown(values: Array<Record<string, unknown>>, key: string): number | null {
  const numbers = values.map((value) => token(value[key]))
  return numbers.length > 0 && numbers.every((value): value is number => value !== null)
    ? numbers.reduce((sum, value) => sum + value, 0)
    : null
}

export function extractChildUsage(messages: Array<Record<string, any>>): UsageMetrics {
  const terminal = messages
    .filter((message) => /^child_session\/(completed|failed|cancelled|timed_out)$/.test(String(message.method ?? '')))
    .map((message) => message.params?.payload?.usage)
    .filter((usage): usage is Record<string, unknown> => usage !== null && typeof usage === 'object')
  if (terminal.length === 0) return emptyUsage()
  const input = sumKnown(terminal, 'input_tokens')
  const cache = sumKnown(terminal, 'cache_hit_tokens')
  return {
    source: 'final',
    input_tokens: input,
    output_tokens: sumKnown(terminal, 'output_tokens'),
    cache_hit_tokens: cache,
    cache_hit_rate: input !== null && input > 0 && cache !== null ? cache / input : null,
    reporting_status: reportingStatus(terminal)
  }
}

export function reportedTotals(
  results: Array<Record<string, any>>,
  field: 'usage' | 'child_usage'
): { reported: number; input: number | null; output: number | null; cache: number | null } {
  const metrics = results
    .map((result) => result[field] as UsageMetrics | undefined)
    .filter((value): value is UsageMetrics => value !== undefined && value.reporting_status !== 'not_reported')
  const sum = (key: keyof Pick<UsageMetrics, 'input_tokens' | 'output_tokens' | 'cache_hit_tokens'>): number | null => {
    const values = metrics.map((metric) => metric[key])
    return values.length > 0 && values.every((value): value is number => value !== null)
      ? values.reduce((total, value) => total + value, 0)
      : null
  }
  return { reported: metrics.length, input: sum('input_tokens'), output: sum('output_tokens'), cache: sum('cache_hit_tokens') }
}

export function weightedCacheRate(results: Array<Record<string, any>>): number | null {
  let input = 0
  let cache = 0
  let pairs = 0
  for (const result of results) {
    for (const field of ['usage', 'child_usage'] as const) {
      const metric = result[field] as UsageMetrics | undefined
      if (metric?.input_tokens !== null && metric?.input_tokens !== undefined &&
          metric.cache_hit_tokens !== null && metric.cache_hit_tokens !== undefined && metric.input_tokens > 0) {
        input += metric.input_tokens
        cache += metric.cache_hit_tokens
        pairs += 1
      }
    }
  }
  return pairs > 0 ? cache / input : null
}
