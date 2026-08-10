import { test } from 'node:test'
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { createUpdateManager, type UpdateManager } from './auto-update.ts'
import type { AppUpdater, ProgressInfo, UpdateDownloadedEvent } from 'electron-updater'

class FakeUpdater extends EventEmitter {
  autoDownload = true
  autoInstallOnAppQuit = true
  forceDevUpdateConfig = false
  disableDifferentialDownload = false
  feedUrl: unknown = null
  checkCalls = 0
  downloadCalls = 0
  installCalls = 0
  checkError: Error | null = null
  downloadError: Error | null = null
  emitUpdateNotAvailable = false
  emitUpdateAvailableVersion: string | null = null

  setFeedURL(options: unknown): void {
    this.feedUrl = options
  }

  async checkForUpdates(): Promise<unknown> {
    this.checkCalls += 1
    if (this.checkError !== null) throw this.checkError
    if (this.emitUpdateNotAvailable) this.emit('update-not-available', {})
    if (this.emitUpdateAvailableVersion !== null) {
      this.emit('update-available', { version: this.emitUpdateAvailableVersion })
    }
    return null
  }

  async downloadUpdate(): Promise<unknown> {
    this.downloadCalls += 1
    if (this.downloadError !== null) throw this.downloadError
    return null
  }

  quitAndInstall(): void {
    this.installCalls += 1
  }
}

function createManager(
  overrides: Partial<{
    feedUrl: string | null
    isEnabled: () => boolean
    updater: FakeUpdater
  }> = {}
): { manager: UpdateManager; updater: FakeUpdater } {
  const updater = overrides.updater ?? new FakeUpdater()
  const manager = createUpdateManager({
    updater: updater as unknown as AppUpdater,
    currentVersion: '0.1.0',
    feedUrl: overrides.feedUrl ?? null,
    isEnabled: overrides.isEnabled ?? (() => true)
  })
  return { manager, updater }
}

test('disabled service reports disabled and never touches the updater', async () => {
  const { manager, updater } = createManager({ isEnabled: () => false })
  const snapshot = await manager.check()
  assert.equal(snapshot.status, 'disabled')
  assert.equal(snapshot.currentVersion, '0.1.0')
  assert.match(snapshot.error ?? '', /更新服务不可用/)
  assert.equal(updater.checkCalls, 0)
})

test('manual check with no update available lands on not-available', async () => {
  const { manager, updater } = createManager()
  updater.emitUpdateNotAvailable = true
  const snapshot = await manager.check()
  assert.equal(snapshot.status, 'not-available')
  assert.equal(snapshot.availableVersion, null)
  assert.equal(updater.checkCalls, 1)
})

test('available -> download -> downloaded -> install flow', async () => {
  const { manager, updater } = createManager()
  updater.emitUpdateAvailableVersion = '0.1.1'
  const statuses: string[] = []
  manager.on('status', (snapshot) => statuses.push(snapshot.status))

  const afterCheck = await manager.check()
  assert.equal(afterCheck.status, 'available')
  assert.equal(afterCheck.availableVersion, '0.1.1')

  const downloading = manager.download()
  updater.emit('download-progress', {
    percent: 50,
    transferred: 100,
    total: 200
  } as ProgressInfo)
  updater.emit('update-downloaded', { version: '0.1.1' } as UpdateDownloadedEvent)
  const afterDownload = await downloading
  assert.equal(afterDownload.status, 'downloaded')
  assert.deepEqual(afterDownload.progress, { percent: 50, transferred: 100, total: 200 })
  assert.equal(updater.downloadCalls, 1)

  manager.install()
  assert.equal(updater.installCalls, 1)
  assert.equal(manager.snapshot().status, 'idle')
  assert.ok(statuses.includes('checking'))
  assert.ok(statuses.includes('downloading'))
})

test('check failure keeps the old version untouched and allows re-check', async () => {
  const { manager, updater } = createManager()
  updater.checkError = new Error('feed unreachable')
  const first = await manager.check()
  assert.equal(first.status, 'error')
  assert.match(first.error ?? '', /feed unreachable/)
  assert.equal(first.currentVersion, '0.1.0')

  updater.checkError = null
  updater.emitUpdateNotAvailable = true
  const second = await manager.check()
  assert.equal(second.status, 'not-available')
  assert.equal(second.currentVersion, '0.1.0')
})

test('download failure after available leaves app runnable and re-check works', async () => {
  const { manager, updater } = createManager()
  updater.emitUpdateAvailableVersion = '0.1.1'
  await manager.check()
  updater.downloadError = new Error('download interrupted')
  const afterDownload = await manager.download()
  assert.equal(afterDownload.status, 'error')
  assert.match(afterDownload.error ?? '', /download interrupted/)
  assert.equal(afterDownload.availableVersion, '0.1.1')

  updater.downloadError = null
  updater.emit('update-downloaded', { version: '0.1.1' } as UpdateDownloadedEvent)
  const retry = await manager.download()
  assert.equal(retry.status, 'downloaded')
})

test('feed URL override configures the generic provider', () => {
  const updater = new FakeUpdater()
  createManager({ updater, feedUrl: 'http://127.0.0.1:9999/feed' })
  assert.deepEqual(updater.feedUrl, { provider: 'generic', url: 'http://127.0.0.1:9999/feed' })
})

test('autoDownload and autoInstallOnAppQuit are forced off (manual only)', () => {
  const updater = new FakeUpdater()
  createManager({ updater })
  assert.equal(updater.autoDownload, false)
  assert.equal(updater.autoInstallOnAppQuit, false)
})

test('download and install are no-ops outside their valid states', async () => {
  const { manager, updater } = createManager()
  await manager.download()
  assert.equal(updater.downloadCalls, 0)
  manager.install()
  assert.equal(updater.installCalls, 0)
})
