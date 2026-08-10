import { test } from 'node:test'
import assert from 'node:assert/strict'
import { isAllowedNavigation, type NavigationPolicy } from './navigation.ts'

const appIndexUrl = 'file:///D:/agent-demo/RxyCode-Desktop/out/renderer/index.html'
const devUrl = 'http://localhost:5173/'

function policy(overrides: Partial<NavigationPolicy> = {}): NavigationPolicy {
  return { appIndexUrl, isDev: false, ...overrides }
}

test('allows the exact production index.html URL', () => {
  assert.equal(isAllowedNavigation(appIndexUrl, policy()), true)
})

test('allows the exact dev renderer URL only in dev mode', () => {
  assert.equal(isAllowedNavigation(devUrl, policy({ isDev: true, devUrl })), true)
  assert.equal(isAllowedNavigation(devUrl, policy({ isDev: false, devUrl })), false)
})

test('rejects any other file:// path', () => {
  assert.equal(
    isAllowedNavigation('file:///D:/agent-demo/RxyCode-Desktop/out/renderer/other.html', policy()),
    false
  )
  assert.equal(isAllowedNavigation('file:///C:/Windows/win.ini', policy()), false)
})

test('rejects dev URLs that differ from the renderer URL and non-http schemes', () => {
  assert.equal(
    isAllowedNavigation('http://localhost:5173/other', policy({ isDev: true, devUrl })),
    false
  )
  assert.equal(isAllowedNavigation('javascript:alert(1)', policy({ isDev: true, devUrl })), false)
})
