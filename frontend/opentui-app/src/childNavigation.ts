export interface ChildNavigationEntry {
  session_id: string
  parent_session_id?: string | null
  agent_id?: string
  status?: string
}

export function resolveChildTarget(
  target: string,
  children: ChildNavigationEntry[],
): ChildNavigationEntry | null {
  const value = target.trim()
  if (value === '') return null
  const byId = children.find((child) => child.session_id === value)
  if (byId !== undefined) return byId
  const index = Number(value)
  if (!Number.isInteger(index) || index < 1) return null
  return children[index - 1] ?? null
}

export function formatChildNavigation(
  entry: ChildNavigationEntry,
  events: Array<Record<string, unknown>> = [],
): string {
  const agent = entry.agent_id ? `@${entry.agent_id}` : 'child agent'
  const status = entry.status ?? 'unknown'
  const lines = events.slice(-8).map((event) => {
    const name = String(event.event_name ?? event.method ?? 'event')
    const payload = event.payload
    if (typeof payload === 'object' && payload !== null) {
      const record = payload as Record<string, unknown>
      const text = record.text ?? record.summary ?? record.error
      if (text !== undefined) return `- ${name}: ${String(text)}`
    }
    return `- ${name}`
  })
  return [`${agent} · ${status}`, `session: ${entry.session_id}`, ...lines].join('\n')
}
