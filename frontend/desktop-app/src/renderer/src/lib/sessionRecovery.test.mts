import { test } from 'node:test'
import assert from 'node:assert/strict'
import { isNonFatalChildRecoveryError } from './sessionRecovery.mts'

test('child session RPC timeouts are non-fatal and must not look like a dead appserver', () => {
  assert.equal(
    isNonFatalChildRecoveryError('RPC timeout: child_sessions/events'),
    true
  )
  assert.equal(
    isNonFatalChildRecoveryError('Method not found'),
    true
  )
  assert.equal(
    isNonFatalChildRecoveryError('appserver process exited'),
    false
  )
})
