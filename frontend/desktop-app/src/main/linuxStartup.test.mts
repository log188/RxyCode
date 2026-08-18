import assert from 'node:assert/strict'
import test from 'node:test'
import { shouldDisableLinuxSandbox } from './linuxStartup.ts'

test('packaged Linux AppImage disables the unsigned chrome-sandbox', () => {
  assert.equal(shouldDisableLinuxSandbox('linux', true), true)
})

test('dev Linux and packaged Windows/mac keep the default sandbox', () => {
  assert.equal(shouldDisableLinuxSandbox('linux', false), false)
  assert.equal(shouldDisableLinuxSandbox('win32', true), false)
  assert.equal(shouldDisableLinuxSandbox('darwin', true), false)
})
