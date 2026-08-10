import { test } from 'node:test'
import assert from 'node:assert/strict'
import { isSafeExternalUrl } from './external-url.ts'

test('isSafeExternalUrl accepts http and https absolute URLs', () => {
  assert.equal(isSafeExternalUrl('https://example.com/path?q=1'), true)
  assert.equal(isSafeExternalUrl('http://localhost:3000/'), true)
})

test('isSafeExternalUrl rejects non-http(s) schemes', () => {
  assert.equal(isSafeExternalUrl('javascript:alert(1)'), false)
  assert.equal(isSafeExternalUrl('file:///C:/Windows/win.ini'), false)
  assert.equal(isSafeExternalUrl('data:text/html,<script>1</script>'), false)
  assert.equal(isSafeExternalUrl('about:blank'), false)
})

test('isSafeExternalUrl rejects invalid or relative URLs', () => {
  assert.equal(isSafeExternalUrl(''), false)
  assert.equal(isSafeExternalUrl('/relative/path'), false)
  assert.equal(isSafeExternalUrl('not a url'), false)
})
