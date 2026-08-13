import { test } from 'node:test'
import assert from 'node:assert/strict'
import { formatTokenCount, formatUsageRate, shouldShowStartupProgress } from './taskPresentation.mts'

test('formatTokenCount makes absent usage explicit instead of presenting zero', () => {
  assert.equal(formatTokenCount(null), 'not reported')
  assert.equal(formatTokenCount(0), '0')
  assert.equal(formatTokenCount(12_340), '12.3k')
})

test('formatUsageRate only calculates cache rate from reported positive input', () => {
  assert.equal(formatUsageRate({ inputTokens: 200, cacheHitTokens: 50 }), '25%')
  assert.equal(formatUsageRate({ inputTokens: null, cacheHitTokens: 0 }), 'not reported')
  assert.equal(formatUsageRate({ inputTokens: 0, cacheHitTokens: 0 }), 'not reported')
})

test('empty new-task pages do not keep a stale Preparing Agent worker banner', () => {
  assert.equal(shouldShowStartupProgress({
    timelineLength: 0,
    running: false,
    progress: 'Preparing Agent worker…'
  }), false)
  assert.equal(shouldShowStartupProgress({
    timelineLength: 0,
    running: true,
    progress: 'Preparing Agent worker…'
  }), true)
})
