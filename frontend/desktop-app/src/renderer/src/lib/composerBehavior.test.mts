import test from 'node:test'
import assert from 'node:assert/strict'
import { canSubmitComposer, shouldSubmitOnKey } from './composerBehavior.mts'

test('composer sends a non-empty prompt from Enter but preserves Shift+Enter', () => {
  assert.equal(canSubmitComposer({ disabled: false, running: false, text: ' inspect ' }), true)
  assert.equal(shouldSubmitOnKey({ key: 'Enter', shiftKey: false, running: false }), true)
  assert.equal(shouldSubmitOnKey({ key: 'Enter', shiftKey: true, running: false }), false)
})

test('composer never sends while disabled or running', () => {
  assert.equal(canSubmitComposer({ disabled: true, running: false, text: 'x' }), false)
  assert.equal(canSubmitComposer({ disabled: false, running: true, text: 'x' }), false)
  assert.equal(canSubmitComposer({ disabled: false, running: false, text: '   ' }), false)
  assert.equal(shouldSubmitOnKey({ key: 'Enter', shiftKey: false, running: true }), false)
})
