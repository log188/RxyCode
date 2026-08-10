import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  WORKSPACE_SETTINGS_STORAGE_KEY,
  effectiveWorkspaceRoot,
  loadWorkspaceSettings,
  normalizeWorkspaceRoot,
  saveWorkspaceSettings,
  type StorageLike,
  type WorkspaceSettings
} from './workspaceSettings.mts'

function createFakeStorage(initial: Record<string, string> = {}): {
  data: Record<string, string>
  getItem: StorageLike['getItem']
  setItem: StorageLike['setItem']
} {
  const data: Record<string, string> = { ...initial }
  return {
    data,
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => {
      data[key] = value
    }
  }
}

test('loadWorkspaceSettings returns the default when no value is stored', () => {
  const storage = createFakeStorage()
  assert.deepEqual(loadWorkspaceSettings(storage), { workspaceRoot: null })
})

test('loadWorkspaceSettings ignores malformed JSON and falls back to the default', () => {
  const storage = createFakeStorage({ [WORKSPACE_SETTINGS_STORAGE_KEY]: '{not-json' })
  assert.deepEqual(loadWorkspaceSettings(storage), { workspaceRoot: null })
})

test('loadWorkspaceSettings rejects stored values with a non-string workspaceRoot', () => {
  const storage = createFakeStorage({
    [WORKSPACE_SETTINGS_STORAGE_KEY]: JSON.stringify({ workspaceRoot: 123 })
  })
  assert.deepEqual(loadWorkspaceSettings(storage), { workspaceRoot: null })
})

test('loadWorkspaceSettings reads back a saved workspace root', () => {
  const storage = createFakeStorage({
    [WORKSPACE_SETTINGS_STORAGE_KEY]: JSON.stringify({ workspaceRoot: 'D:\\demo' })
  })
  assert.deepEqual(loadWorkspaceSettings(storage), { workspaceRoot: 'D:\\demo' })
})

test('saveWorkspaceSettings round-trips through loadWorkspaceSettings', () => {
  const storage = createFakeStorage()
  const settings: WorkspaceSettings = { workspaceRoot: 'D:\\round-trip' }
  saveWorkspaceSettings(settings, storage)
  assert.equal(storage.data[WORKSPACE_SETTINGS_STORAGE_KEY], JSON.stringify(settings))
  assert.deepEqual(loadWorkspaceSettings(storage), settings)
})

test('normalizeWorkspaceRoot trims surrounding whitespace', () => {
  assert.equal(normalizeWorkspaceRoot('  D:\\ demo  '), 'D:\\ demo')
})

test('normalizeWorkspaceRoot turns blank values into null', () => {
  assert.equal(normalizeWorkspaceRoot(''), null)
  assert.equal(normalizeWorkspaceRoot('   '), null)
  assert.equal(normalizeWorkspaceRoot(null), null)
})

test('effectiveWorkspaceRoot uses the saved workspace when set', () => {
  const settings: WorkspaceSettings = { workspaceRoot: 'D:\\saved' }
  assert.equal(effectiveWorkspaceRoot(settings, 'D:\\fallback'), 'D:\\saved')
})

test('effectiveWorkspaceRoot falls back to the repo root when nothing is saved', () => {
  const settings: WorkspaceSettings = { workspaceRoot: null }
  assert.equal(effectiveWorkspaceRoot(settings, 'D:\\fallback'), 'D:\\fallback')
})
