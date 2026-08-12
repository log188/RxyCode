import assert from 'node:assert/strict'
import test from 'node:test'
import { extractChildUsage, reportedTotals, weightedCacheRate } from './desktop-cd-usage.mts'

test('child usage preserves unknown token fields instead of converting them to zero', () => {
  const usage = extractChildUsage([
    { method: 'child_session/completed', params: { payload: { usage: { input_tokens: 12, output_tokens: null, cache_hit_tokens: null } } } },
    { method: 'child_session/completed', params: { payload: { usage: { input_tokens: null, output_tokens: 4, cache_hit_tokens: 1 } } } }
  ])
  assert.equal(usage.input_tokens, null)
  assert.equal(usage.output_tokens, null)
  assert.equal(usage.cache_hit_tokens, null)
  assert.equal(usage.reporting_status, 'partial')
})

test('reported totals never sum partial fields as if they were zero', () => {
  const results = [
    { usage: { reporting_status: 'partial', input_tokens: 10, output_tokens: null, cache_hit_tokens: 2 } },
    { usage: { reporting_status: 'reported', input_tokens: 20, output_tokens: 5, cache_hit_tokens: 4 } }
  ]
  assert.deepEqual(reportedTotals(results, 'usage'), { reported: 2, input: 30, output: null, cache: 6 })
  assert.equal(weightedCacheRate(results), 6 / 30)
})
