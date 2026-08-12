import assert from 'node:assert/strict'
import test from 'node:test'
import { selectRendererTarget } from './cdp-harness.mts'

test('CDP harness ignores devtools targets and chooses the renderer page', () => {
  assert.equal(selectRendererTarget([
    { type: 'page', url: 'devtools://devtools/bundled/inspector.html', webSocketDebuggerUrl: 'ws://devtools' },
    { type: 'page', url: 'file:///renderer/index.html', webSocketDebuggerUrl: 'ws://renderer' }
  ]), 'ws://renderer')
})

test('CDP harness returns null when no page target is available', () => {
  assert.equal(selectRendererTarget([{ type: 'browser', webSocketDebuggerUrl: 'ws://browser' }]), null)
})
