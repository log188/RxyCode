import test from 'node:test'
import assert from 'node:assert/strict'
import type { TimelineItem } from './conversationStore.mts'
import { hasLaterPlanFinal, latestPlanFromTimeline } from './planTimeline.mts'

const PLAN = `# 标题

## Summary
概述。

## Steps
1. 第一步
`

test('latestPlanFromTimeline returns the newest structured plan', () => {
  const timeline: TimelineItem[] = [
    { kind: 'user_prompt', id: 'u1', text: 'plan it' },
    { kind: 'final_answer', id: 'p1', text: PLAN, runId: 'r1', status: 'succeeded' },
    { kind: 'final_answer', id: 'p2', text: PLAN.replace('标题', '修订版'), runId: 'r2', status: 'succeeded' }
  ]
  const latest = latestPlanFromTimeline(timeline)
  assert.equal(latest?.itemId, 'p2')
  assert.equal(latest?.document.title, '修订版')
  assert.equal(hasLaterPlanFinal(timeline, 'p1'), true)
  assert.equal(hasLaterPlanFinal(timeline, 'p2'), false)
})

test('latestPlanFromTimeline ignores ordinary finals', () => {
  const timeline: TimelineItem[] = [
    { kind: 'final_answer', id: 'done', text: '已完成。', runId: 'r3', status: 'succeeded' }
  ]
  assert.equal(latestPlanFromTimeline(timeline), null)
})
