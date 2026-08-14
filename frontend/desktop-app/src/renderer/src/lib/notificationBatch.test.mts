import assert from 'node:assert/strict'
import test from 'node:test'
import { createNotificationBatcher } from './notificationBatch.mts'

test('notification batcher coalesces stream notifications in arrival order', () => {
  const flushes: string[][] = []
  const batcher = createNotificationBatcher(
    (items) => flushes.push(items.map((item) => String((item.params as { text: string }).text))),
    10_000
  )

  batcher.push({ method: 'event/message_delta', params: { text: 'a' } })
  batcher.push({ method: 'event/message_delta', params: { text: 'b' } })
  assert.deepEqual(flushes, [])
  batcher.flush()
  assert.deepEqual(flushes, [['a', 'b']])
  batcher.cancel()
})

test('notification batcher flushes synchronously before an ordered control event', () => {
  const applied: string[] = []
  const batcher = createNotificationBatcher(
    (items) => applied.push(...items.map((item) => String((item.params as { text: string }).text))),
    10_000
  )

  batcher.push({ method: 'event/message_delta', params: { text: 'before-final' } })
  batcher.flush()
  applied.push('final')
  assert.deepEqual(applied, ['before-final', 'final'])
  batcher.cancel()
})

test('notification batcher does not publish cancelled pending notifications', () => {
  let published = false
  const batcher = createNotificationBatcher(() => { published = true }, 10_000)
  batcher.push({ method: 'event/message_delta', params: { text: 'discard' } })
  batcher.cancel()
  batcher.flush()
  assert.equal(published, false)
})
