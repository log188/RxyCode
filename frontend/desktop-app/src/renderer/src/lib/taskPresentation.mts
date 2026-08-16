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

const STARTUP_PROGRESS = /starting agent worker|preparing agent worker|正在启动 agent/i

export function isStartupProgress(progress: string | null | undefined): boolean {
  return typeof progress === 'string' && STARTUP_PROGRESS.test(progress)
}

export function modelStatusLabel(input: {
  selectedModelId: string
  loading: boolean
  snapshotLoaded: boolean
}): string {
  if (input.selectedModelId.trim() !== '') return input.selectedModelId
  if (input.loading || !input.snapshotLoaded) return 'Connecting model…'
  return 'Model not connected'
}

export function visibleRunProgress(input: {
  progress?: string | null
  timelineLength: number
}): string | null {
  if (input.progress == null || input.progress === '') return null
  if (isStartupProgress(input.progress) && input.timelineLength > 2) return null
  return input.progress
}

export function shouldShowStartupProgress(input: {
  timelineLength: number
  running: boolean
  progress?: string | null
}): boolean {
  if (!input.running) return false
  return Boolean(input.progress)
}
