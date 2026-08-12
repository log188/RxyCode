import test from 'node:test'
import assert from 'node:assert/strict'
import {
  DEFAULT_DESKTOP_PREFERENCES,
  loadDesktopPreferences,
  saveDesktopPreferences,
  type DesktopPreferences
} from './desktopPreferences.mts'

function storage(): Storage {
  const values = new Map<string, string>()
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
    clear: () => values.clear(),
    key: (index) => [...values.keys()][index] ?? null,
    get length() { return values.size }
  } as Storage
}

test('desktop preferences default to safe confirm-all and system theme', () => {
  assert.deepEqual(loadDesktopPreferences(storage()), DEFAULT_DESKTOP_PREFERENCES)
})

test('desktop preferences preserve the per-window safety mode and language', () => {
  const target = storage()
  const preferences: DesktopPreferences = {
    permissionMode: 'auto_edit',
    theme: 'light',
    language: 'en-US'
  }
  saveDesktopPreferences(preferences, target)
  assert.deepEqual(loadDesktopPreferences(target), preferences)
})

test('desktop preferences reject malformed or unsafe stored values', () => {
  const target = storage()
  target.setItem('rxycode.desktop.preferences.v1', JSON.stringify({
    permissionMode: 'approve_everything',
    theme: 'neon',
    language: 'fr'
  }))
  assert.deepEqual(loadDesktopPreferences(target), DEFAULT_DESKTOP_PREFERENCES)
})
