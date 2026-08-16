import test from 'node:test'
import assert from 'node:assert/strict'
import { canSubmitComposer, promptWithAttachment, shouldSubmitOnKey } from './composerBehavior.mts'

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

test('composer can send an attachment with an empty prompt', () => {
  assert.equal(canSubmitComposer({ disabled: false, running: false, text: '', hasAttachment: true }), true)
  assert.equal(canSubmitComposer({ disabled: false, running: true, text: '', hasAttachment: true }), false)
})

test('promptWithAttachment asks the agent to read the local file', () => {
  assert.equal(promptWithAttachment('', null), '')
  assert.equal(promptWithAttachment('看这个', { name: 'a.ts', path: 'D:/repo/a.ts' }), '看这个\n\n请先读取附件：D:/repo/a.ts')
  assert.equal(promptWithAttachment('  ', { name: 'notes.md', path: 'notes.md' }), '请先读取附件：notes.md')
})
