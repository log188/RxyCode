#!/usr/bin/env node
/**
 * Phase4-D5 visual acceptance driver.
 *
 * Starts `electron-vite dev` with the in-repo fake appserver and drives
 * the renderer over CDP to capture the settings page states: model tab
 * (BLOCKED_PREREQUISITE panels), API Key tab (blocked), workspace tab
 * default fallback, and a persisted workspace selection after reload.
 *
 * The native directory dialog cannot be driven headlessly, so the saved
 * state is seeded through the same versioned localStorage key the settings
 * page reads/writes, then verified after a full renderer reload (same
 * technique as the Phase4-D4 persisted-rule shot).
 *
 * Usage: node scripts/settings-screenshot.mts [output-dir]
 */
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const appDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const outDir = resolve(process.argv[2] ?? join(appDir, 'docs', 'd5-screenshots'))
const debugPort = 9335
const electronViteBin = join(appDir, 'node_modules', 'electron-vite', 'bin', 'electron-vite.js')
// Fresh profile: previous runs may have persisted workspace settings in the
// default Electron userData dir, which would break the default-state shot.
const profileDir = mkdtempSync(join(tmpdir(), 'rxycode-d5-profile-'))

function delay(ms: number): Promise<void> {
  return new Promise((resolveWait) => setTimeout(resolveWait, ms))
}

async function waitFor<T>(
  probe: () => Promise<T | null>,
  timeoutMs: number,
  label: string
): Promise<T> {
  const deadline = Date.now() + timeoutMs
  let lastValue: T | null = null
  while (Date.now() < deadline) {
    lastValue = await probe()
    if (lastValue !== null) return lastValue
    await delay(250)
  }
  throw new Error(`timeout waiting for ${label}`)
}

async function main(): Promise<void> {
  if (!existsSync(electronViteBin)) {
    console.error(`SCREENSHOT_ABORT electron-vite bin not found: ${electronViteBin}`)
    process.exit(2)
  }
  mkdirSync(outDir, { recursive: true })

  const dev = spawn(
    process.execPath,
    [
      electronViteBin,
      'dev',
      '--',
      `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${profileDir}`
    ],
    {
      cwd: appDir,
      env: {
        ...process.env,
        RXYCODE_DESKTOP_FAKE_APPSERVER: '1',
        RXYCODE_DESKTOP_WIDTH: '900',
        RXYCODE_DESKTOP_HEIGHT: '670'
      },
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe']
    }
  )
  dev.stdout.on('data', (chunk: Buffer | string) => process.stdout.write(chunk))
  dev.stderr.on('data', (chunk: Buffer | string) => process.stderr.write(chunk))

  let ws: WebSocket | null = null
  try {
    const target = await waitFor(
      async () => {
        try {
          const response = await fetch(`http://127.0.0.1:${debugPort}/json/list`)
          const list = (await response.json()) as Array<{
            type: string
            webSocketDebuggerUrl?: string
          }>
          const page = list.find(
            (entry) => entry.type === 'page' && entry.webSocketDebuggerUrl !== undefined
          )
          return page?.webSocketDebuggerUrl ?? null
        } catch {
          return null
        }
      },
      90_000,
      'CDP page target'
    )

    ws = new WebSocket(target)
    await new Promise<void>((resolveOpen, rejectOpen) => {
      ws!.onopen = () => resolveOpen()
      ws!.onerror = () => rejectOpen(new Error('CDP websocket failed to open'))
    })
    console.log(`SCREENSHOT_CDP_TARGET ${target}`)

    let messageId = 0
    const pending = new Map<number, (message: { result: unknown; error?: unknown }) => void>()
    ws.onmessage = (event: MessageEvent) => {
      const message = JSON.parse(String(event.data)) as {
        id?: number
        method?: string
        params?: {
          entry?: { text?: string; level?: string }
          args?: Array<{ value?: unknown }>
          exceptionDetails?: { text?: string }
        }
        result?: unknown
        error?: unknown
      }
      if (message.method === 'Runtime.consoleAPICalled') {
        const values = (message.params?.args ?? []).map((arg) => String(arg.value ?? '')).join(' ')
        console.log(`RENDERER_CONSOLE ${values}`)
      }
      if (message.method === 'Runtime.exceptionThrown') {
        console.error(
          `RENDERER_EXCEPTION ${JSON.stringify(message.params?.exceptionDetails ?? {})}`
        )
      }
      if (message.id !== undefined && pending.has(message.id)) {
        pending.get(message.id)?.(message as { result: unknown; error?: unknown })
        pending.delete(message.id)
      }
    }

    function send(method: string, params: unknown = {}): Promise<unknown> {
      return new Promise((resolveSend, rejectSend) => {
        const id = ++messageId
        pending.set(id, (message) => {
          if (message.error !== undefined) {
            rejectSend(new Error(`CDP ${method} failed: ${JSON.stringify(message.error)}`))
          } else {
            resolveSend(message.result)
          }
        })
        ws?.send(JSON.stringify({ id, method, params }))
      })
    }
    await send('Runtime.enable')

    async function evaluate(expression: string): Promise<unknown> {
      const result = (await send('Runtime.evaluate', {
        expression,
        awaitPromise: true,
        returnByValue: true
      })) as { result?: { value?: unknown }; exceptionDetails?: unknown }
      if (result.exceptionDetails !== undefined) {
        throw new Error(`renderer evaluate failed: ${JSON.stringify(result.exceptionDetails)}`)
      }
      return result.result?.value
    }

    async function capture(file: string): Promise<void> {
      const result = (await send('Page.captureScreenshot', { format: 'png' })) as {
        data?: string
      }
      if (result.data === undefined) throw new Error('captureScreenshot returned no data')
      writeFileSync(file, Buffer.from(result.data, 'base64'))
      console.log(`SCREENSHOT_SAVED ${file}`)
    }

    async function waitForSelector(
      selector: string,
      timeoutMs: number,
      label: string
    ): Promise<void> {
      await waitFor(
        async () =>
          (await evaluate(`Boolean(document.querySelector(${JSON.stringify(selector)}))`)) === true
            ? true
            : null,
        timeoutMs,
        label
      )
    }

    async function waitForSelectorGone(
      selector: string,
      timeoutMs: number,
      label: string
    ): Promise<void> {
      await waitFor(
        async () =>
          (await evaluate(`Boolean(document.querySelector(${JSON.stringify(selector)}))`)) === false
            ? true
            : null,
        timeoutMs,
        label
      )
    }

    async function waitForAnySelector(
      selectors: string[],
      timeoutMs: number,
      label: string
    ): Promise<string> {
      const deadline = Date.now() + timeoutMs
      while (Date.now() < deadline) {
        for (const selector of selectors) {
          const present = (await evaluate(
            `Boolean(document.querySelector(${JSON.stringify(selector)}))`
          )) as boolean
          if (present) return selector
        }
        await delay(250)
      }
      throw new Error(`timeout waiting for ${label}`)
    }

    await waitForSelector(
      '.session-panel .new-session:not(:disabled)',
      60_000,
      'renderer ready with running appserver'
    )
    await delay(500)

    // 01: main window with the settings entry button
    console.log('SCREENSHOT_STEP 01-main-settings-button')
    await capture(join(outDir, '01-main-settings-button.png'))

    // Open settings; the default tab is 模型 with two blocked panels.
    console.log('SCREENSHOT_STEP 02-model-blocked')
    await evaluate(`document.querySelector('.settings-button').click()`)
    await waitForSelector('.settings-page', 10_000, 'settings page opened')
    const modelPanels = (await evaluate(
      `document.querySelectorAll('.settings-panel .blocked-panel').length`
    )) as number
    if (modelPanels !== 2) {
      throw new Error(`expected 2 blocked panels on model tab, got ${modelPanels}`)
    }
    await capture(join(outDir, '02-model-blocked.png'))

    // 03: API Key tab blocked state
    console.log('SCREENSHOT_STEP 03-apikey-blocked')
    await evaluate(`document.querySelector('.settings-tab[data-tab="apikey"]').click()`)
    await delay(200)
    const apiKeyPanels = (await evaluate(
      `document.querySelectorAll('.settings-panel .blocked-panel').length`
    )) as number
    if (apiKeyPanels !== 1) {
      throw new Error(`expected 1 blocked panel on API Key tab, got ${apiKeyPanels}`)
    }
    await capture(join(outDir, '03-apikey-blocked.png'))

    // 04: workspace tab default state (fallback to the appserver repo root)
    console.log('SCREENSHOT_STEP 04-workspace-default')
    await evaluate(`document.querySelector('.settings-tab[data-tab="workspace"]').click()`)
    await waitForSelector('.workspace-card', 10_000, 'workspace card rendered')
    const info = (await evaluate(`window.api.appserver.getInfo()`)) as { repoRoot: string }
    const defaultText = (await evaluate(
      `document.querySelector('.workspace-card').innerText`
    )) as string
    if (!defaultText.includes(info.repoRoot)) {
      throw new Error(`workspace default state did not show repoRoot ${info.repoRoot}`)
    }
    await capture(join(outDir, '04-workspace-default.png'))
    await evaluate(`document.querySelector('.settings-close').click()`)
    await waitForSelectorGone('.settings-page', 10_000, 'settings page closed')

    // 05: persisted workspace selection survives a full renderer reload
    console.log('SCREENSHOT_STEP 05-workspace-saved')
    await evaluate(
      `localStorage.setItem(${JSON.stringify('rxycode.desktop.workspaceSettings.v1')}, ${JSON.stringify(JSON.stringify({ workspaceRoot: 'D:\\\\demo-workspace' }))})`
    )
    await evaluate(`window.__preReloadMarker = true`)
    await send('Page.reload')
    await delay(500)
    const reloaded = (await evaluate(`window.__preReloadMarker === undefined`)) === true
    if (!reloaded) {
      throw new Error('Page.reload did not produce a fresh renderer context')
    }
    const ready = await waitForAnySelector(
      ['.appserver-start:not(:disabled)', '.session-panel .new-session:not(:disabled)'],
      60_000,
      'renderer ready after reload'
    )
    if (ready === '.appserver-start:not(:disabled)') {
      await evaluate(`document.querySelector('.appserver-start').click()`)
    }
    await waitForSelector(
      '.session-panel .new-session:not(:disabled)',
      30_000,
      'appserver running after reload'
    )
    await evaluate(`document.querySelector('.settings-button').click()`)
    await waitForSelector('.settings-page', 10_000, 'settings page reopened')
    await evaluate(`document.querySelector('.settings-tab[data-tab="workspace"]').click()`)
    await waitForSelector('.workspace-card', 10_000, 'workspace card after reload')
    const savedText = (await evaluate(
      `document.querySelector('.workspace-card').innerText`
    )) as string
    if (!savedText.includes('D:\\\\demo-workspace')) {
      throw new Error('persisted workspace selection was not displayed after reload')
    }
    await capture(join(outDir, '05-workspace-saved.png'))

    console.log('SCREENSHOT_D5_OK settings states captured and asserted')
    console.log(`SCREENSHOT_OK ${outDir}`)
  } catch (error) {
    console.error(`SCREENSHOT_FAILED ${String(error)}`)
    process.exitCode = 1
  } finally {
    ws?.close()
    if (process.platform === 'win32') {
      spawnSync('taskkill', ['/pid', String(dev.pid), '/T', '/F'], { stdio: 'ignore' })
    } else {
      try {
        process.kill(dev.pid, 'SIGKILL')
      } catch {
        // already gone
      }
    }
    await delay(500)
    try {
      rmSync(profileDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 })
    } catch {
      // The OS may still hold the profile for a moment after taskkill; the
      // temp dir will be cleaned by the OS eventually.
    }
  }
}

void main()
