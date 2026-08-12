export interface TaskTrashDecision {
  allowed: boolean
  message: string | null
}

export function canTrashTask(activeSessionId: string | null, targetSessionId: string): TaskTrashDecision {
  if (activeSessionId === targetSessionId) {
    return { allowed: false, message: '您正在打开该窗口删不掉' }
  }
  return { allowed: true, message: null }
}

export function isRecoverableConnectionError(message: string): boolean {
  const normalized = message.toLowerCase()
  return normalized.includes('timeout') ||
    normalized.includes('timed out') ||
    normalized.includes('degraded') ||
    normalized.includes('connection') ||
    normalized.includes('pipe')
}
