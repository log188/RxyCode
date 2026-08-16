export type AgentRunMode = 'plan' | 'build'

export interface PlanDocument {
  title: string
  summary: string
  steps: string[]
  raw: string
}

const HINT_RE = /\r?\n---\r?\n\*\*(?:下一步|Next)\*\*[\s\S]*$/

export function stripPlanHint(text: string): string {
  return text.replace(HINT_RE, '').trim()
}

function section(body: string, names: string[]): string {
  for (const name of names) {
    const match = body.match(new RegExp(`(?:^|\\n)##\\s+${name}\\s*\\n([\\s\\S]*?)(?=\\n##\\s+|$)`, 'i'))
    if (match?.[1] !== undefined) return match[1].trim()
  }
  return ''
}

function numberedSteps(block: string): string[] {
  return block
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*(?:\d+[.)]|[-*])\s+/, '').trim())
    .filter((line) => line.length > 0)
}

export function parsePlanDocument(text: string): PlanDocument {
  const raw = stripPlanHint(text)
  const titleMatch = raw.match(/^#\s+(.+)$/m)
  const title = (titleMatch?.[1] ?? '').trim() || '计划'
  const summary = section(raw, ['Summary', '摘要', '概述']) || (
    titleMatch === null
      ? raw.split(/\n##\s+/)[0]?.trim() ?? raw
      : raw.replace(/^#\s+.+$/m, '').replace(/^##\s+(?:Steps|步骤)[\s\S]*$/m, '').trim()
  )
  const stepsBlock = section(raw, ['Steps', '步骤'])
  const steps = numberedSteps(stepsBlock)
  const fallbackSteps = steps.length > 0
    ? steps
    : numberedSteps(raw.split(/\r?\n/).filter((line) => /^\s*\d+[.)]/.test(line)).join('\n'))
  return {
    title,
    summary: summary.replace(/^##\s+(?:Summary|摘要|概述)\s*/i, '').trim(),
    steps: fallbackSteps,
    raw
  }
}

export function looksLikePlanDocument(text: string): boolean {
  const raw = stripPlanHint(text)
  const hasTitle = /^#\s+.+/m.test(raw)
  const hasSummary = /^##\s+(Summary|摘要|概述)\b/im.test(raw)
  const hasSteps = /^##\s+(Steps|步骤)\b/im.test(raw)
  return (hasTitle && hasSteps) || (hasSummary && hasSteps)
}

export function formatPlanDocument(doc: PlanDocument): string {
  const steps = doc.steps.map((step, index) => `${index + 1}. ${step}`).join('\n')
  return [`# ${doc.title}`, '', '## Summary', doc.summary, '', '## Steps', steps].join('\n').trim()
}

export function buildImplementPrompt(doc: PlanDocument): string {
  return [
    '请严格按照以下计划实施，不要跳步，也不要改写目标。完成一步再进入下一步。',
    '',
    formatPlanDocument(doc)
  ].join('\n')
}

export function buildRevisePrompt(doc: PlanDocument, feedback: string): string {
  return [
    '请根据用户的补充说明，改写上一份计划文档。仍然只输出计划，不要开始实施。',
    '保持 Markdown 结构：# 标题、## Summary、## Steps。',
    '',
    '上一份计划：',
    formatPlanDocument(doc),
    '',
    '需要改进的地方：',
    feedback.trim()
  ].join('\n')
}

export function planModeInstruction(): string {
  return [
    '请只输出计划文档，不要实施、不要写文件。使用下面的 Markdown 结构：',
    '# <短标题>',
    '## Summary',
    '<一段话说明要做什么和约束>',
    '## Steps',
    '1. …',
    '2. …'
  ].join('\n')
}
