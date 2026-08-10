#!/usr/bin/env node
/**
 * Phase4-D4 visual acceptance driver.
 *
 * Starts `electron-vite dev` with the in-repo fake appserver and drives
 * the renderer over CDP to capture the approval modal states:
 * empty rules, normal request, always-allow scope form, persisted rule
 * list, submitting, connection-lost error, plus a persisted-rule
 * auto-approval assertion.
 *
 * Usage: node scripts/approval-screenshot.mts [output-dir]
 */
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const appDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const outDir = resolve(process.argv[2] ?? join(appDir, 'docs', 'd4-screenshots'))
const debugPort = 9334
const electronViteBin = join(appDir, 'node_modules', 'electron-vite', 'bin', 'electron-vite.js')
// Fresh profile: previous runs may have persisted approval rules in the
// default Electron userData dir, which would break the empty-state shot.
const profileDir = mkdtempSync(join(tmpdir(), 'rxycode-d4-profile-'))

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

    async function setPrompt(text: string): Promise<void> {
      await evaluate(`(() => {
        const ta = document.querySelector('.composer textarea');
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLTextAreaElement.prototype,
          'value'
        ).set;
        setter.call(ta, ${JSON.stringify(text)});
        ta.dispatchEvent(new Event('input', { bubbles: true }));
      })()`)
      await delay(200)
    }

    await waitForSelector(
      '.session-panel .new-session:not(:disabled)',
      60_000,
      'renderer ready with running appserver'
    )
    await delay(500)

    // 01: rules manager empty state
    console.log('SCREENSHOT_STEP 01-rules-empty')
    await evaluate(`document.querySelector('.rules-button').click()`)
    await waitForSelector('.rules-dialog .rules-empty', 10_000, 'empty rules state')
    await capture(join(outDir, '01-rules-empty.png'))
    await evaluate(`document.querySelector('.rules-close').click()`)
    await waitForSelectorGone('.rules-dialog', 10_000, 'rules modal closed')

    // 02: normal pending approval request
    console.log('SCREENSHOT_STEP 02-approval-normal')
    await evaluate(`document.querySelector('.new-session').click()`)
    await waitForSelector('.session-item', 20_000, 'session created')
    await waitForSelector('.composer textarea:not(:disabled)', 20_000, 'composer enabled')
    await setPrompt('approval demo')
    await evaluate(`document.querySelector('.send').click()`)
    await waitForSelector('.approval-dialog', 20_000, 'approval modal shown')
    await capture(join(outDir, '02-approval-normal.png'))

    // 03: always-allow scope form
    console.log('SCREENSHOT_STEP 03-always-allow-form')
    await evaluate(`document.querySelector('.always-allow').click()`)
    await waitForSelector('.approval-scope-form', 10_000, 'always-allow scope form')
    await capture(join(outDir, '03-always-allow-form.png'))

    // Save an exact 24h rule; the current run completes and the rule persists.
    console.log('SCREENSHOT_STEP save-rule')
    await evaluate(`document.querySelector('.save-rule').click()`)
    await waitForSelectorGone('.approval-dialog', 20_000, 'approval resolved')
    await waitForSelector('body:not(:has(.running-indicator))', 30_000, 'approval demo finished')

    // 04: persisted rule list
    console.log('SCREENSHOT_STEP 04-rules-list')
    await evaluate(`document.querySelector('.rules-button').click()`)
    await waitForSelector('.rules-dialog .rule-item', 10_000, 'persisted rule listed')
    await capture(join(outDir, '04-rules-list.png'))
    await evaluate(`document.querySelector('.rules-close').click()`)
    await waitForSelectorGone('.rules-dialog', 10_000, 'rules modal closed')

    // 05: submitting state (fake appserver delays 1.2s after a decision)
    console.log('SCREENSHOT_STEP 05-approval-submitting')
    await setPrompt('approval demo')
    await evaluate(`document.querySelector('.send').click()`)
    await waitForSelector('.approval-dialog', 20_000, 'second approval modal shown')
    await evaluate(`document.querySelector('.approve').click()`)
    await delay(300)
    await waitForSelector('.approval-dialog .approval-submitting', 5_000, 'submitting state')
    await capture(join(outDir, '05-approval-submitting.png'))
    await waitForSelectorGone('.approval-dialog', 20_000, 'approval resolved')
    await waitForSelector('body:not(:has(.running-indicator))', 30_000, 'run finished')

    // 06: connection lost while an approval is pending -> error state
    console.log('SCREENSHOT_STEP 06-approval-error')
    await setPrompt('approval demo')
    await evaluate(`document.querySelector('.send').click()`)
    await waitForSelector('.approval-dialog', 20_000, 'third approval modal shown')
    await evaluate(`document.querySelector('.appserver-stop').click()`)
    await waitForSelector('.approval-dialog.error', 15_000, 'approval error state')
    await capture(join(outDir, '06-approval-error.png'))
    await evaluate(`document.querySelector('.approval-dismiss').click()`)
    await waitForSelectorGone('.approval-dialog', 10_000, 'error modal dismissed')

    // Auto-approval: seed a matching persisted rule, reload so the hook
    // loads it, then run a fixed-action approval scenario without the modal.
    console.log('SCREENSHOT_STEP auto-approval')
    const info = (await evaluate(`window.api.appserver.getInfo()`)) as {
      repoRoot: string
    }
    const seedRule = {
      id: 'seed-auto',
      workspaceRoot: info.repoRoot,
      riskLevel: 'WRITE',
      actionScope: 'exact',
      action: 'bash: write approval-auto.txt',
      createdAt: Date.now(),
      expiresAt: Date.now() + 24 * 3600 * 1000
    }
    await evaluate(
      `localStorage.setItem(${JSON.stringify('rxycode.desktop.approvalRules.v1')}, ${JSON.stringify(JSON.stringify([seedRule]))})`
    )
    await evaluate(`window.__preReloadMarker = true`)
    await send('Page.reload')
    await delay(500)
    const reloaded = (await evaluate(`window.__preReloadMarker === undefined`)) === true
    if (!reloaded) {
      throw new Error('Page.reload did not produce a fresh renderer context')
    }
    await waitForSelector('.appserver-start:not(:disabled)', 60_000, 'renderer ready after reload')
    await evaluate(`document.querySelector('.appserver-start').click()`)
    await waitForSelector(
      '.session-panel .new-session:not(:disabled)',
      30_000,
      'appserver running after reload'
    )
    await evaluate(`document.querySelector('.new-session').click()`)
    await waitForSelector('.session-item', 20_000, 'session created after reload')
    await waitForSelector('.composer textarea:not(:disabled)', 20_000, 'composer enabled')
    console.log(
      `SCREENSHOT_DIAG seeded_storage=${JSON.stringify(
        await evaluate(`localStorage.getItem('rxycode.desktop.approvalRules.v1')`)
      )}`
    )
    await evaluate(`(() => {
      window.__approvalSeen = false;
      window.__approvalObserver = new MutationObserver(() => {
        if (document.querySelector('.approval-dialog')) window.__approvalSeen = true;
      });
      window.__approvalObserver.observe(document.body, { childList: true, subtree: true });
    })()`)
    await setPrompt('approval auto')
    await evaluate(`document.querySelector('.send').click()`)
    try {
      await waitForSelector('body:not(:has(.running-indicator))', 30_000, 'auto run finished')
    } catch (error) {
      console.log(
        `SCREENSHOT_DIAG auto_state=${JSON.stringify(
          await evaluate(
            `JSON.stringify({ modal: Boolean(document.querySelector('.approval-dialog')), seen: Boolean(window.__approvalSeen), running: Boolean(document.querySelector('.running-indicator')), text: document.body.innerText.slice(0, 400) })`
          )
        )}`
      )
      throw error
    }
    await delay(400)
    const approvalSeen = (await evaluate('window.__approvalSeen')) === true
    if (approvalSeen) {
      throw new Error('auto-approval rule matched but the approval modal appeared')
    }
    console.log('SCREENSHOT_AUTO_OK persisted rule auto-approved without the modal')

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
