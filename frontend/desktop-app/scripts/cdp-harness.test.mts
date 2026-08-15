import assert from 'node:assert/strict'
import test from 'node:test'
import { DesktopCdpHarness, electronViteDevArgs, electronViteNodeOptions, selectRendererTarget } from './cdp-harness.mts'

test('CDP harness ignores devtools targets and chooses the renderer page', () => {
  assert.equal(selectRendererTarget([
    { type: 'page', url: 'devtools://devtools/bundled/inspector.html', webSocketDebuggerUrl: 'ws://devtools' },
    { type: 'page', url: 'file:///renderer/index.html', webSocketDebuggerUrl: 'ws://renderer' }
  ]), 'ws://renderer')
})

test('CDP harness returns null when no page target is available', () => {
  assert.equal(selectRendererTarget([{ type: 'browser', webSocketDebuggerUrl: 'ws://browser' }]), null)
})

test('CDP harness asks Vite for an ephemeral renderer port', () => {
  const args = electronViteDevArgs('C:\\temp\\rxycode-profile')
  assert.deepEqual(args.slice(1, 4), ['dev', '--', '--port=0'])
  assert.ok(args.includes('--remote-debugging-port=0'))
})

test('electron-vite node options raise the heap without clobbering an existing cap', () => {
  assert.equal(electronViteNodeOptions(undefined), '--max-old-space-size=8192')
  assert.equal(electronViteNodeOptions(''), '--max-old-space-size=8192')
  assert.equal(electronViteNodeOptions('--enable-source-maps'), '--enable-source-maps --max-old-space-size=8192')
  assert.equal(electronViteNodeOptions('--max-old-space-size=4096'), '--max-old-space-size=4096')
})

test('real artifact harness can use an empty workspace instead of exposing the source tree', () => {
  const options = { artifactDir: 'C:\\artifacts', fakeAppserver: false, workspaceMode: 'empty' as const }
  assert.equal(options.workspaceMode, 'empty')
})

test('responsive CDP coverage uses the requested desktop zoom levels', () => {
  assert.deepEqual([1, 1.25, 1.5].map((factor) => Math.round(factor * 100)), [100, 125, 150])
})

test('CDP requests fail and leave no pending entry when the renderer stops replying', async () => {
  const harness = Object.create(DesktopCdpHarness.prototype) as any
  harness.sequence = 0
  harness.pending = new Map()
  harness.socket = { readyState: 1, send: () => undefined }

  await assert.rejects(
    harness.send('Runtime.evaluate', {}, 5),
    /CDP request timed out after 5ms: Runtime\.evaluate/
  )
  assert.equal(harness.pending.size, 0)
})
