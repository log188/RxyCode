import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  classifyModelsListFailure,
  modelsUnavailableCopy
} from './modelAvailability.mts'

test('missing protocol client is a connection problem, not an old appserver', () => {
  assert.equal(classifyModelsListFailure(null, false), 'not-connected')
  const copy = modelsUnavailableCopy('not-connected', 'appserver not connected')
  assert.match(copy.title, /后端未连接/)
  assert.equal(copy.blockedPrerequisite, false)
  assert.doesNotMatch(copy.title, /旧版/)
})

test('JSON-RPC method-not-found keeps the old-appserver diagnosis', () => {
  assert.equal(
    classifyModelsListFailure({ code: -32601, message: 'Method not found' }, true),
    'method-not-found'
  )
  assert.equal(classifyModelsListFailure(new Error('Method not found'), true), 'method-not-found')
  const copy = modelsUnavailableCopy('method-not-found', 'Method not found')
  assert.match(copy.title, /旧版 appserver/)
  assert.equal(copy.blockedPrerequisite, true)
})

test('runtime RPC failures surface the real error instead of BLOCKED_PREREQUISITE', () => {
  assert.equal(
    classifyModelsListFailure(new Error('python.exe failed to start'), true),
    'error'
  )
  const copy = modelsUnavailableCopy('error', 'python.exe failed to start')
  assert.equal(copy.title, '模型管理不可用')
  assert.match(copy.detail, /python\.exe failed to start/)
  assert.equal(copy.blockedPrerequisite, false)
})
