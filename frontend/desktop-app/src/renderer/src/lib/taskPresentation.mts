// Presentation helpers intentionally live outside React so unknown usage
// remains testable and is never silently normalized to zero in the UI.

export function formatTokenCount(value: number | null): string {
  if (value === null) return 'not reported'
  if (Math.abs(value) < 1_000) return String(value)
  return (value / 1_000).toFixed(1) + 'k'
}

export function formatUsageRate(input: {
  inputTokens: number | null
  cacheHitTokens: number | null
}): string {
  if (
    input.inputTokens === null ||
    input.cacheHitTokens === null ||
    input.inputTokens <= 0
  ) {
    return 'not reported'
  }
  return String(Math.round((input.cacheHitTokens / input.inputTokens) * 100)) + '%'
}

export function shouldShowStartupProgress(input: {
  timelineLength: number
  running: boolean
  progress?: string | null
}): boolean {
  if (!input.running) return false
  return Boolean(input.progress)
}
