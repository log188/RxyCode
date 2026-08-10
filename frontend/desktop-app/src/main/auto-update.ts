/**
 * Auto-update manager (Phase4-D7).
 *
 * Thin, testable wrapper around electron-updater. Updates are always
 * user-initiated from the settings page "更新与诊断" tab: checking is
 * manual, downloading only happens after the user confirms, and install
 * only runs on an explicit restart action. There is no startup check and
 * a failed check/download never touches the running app (the old version
 * keeps running untouched).
 *
 * The manager is framework-agnostic: the electron-updater instance is
 * injected so unit tests can drive the state machine with a fake.
 */
import { EventEmitter } from 'node:events'
import type { AppUpdater, ProgressInfo } from 'electron-updater'

export type UpdateStatus =
  | 'disabled'
  | 'idle'
  | 'checking'
  | 'available'
  | 'not-available'
  | 'downloading'
  | 'downloaded'
  | 'error'

export interface UpdateProgress {
  percent: number
  transferred: number
  total: number
}

export interface UpdateStatusSnapshot {
  status: UpdateStatus
  currentVersion: string
  availableVersion: string | null
  error: string | null
  progress: UpdateProgress | null
}

export interface UpdateManagerOptions {
  /** electron-updater instance (injected for tests). */
  updater: AppUpdater
  /** Version of the running app. */
  currentVersion: string
  /** Generic feed URL override (RXYCODE_UPDATE_FEED_URL). */
  feedUrl?: string | null
  /** Whether the update service is available (packaged app / dev feed override). */
  isEnabled: () => boolean
}

export interface UpdateManager {
  on(event: 'status', listener: (snapshot: UpdateStatusSnapshot) => void): UpdateManager
  snapshot(): UpdateStatusSnapshot
  check(): Promise<UpdateStatusSnapshot>
  download(): Promise<UpdateStatusSnapshot>
  install(): void
}

export function createUpdateManager(options: UpdateManagerOptions): UpdateManager {
  const { updater } = options
  const emitter = new EventEmitter()
  let status: UpdateStatus = 'idle'
  let availableVersion: string | null = null
  let errorMessage: string | null = null
  let progress: UpdateProgress | null = null

  const snapshot = (): UpdateStatusSnapshot => ({
    status,
    currentVersion: options.currentVersion,
    availableVersion,
    error: errorMessage,
    progress
  })

  const setStatus = (next: UpdateStatus): void => {
    if (next !== 'error' && next !== 'disabled') errorMessage = null
    status = next
    emitter.emit('status', snapshot())
  }

  // No forced downloads and no install-on-quit: everything happens on an
  // explicit user action from the settings page (Phase4-D7 requirement).
  updater.autoDownload = false
  updater.autoInstallOnAppQuit = false

  const feedUrl = options.feedUrl
  if (feedUrl !== undefined && feedUrl !== null && feedUrl !== '') {
    updater.setFeedURL({ provider: 'generic', url: feedUrl })
  }

  updater.on('update-not-available', () => setStatus('not-available'))
  updater.on('update-available', (info) => {
    availableVersion = info.version
    setStatus('available')
  })
  updater.on('download-progress', (info: ProgressInfo) => {
    progress = {
      percent: info.percent,
      transferred: info.transferred,
      total: info.total
    }
    emitter.emit('status', snapshot())
  })
  updater.on('update-downloaded', () => setStatus('downloaded'))
  updater.on('error', (error: Error) => {
    errorMessage = error.message
    setStatus('error')
  })

  const manager: UpdateManager = {
    on: (event, listener) => {
      emitter.on(event, listener)
      return manager
    },
    snapshot,
    async check() {
      if (!options.isEnabled()) {
        errorMessage =
          '更新服务不可用：仅打包构建支持检查更新（开发模式可设置 RXYCODE_UPDATE_FEED_URL 指向本地 feed）'
        setStatus('disabled')
        return snapshot()
      }
      if (status === 'checking' || status === 'downloading') return snapshot()
      setStatus('checking')
      try {
        await updater.checkForUpdates()
      } catch (error) {
        errorMessage = error instanceof Error ? error.message : String(error)
        setStatus('error')
      }
      return snapshot()
    },
    async download() {
      if (status !== 'available') return snapshot()
      progress = null
      setStatus('downloading')
      try {
        await updater.downloadUpdate()
      } catch (error) {
        errorMessage = error instanceof Error ? error.message : String(error)
        setStatus('error')
      }
      return snapshot()
    },
    install() {
      if (status !== 'downloaded') return
      setStatus('idle')
      updater.quitAndInstall()
    }
  }
  return manager
}
