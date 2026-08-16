import test from 'node:test'
import assert from 'node:assert/strict'
import { isClearGoalText, parseComposerCommand } from './composerCommands.mts'

test('parseComposerCommand recognizes /plan /build /goal', () => {
  assert.deepEqual(parseComposerCommand('/plan'), { kind: 'slash_plan', rest: '' })
  assert.deepEqual(parseComposerCommand('/plan 做 1+1'), { kind: 'slash_plan', rest: '做 1+1' })
  assert.deepEqual(parseComposerCommand('/build'), { kind: 'slash_build', rest: '' })
  assert.deepEqual(parseComposerCommand('/goal 先把登录做完'), { kind: 'slash_goal', rest: '先把登录做完' })
  assert.equal(parseComposerCommand('普通输入'), null)
})

test('isClearGoalText accepts clear aliases', () => {
  assert.equal(isClearGoalText('clear'), true)
  assert.equal(isClearGoalText('清除'), true)
  assert.equal(isClearGoalText('keep going'), false)
})
