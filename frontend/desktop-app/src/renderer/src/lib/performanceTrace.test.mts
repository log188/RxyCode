import assert from 'node:assert/strict'
import test from 'node:test'
import { PerformanceTrace, PerformanceTraceRegistry } from './performanceTrace.mts'

test('performance trace keeps the first mark for each stage and derives durations', () => {
  let now = 100
  const trace = new PerformanceTrace({ now: () => now })
  trace.startRun('session-1')
  trace.mark('send_click')
  now = 140
  trace.mark('rpc_sent')
  now = 210
  trace.mark('first_token')
  now = 260
  trace.mark('first_token')

  assert.deepEqual(trace.snapshot(), {
    sessionId: 'session-1',
    marks: { send_click: 100, rpc_sent: 140, first_token: 210 },
    durations: { send_click: 0, rpc_sent: 40, first_token: 110 }
  })
})

test('performance registry keeps parallel sessions isolated', () => {
  let now = 0
  const registry = new PerformanceTraceRegistry({ now: () => now })
  registry.startRun('primary-a')
  registry.mark('primary-a', 'send_click')
  now = 20
  registry.startRun('primary-b')
  registry.mark('primary-b', 'send_click')
  now = 50
  registry.mark('primary-a', 'first_token')

  const snapshot = registry.snapshot()
  assert.equal(snapshot.sessions['primary-a']?.durations.first_token, 50)
  assert.equal(snapshot.sessions['primary-b']?.durations.first_token, undefined)
  assert.equal(snapshot.activeSessionId, 'primary-b')
})
