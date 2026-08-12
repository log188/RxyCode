import { test } from 'node:test'
import assert from 'node:assert/strict'
import { canTrashTask, isRecoverableConnectionError } from './taskActions.mts'

test('the open task cannot be moved to recently deleted', () => {
  assert.deepEqual(canTrashTask('open-session', 'open-session'), {
    allowed: false,
    message: '您正在打开该窗口删不掉'
  })
})

test('a different task can be moved to recently deleted', () => {
  assert.deepEqual(canTrashTask('open-session', 'other-session'), {
    allowed: true,
    message: null
  })
})

test('appserver timeout and degraded errors are eligible for reconnect', () => {
  assert.equal(isRecoverableConnectionError('RPC timeout: session/prompt'), true)
  assert.equal(isRecoverableConnectionError('appserver degraded: job stalled'), true)
  assert.equal(isRecoverableConnectionError('invalid permission_mode'), false)
})
