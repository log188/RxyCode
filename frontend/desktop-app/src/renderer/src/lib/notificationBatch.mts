export interface BatchedNotification {
  method: string
  params: unknown
}

export interface NotificationBatcher {
  push: (notification: BatchedNotification) => void
  flush: () => void
  cancel: () => void
}

/**
 * Coalesce high-frequency stream notifications without delaying ordered
 * control-plane events.  The caller can flush synchronously before applying a
 * tool/final/approval event, so batching cannot reorder the task timeline.
 */
export function createNotificationBatcher(
  onFlush: (notifications: BatchedNotification[]) => void,
  intervalMs = 32
): NotificationBatcher {
  let pending: BatchedNotification[] = []
  let timer: ReturnType<typeof setTimeout> | null = null

  const flush = (): void => {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
    if (pending.length === 0) return
    const next = pending
    pending = []
    onFlush(next)
  }

  const schedule = (): void => {
    if (timer !== null) return
    timer = setTimeout(flush, Math.max(1, intervalMs))
  }

  return {
    push(notification) {
      pending.push(notification)
      schedule()
    },
    flush,
    cancel() {
      if (timer !== null) clearTimeout(timer)
      timer = null
      pending = []
    }
  }
}
