const STORAGE_KEY = 'rxycode.desktop.sessionGoals'

export type SessionGoals = Record<string, string>

export function loadSessionGoals(storage: Pick<Storage, 'getItem'>): SessionGoals {
  try {
    const raw = storage.getItem(STORAGE_KEY)
    if (raw === null || raw === '') return {}
    const parsed = JSON.parse(raw) as unknown
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const out: SessionGoals = {}
    for (const [key, value] of Object.entries(parsed)) {
      if (typeof value === 'string' && value.trim() !== '') out[key] = value.trim()
    }
    return out
  } catch {
    return {}
  }
}

export function saveSessionGoals(goals: SessionGoals, storage: Pick<Storage, 'setItem'>): void {
  const trimmed: SessionGoals = {}
  for (const [key, value] of Object.entries(goals)) {
    const text = value.trim()
    if (text !== '') trimmed[key] = text
  }
  storage.setItem(STORAGE_KEY, JSON.stringify(trimmed))
}

export function applyGoalToPrompt(goal: string | undefined, text: string): string {
  const trimmedGoal = goal?.trim() ?? ''
  if (trimmedGoal === '') return text
  return `持续目标：${trimmedGoal}\n\n${text}`
}
