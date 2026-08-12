#!/usr/bin/env node
/**
 * Phase4-D3 visual acceptance driver.
 *
 * Starts `electron-vite dev` with the in-repo fake appserver and a
 * remote debugging port, drives the renderer over CDP to produce the
 * five required states (empty, normal, loading, error, narrow), and
 * captures PNG screenshots for vision review.
 *
 * Usage: node scripts/screenshot.mts [output-dir]
 */
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const appDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const outDir = resolve(process.argv[2] ?? join(appDir, 'docs', 'd3-screenshots'))
const debugPort = 9333
const electronViteBin = join(appDir, 'node_modules', 'electron-vite', 'bin', 'electron-vite.js')

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
    [electronViteBin, 'dev', '--', `--remote-debugging-port=${debugPort}`],
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
      if (message.method === 'Log.entryAdded') {
        console.log(
          `RENDERER_LOG ${message.params?.entry?.level ?? ''} ${message.params?.entry?.text ?? ''}`
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
    await send('Log.enable')

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
      const layout = (await evaluate(`JSON.stringify({
        innerHeight,
        composer: document.querySelector('.composer')
          ? (() => {
              const r = document.querySelector('.composer').getBoundingClientRect();
              return { top: Math.round(r.top), bottom: Math.round(r.bottom), height: Math.round(r.height) };
            })()
          : null,
        chatArea: (() => {
          const el = document.querySelector('.chat-area');
          if (!el) return null;
          return { scrollTop: el.scrollTop, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight };
        })(),
        banner: document.querySelector('.error-banner')
          ? document.querySelector('.error-banner').getBoundingClientRect().top
          : null,
        commandLayout: ['.main-layout', '.session-panel', '.task-main', '.task-inspector'].map((selector) => {
          const el = document.querySelector(selector);
          const r = el ? el.getBoundingClientRect() : null;
          return { selector, display: el ? getComputedStyle(el).display : 'missing', gridColumn: el ? getComputedStyle(el).gridColumn : '', rect: r ? { left: Math.round(r.left), width: Math.round(r.width), top: Math.round(r.top), height: Math.round(r.height) } : null };
        })
      })`)) as string
      console.log(`SCREENSHOT_LAYOUT ${layout}`)
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

    await waitForSelector(
      '.session-panel .new-session:not(:disabled)',
      60_000,
      'renderer ready with running appserver'
    )
    await delay(500)
    await capture(join(outDir, '01-empty.png'))

    // Explicitly exercise both semantic theme branches; system theme alone
    // is not evidence that the user-selectable light/dark tokens work.
    async function setTheme(mode: 'light' | 'dark'): Promise<void> {
      await evaluate(`(() => {
        const button = Array.from(document.querySelectorAll('.theme-picker button'))
          .find((item) => item.textContent?.trim() === ${JSON.stringify(mode)});
        if (!(button instanceof HTMLButtonElement)) throw new Error('theme button not found');
        button.click();
      })()`)
      await delay(100)
    }

    await setTheme('light')
    await capture(join(outDir, '06-light-empty.png'))
    await setTheme('dark')
    await capture(join(outDir, '07-dark-empty.png'))

    await evaluate(`document.querySelector('.new-session').click()`)
    await waitForSelector('.session-item', 20_000, 'session created')
    await waitForSelector('.composer textarea:not(:disabled)', 20_000, 'composer enabled')

    await setPrompt('tool demo')
    await evaluate(`document.querySelector('.send').click()`)
    await waitForSelector('body:not(:has(.running-indicator))', 30_000, 'tool demo finished')
    await delay(500)
    await capture(join(outDir, '02-normal.png'))

    await setPrompt('slow demo')
    await evaluate(`document.querySelector('.send').click()`)
    await waitForSelector('.stop', 10_000, 'stop button while streaming')
    await waitForSelector('.tool-card.running', 10_000, 'running tool card')
    await delay(500)
    await capture(join(outDir, '03-loading.png'))
    await evaluate(`document.querySelector('.stop').click()`)
    await waitForSelector('body:not(:has(.running-indicator))', 20_000, 'run stopped')

    await setPrompt('fail demo')
    await evaluate(`document.querySelector('.send').click()`)
    await waitForSelector('.message.error, .error-banner', 20_000, 'error state visible')
    await delay(400)
    await capture(join(outDir, '04-error.png'))

    await send('Emulation.setDeviceMetricsOverride', {
      width: 480,
      height: 670,
      deviceScaleFactor: 1,
      mobile: false
    })
    await delay(600)
    await capture(join(outDir, '05-narrow.png'))
    const narrowTaskWidth = await evaluate(
      `Math.round(document.querySelector('.task-main')?.getBoundingClientRect().width ?? 0)`
    )
    if (typeof narrowTaskWidth !== 'number' || narrowTaskWidth < 300) {
      throw new Error(`narrow task column is unusable: ${String(narrowTaskWidth)}px`)
    }

    console.log(`SCREENSHOT_OK ${outDir}`)
  } catch (error) {
    console.error(`SCREENSHOT_FAILED ${String(error)}`)
    try {
      const diagnosis = (await evaluate(
        `JSON.stringify({
          body: document.body ? document.body.innerText.slice(0, 800) : 'NO_BODY',
          api: typeof window.api,
          appserver: typeof window.api?.appserver
        })`
      )) as string
      console.error(`SCREENSHOT_DIAG ${diagnosis}`)
    } catch {
      // diagnostics are best-effort
    }
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
  }
}

void main()
