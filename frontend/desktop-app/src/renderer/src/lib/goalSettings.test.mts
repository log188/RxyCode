import test from 'node:test'
import assert from 'node:assert/strict'
import { applyGoalToPrompt, loadSessionGoals, saveSessionGoals } from './goalSettings.mts'

test('goal settings round-trip through storage', () => {
  const store = new Map<string, string>()
  const storage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => { store.set(key, value) }
  }
  saveSessionGoals({ s1: ' keep shipping ' }, storage)
  assert.deepEqual(loadSessionGoals(storage), { s1: 'keep shipping' })
})

test('applyGoalToPrompt prefixes a standing goal and leaves empty goals alone', () => {
  assert.equal(applyGoalToPrompt(undefined, '写测试'), '写测试')
  assert.equal(applyGoalToPrompt('  ', '写测试'), '写测试')
  assert.equal(applyGoalToPrompt('先修登录', '写测试'), '持续目标：先修登录\n\n写测试')
})
