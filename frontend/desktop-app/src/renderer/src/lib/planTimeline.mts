import type { TimelineItem } from './conversationStore.mts'
import { looksLikePlanDocument, parsePlanDocument, type PlanDocument } from './planDocument.mts'

export function latestPlanFromTimeline(
  timeline: TimelineItem[]
): { itemId: string; document: PlanDocument } | null {
  for (let index = timeline.length - 1; index >= 0; index -= 1) {
    const item = timeline[index]
    if (item === undefined) continue
    if (item.kind === 'final_answer' && looksLikePlanDocument(item.text)) {
      return { itemId: item.id, document: parsePlanDocument(item.text) }
    }
  }
  return null
}

export function hasLaterPlanFinal(timeline: TimelineItem[], itemId: string): boolean {
  const start = timeline.findIndex((item) => item.id === itemId)
  if (start < 0) return false
  return timeline.slice(start + 1).some(
    (item) => item.kind === 'final_answer' && looksLikePlanDocument(item.text)
  )
}
