import assert from 'node:assert/strict'
import test from 'node:test'
import { formatChildNavigation, resolveChildTarget } from './childNavigation.ts'

const children = [
  { session_id: 'child-a', agent_id: 'explore', status: 'running' },
  { session_id: 'child-b', agent_id: 'reviewer', status: 'completed' },
]

test('child navigation accepts stable session ids and one-based indices', () => {
  assert.equal(resolveChildTarget('child-b', children)?.agent_id, 'reviewer')
  assert.equal(resolveChildTarget('1', children)?.session_id, 'child-a')
  assert.equal(resolveChildTarget('0', children), null)
  assert.equal(resolveChildTarget('missing', children), null)
})

test('child navigation formats status and recent child activity without dumping hidden reasoning', () => {
  const text = formatChildNavigation(children[0]!, [
    { event_name: 'progress', payload: { text: 'Inspect repository' } },
    { event_name: 'completed', payload: { summary: 'Found two files' } },
  ])
  assert.match(text, /@explore · running/)
  assert.match(text, /progress: Inspect repository/)
  assert.doesNotMatch(text, /chain.of.thought/i)
})
