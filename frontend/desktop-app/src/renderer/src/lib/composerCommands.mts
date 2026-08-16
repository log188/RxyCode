export type ComposerCommand =
  | { kind: 'slash_plan'; rest: string }
  | { kind: 'slash_build'; rest: string }
  | { kind: 'slash_goal'; rest: string }

export function parseComposerCommand(text: string): ComposerCommand | null {
  const trimmed = text.trim()
  const match = trimmed.match(/^\/(plan|build|goal)(?:\s+([\s\S]*))?$/i)
  if (match === null) return null
  const rest = (match[2] ?? '').trim()
  const name = match[1].toLowerCase()
  if (name === 'plan') return { kind: 'slash_plan', rest }
  if (name === 'build') return { kind: 'slash_build', rest }
  return { kind: 'slash_goal', rest }
}

export function isClearGoalText(text: string): boolean {
  return /^(clear|none|off|清除|取消)$/i.test(text.trim())
}
