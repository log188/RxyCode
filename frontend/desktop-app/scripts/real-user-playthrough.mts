#!/usr/bin/env node
/**
 * Real-user playthrough of accepted T01–T09 artifacts.
 * Opens each product, operates it like a person, and saves a screenshot per step.
 * This is not the shallow one-click probe used during generation.
 */
import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http'
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync
} from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, extname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { selectRendererTarget, waitFor } from './cdp-harness.mts'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const repoDir = resolve(scriptDir, '..', '..', '..')
const artifactsRoot = resolve(repoDir, '..', '..', 'artifacts')
const outRoot = resolve(
  process.argv.find((arg) => arg.startsWith('--artifacts='))?.slice('--artifacts='.length)
    ?? join(artifactsRoot, 'rxycode-gui-real-user-playthrough-2026-08-16')
)

type StepResult = Record<string, any>

const TASKS: Array<{
  id: string
  batch: string
  source: string
  kind: 'web' | 'swing' | 'spring'
  mainClass?: string
}> = [
  { id: 'T01', batch: 'A', kind: 'web', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-A/batch-A/outputs/T01-runner') },
  { id: 'T02', batch: 'A', kind: 'web', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-A/batch-A/outputs/T02-platformer') },
  { id: 'T03', batch: 'A', kind: 'web', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-A/batch-A/outputs/T03-company') },
  { id: 'T04', batch: 'A', kind: 'web', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-A/batch-A/outputs/T04-travel') },
  { id: 'T05', batch: 'A', kind: 'swing', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-A/batch-A/outputs/T05-number-bomb'), mainClass: 'numberbomb.NumberBombApp' },
  { id: 'T06', batch: 'A', kind: 'web', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-A/batch-A/outputs/T06-market-bi') },
  { id: 'T07', batch: 'A', kind: 'web', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-A/batch-A/outputs/T07-ev') },
  { id: 'T08', batch: 'A', kind: 'web', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-A/batch-A/outputs/T08-rental') },
  { id: 'T09', batch: 'A', kind: 'spring', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-A/batch-A/outputs/T09-coffee') },
  { id: 'T01', batch: 'B', kind: 'web', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-B2/batch-B/outputs/T01-runner') },
  { id: 'T02', batch: 'B', kind: 'web', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-B2/batch-B/outputs/T02-platformer') },
  { id: 'T03', batch: 'B', kind: 'web', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-B2-retry4/batch-B/outputs/T03-company') },
  { id: 'T04', batch: 'B', kind: 'web', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-B2/batch-B/outputs/T04-travel') },
  { id: 'T05', batch: 'B', kind: 'swing', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-B2/batch-B/outputs/T05-number-bomb'), mainClass: 'NumberBomb' },
  { id: 'T06', batch: 'B', kind: 'web', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-B2-retry4/batch-B/outputs/T06-market-bi') },
  { id: 'T07', batch: 'B', kind: 'web', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-B2/batch-B/outputs/T07-ev') },
  { id: 'T08', batch: 'B', kind: 'web', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-B2-retry3/batch-B/outputs/T08-rental') },
  { id: 'T09', batch: 'B', kind: 'spring', source: join(artifactsRoot, 'rxycode-gui-real-e2e-full-18-B2-retry3/batch-B/outputs/T09-coffee') }
]

function chromeBinary(): string {
  const candidates = [
    process.env.CHROME_PATH,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
  ].filter((value): value is string => typeof value === 'string' && value.length > 0)
  const found = candidates.find((path) => existsSync(path))
  if (found === undefined) throw new Error('Chrome/Edge missing')
  return found
}

function mime(file: string): string {
  switch (extname(file).toLowerCase()) {
    case '.html': return 'text/html; charset=utf-8'
    case '.js': return 'text/javascript; charset=utf-8'
    case '.css': return 'text/css; charset=utf-8'
    case '.csv': return 'text/csv; charset=utf-8'
    case '.svg': return 'image/svg+xml'
    case '.png': return 'image/png'
    case '.json': return 'application/json'
    default: return 'application/octet-stream'
  }
}

function serveStatic(root: string, port: number): Promise<{ close: () => void }> {
  const server = createServer((req: IncomingMessage, res: ServerResponse) => {
    const raw = decodeURIComponent((req.url ?? '/').split('?')[0] || '/')
    let rel = raw.replace(/^\/+/, '')
    if (rel === '' || rel.endsWith('/')) rel = join(rel, 'index.html')
    const disk = resolve(root, rel)
    if (!disk.startsWith(resolve(root))) {
      res.writeHead(403)
      res.end()
      return
    }
    if (!existsSync(disk)) {
      res.writeHead(404)
      res.end('not found')
      return
    }
    res.writeHead(200, { 'content-type': mime(disk) })
    res.end(readFileSync(disk))
  })
  return new Promise((resolveListen, rejectListen) => {
    server.listen(port, '127.0.0.1', () => resolveListen({ close: () => server.close() }))
    server.on('error', rejectListen)
  })
}

function stopProcess(child: ChildProcess | null): void {
  if (child === null || child.killed || child.exitCode !== null) return
  try { child.kill() } catch {}
}

function parseDotEnv(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eq = trimmed.indexOf('=')
    if (eq < 1) continue
    out[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim().replace(/^['"]|['"]$/g, '')
  }
  return out
}

const delay = (ms: number): Promise<void> => new Promise((resolveDelay) => setTimeout(resolveDelay, ms))

function mysqlPartsFromJdbc(url: string): Record<string, string> {
  const match = String(url).match(/^jdbc:mysql:\/\/([^:/?#]+)(?::(\d+))?(?:\/([^?;#]+))?/i)
  if (match === null) return {}
  const parts: Record<string, string> = { MYSQL_HOST: match[1] ?? '' }
  if (match[2]) parts.MYSQL_PORT = match[2]
  if (match[3]) parts.MYSQL_DATABASE = match[3]
  return parts
}

function mysqlEnv(): Record<string, string> {
  const envPath = join(repoDir, '.env.t09-mysql')
  if (!existsSync(envPath)) return {}
  const parsed = parseDotEnv(readFileSync(envPath, 'utf8'))
  const allowed = [
    'MYSQL_URL',
    'MYSQL_USER',
    'MYSQL_PASSWORD',
    'MYSQL_ADMIN_PASSWORD',
    'SPRING_DATASOURCE_URL',
    'SPRING_DATASOURCE_USERNAME',
    'SPRING_DATASOURCE_PASSWORD',
    'APP_ADMIN_USERNAME',
    'APP_ADMIN_PASSWORD',
    'T09_ADMIN_PASSWORD'
  ]
  const out: Record<string, string> = {}
  for (const key of allowed) {
    const value = parsed[key]
    if (typeof value === 'string' && value.length > 0) out[key] = value
  }
  Object.assign(out, mysqlPartsFromJdbc(out.MYSQL_URL ?? out.SPRING_DATASOURCE_URL ?? ''))
  if (!out.APP_ADMIN_USERNAME) out.APP_ADMIN_USERNAME = 'admin'
  if (!out.APP_ADMIN_PASSWORD) out.APP_ADMIN_PASSWORD = out.T09_ADMIN_PASSWORD || 't09-demo-login'
  if (!out.T09_ADMIN_PASSWORD) out.T09_ADMIN_PASSWORD = out.APP_ADMIN_PASSWORD
  return out
}

function redactLog(text: string): string {
  return text
    .replace(/(password|pwd|secret|passwd)\s*[=:]\s*\S+/gi, '$1=***')
    .replace(/jdbc:mysql:\/\/[^\s"']+/gi, 'jdbc:mysql://***')
}

async function withChrome<T>(
  startUrl: string,
  shotDir: string,
  run: (api: {
    evaluate: (expr: string) => Promise<any>
    screenshot: (name: string) => Promise<string>
    navigate: (url: string) => Promise<void>
  }) => Promise<T>
): Promise<T> {
  mkdirSync(shotDir, { recursive: true })
  const profileDir = mkdtempSync(join(tmpdir(), 'rxy-real-user-'))
  const child = spawn(chromeBinary(), [
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    '--disable-background-networking',
    '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost',
    `--user-data-dir=${profileDir}`,
    '--window-size=1280,800',
    '--window-position=40,40',
    '--remote-debugging-port=0',
    startUrl
  ], { windowsHide: false, stdio: ['ignore', 'pipe', 'pipe'] })
  let socket: WebSocket | null = null
  try {
    const activePortFile = join(profileDir, 'DevToolsActivePort')
    const debugPort = await waitFor(async () => {
      if (!existsSync(activePortFile)) return null
      const value = Number(readFileSync(activePortFile, 'utf8').split(/\r?\n/)[0])
      return Number.isInteger(value) && value > 0 ? value : null
    }, 20_000, 'Chrome DevToolsActivePort')
    const target = await waitFor(async () => {
      try {
        const pages = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json() as Array<{ type: string; webSocketDebuggerUrl?: string }>
        return selectRendererTarget(pages)
      } catch {
        return null
      }
    }, 15_000, 'Chrome page target')
    const pending = new Map<number, { resolve: (value: any) => void; reject: (error: Error) => void }>()
    let sequence = 0
    const attachSocket = (next: WebSocket): void => {
      socket = next
      next.onmessage = (event) => {
        const message = JSON.parse(String(event.data)) as { id?: number; error?: unknown; result?: unknown }
        if (message.id === undefined) return
        const entry = pending.get(message.id)
        if (entry === undefined) return
        pending.delete(message.id)
        if (message.error !== undefined) entry.reject(new Error(JSON.stringify(message.error)))
        else entry.resolve(message.result)
      }
    }
    const openSocket = async (url: string): Promise<void> => {
      const next = new WebSocket(url)
      await new Promise<void>((resolveOpen, rejectOpen) => {
        next.onopen = () => resolveOpen()
        next.onerror = () => rejectOpen(new Error('Chrome CDP websocket failed'))
      })
      attachSocket(next)
    }
    await openSocket(target)
    const send = (method: string, params: unknown = {}, timeoutMs = 35_000): Promise<any> => new Promise((resolveSend, rejectSend) => {
      const id = ++sequence
      const timer = setTimeout(() => {
        pending.delete(id)
        rejectSend(new Error(`Chrome CDP timed out: ${method}`))
      }, timeoutMs)
      pending.set(id, {
        resolve: (value) => { clearTimeout(timer); resolveSend(value) },
        reject: (error) => { clearTimeout(timer); rejectSend(error) }
      })
      socket!.send(JSON.stringify({ id, method, params }))
    })
    const reconnect = async (): Promise<void> => {
      await new Promise((resolveDelay) => setTimeout(resolveDelay, 700))
      try { socket?.close() } catch {}
      const nextTarget = await waitFor(async () => {
        try {
          const pages = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json() as Array<{ type: string; webSocketDebuggerUrl?: string }>
          return selectRendererTarget(pages)
        } catch {
          return null
        }
      }, 15_000, 'Chrome page target after navigation')
      sequence = 0
      pending.clear()
      await openSocket(nextTarget)
      await send('Runtime.enable')
      await send('Page.enable')
    }
    await send('Runtime.enable')
    await send('Page.enable')
    const evaluateOnce = async (expression: string): Promise<any> => {
      const evaluated = await send('Runtime.evaluate', {
        expression,
        awaitPromise: true,
        returnByValue: true,
        userGesture: true
      })
      if (evaluated.exceptionDetails !== undefined) {
        throw new Error(evaluated.exceptionDetails.text ?? 'page expression threw')
      }
      return evaluated.result?.value ?? {}
    }
    const evaluate = async (expression: string): Promise<any> => {
      for (let hop = 0; hop < 5; hop += 1) {
        try {
          return await evaluateOnce(expression)
        } catch (caught) {
          const message = caught instanceof Error ? caught.message : String(caught)
          if (!/navigated or closed/i.test(message) || hop === 4) throw caught
          await reconnect()
        }
      }
      return {}
    }
    const screenshot = async (name: string): Promise<string> => {
      try {
        const image = await send('Page.captureScreenshot', { format: 'png' }, 10_000)
        const path = join(shotDir, name)
        if (typeof image.data === 'string') writeFileSync(path, Buffer.from(image.data, 'base64'))
        return path
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : String(caught)
        if (!/navigated or closed/i.test(message)) throw caught
        await reconnect()
        const image = await send('Page.captureScreenshot', { format: 'png' }, 10_000)
        const path = join(shotDir, name)
        if (typeof image.data === 'string') writeFileSync(path, Buffer.from(image.data, 'base64'))
        return path
      }
    }
    const navigate = async (url: string): Promise<void> => {
      try {
        await send('Page.navigate', { url })
      } catch {
        await reconnect()
      }
      await new Promise((resolveDelay) => setTimeout(resolveDelay, 800))
      try {
        await send('Runtime.enable')
      } catch {
        await reconnect()
      }
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 600))
    return await run({ evaluate, screenshot, navigate })
  } finally {
    try { socket?.close() } catch {}
    stopProcess(child)
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 400))
    try { rmSync(profileDir, { recursive: true, force: true }) } catch {}
  }
}

const js = {
  t01: `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const press = (key) => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
      document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
    };
    return (async () => {
      const start = document.querySelector('#btn-start, #startBtn');
      if (!(start instanceof HTMLElement)) return { ok: false, reason: 'no start' };
      const before = Number(document.querySelector('#scoreVal, #score')?.textContent || 0);
      start.click();
      await sleep(250);
      for (let i = 0; i < 8; i += 1) { press(' '); press('ArrowUp'); await sleep(180); }
      const pause = document.querySelector('#btn-pause');
      if (pause instanceof HTMLElement) pause.click();
      else press('p');
      await sleep(200);
      const resume = document.querySelector('#btn-resume, #btn-resume2');
      if (resume instanceof HTMLElement) resume.click();
      for (let i = 0; i < 50; i += 1) { press(' '); await sleep(160); }
      const after = Number(document.querySelector('#scoreVal, #score')?.textContent || 0);
      const state = (document.querySelector('#stateLabel, #state')?.textContent || '').trim();
      const restart = document.querySelector('#btn-restart2, #btn-restart, #restartBtn');
      if (restart instanceof HTMLElement) restart.click();
      await sleep(300);
      const best = Number(document.querySelector('#bestVal, #bestFinalVal, #bestMenuVal')?.textContent || 0);
      return { ok: after > before || /运行|结束|over|running/i.test(state), scoreBefore: before, scoreAfter: after, state, best, startHidden: !isShown(start) };
      function isShown(node) {
        if (!(node instanceof HTMLElement)) return false;
        const s = getComputedStyle(node);
        const b = node.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden' && b.width > 1;
      }
    })();
  })()`,
  t02: `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const down = (key) => {
      const init = { key, code: key === ' ' ? 'Space' : key, bubbles: true, cancelable: true };
      document.dispatchEvent(new KeyboardEvent('keydown', init));
      window.dispatchEvent(new KeyboardEvent('keydown', init));
    };
    const up = (key) => {
      const init = { key, code: key === ' ' ? 'Space' : key, bubbles: true, cancelable: true };
      document.dispatchEvent(new KeyboardEvent('keyup', init));
      window.dispatchEvent(new KeyboardEvent('keyup', init));
    };
    const shown = (node) => {
      if (!(node instanceof HTMLElement)) return false;
      const s = getComputedStyle(node);
      return s.display !== 'none' && s.visibility !== 'hidden' && !node.classList.contains('hidden');
    };
    return (async () => {
      const start = document.querySelector('#btn-start, #startBtn');
      if (!(start instanceof HTMLElement)) return { ok: false, reason: 'no start' };
      start.click();
      await sleep(400);
      down('ArrowRight');
      down('d');
      for (let i = 0; i < 28; i += 1) {
        down(' ');
        down('ArrowUp');
        await sleep(140);
        up(' ');
        up('ArrowUp');
        await sleep(80);
      }
      const score = Number(document.querySelector('#score, #coin, #scoreVal')?.textContent || 0);
      const lives = Number(document.querySelector('#lives')?.textContent || 0);
      const level = Number(document.querySelector('#level')?.textContent || 0);
      const pauseBtn = document.querySelector('#btn-pause');
      if (pauseBtn instanceof HTMLElement) pauseBtn.click();
      else down('p');
      await sleep(350);
      const pauseVisible = shown(document.querySelector('#pause, #pauseOverlay'));
      return {
        ok: score > 0 || pauseVisible || /运行|running/i.test(document.body.innerText),
        coins: score,
        score,
        lives,
        level,
        pauseVisible,
        state: (document.querySelector('#state, #stateLabel')?.textContent || '').trim()
      };
    })();
  })()`,
  t03home: `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    return (async () => {
      const demo = document.querySelector('#btn-demo-login');
      const openLogin = document.querySelector('#btn-open-login');
      return {
        ok: Boolean(document.querySelector('h1')),
        title: document.title,
        hasDemo: Boolean(demo),
        hasOpenLogin: Boolean(openLogin),
        text: (document.body.innerText || '').slice(0, 400)
      };
    })();
  })()`,
  t03wrong: `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    return (async () => {
      const user = document.querySelector('#lg_user, #site-login-user, #login-user, #loginUser');
      const pass = document.querySelector('#lg_pass, #site-login-pass, #login-pass, #loginPass');
      const form = document.querySelector('#loginForm, #siteLoginForm, form');
      if (!(user instanceof HTMLInputElement)) return { ok: false, reason: 'no login fields' };
      user.value = 'wrong';
      user.dispatchEvent(new Event('input', { bubbles: true }));
      if (pass instanceof HTMLInputElement) {
        pass.value = 'nope';
        pass.dispatchEvent(new Event('input', { bubbles: true }));
      }
      if (form instanceof HTMLFormElement) form.requestSubmit();
      else document.querySelector('button[type=submit]')?.click();
      await sleep(500);
      const msg = (document.querySelector('#loginMsg, #siteLoginStatus, .form-msg, .error, #login-error')?.textContent || '').trim();
      const body = document.body.innerText || '';
      return { ok: msg.length > 0 || /错误|失败|invalid|incorrect/i.test(body), msg: msg || body.slice(0, 120) };
    })();
  })()`,
  t03demo: `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    return (async () => {
      const demo = document.querySelector('#btn-demo-login, #btn-demo-login-alt');
      if (demo instanceof HTMLElement) {
        demo.click();
        await sleep(1200);
      }
      return { href: location.href, title: document.title, modules: document.querySelectorAll('[data-module]').length };
    })();
  })()`,
  t03admin: `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    return (async () => {
      for (let i = 0; i < 25 && document.querySelectorAll('[data-module]').length === 0; i += 1) await sleep(150);
      const names = Array.from(document.querySelectorAll('[data-module]')).map((n) => n.getAttribute('data-module'));
      const visited = [];
      for (const name of names) {
        const btn = document.querySelector('[data-module="'+name+'"]');
        if (btn instanceof HTMLElement) {
          btn.click();
          await sleep(220);
          visited.push({ name, title: (document.querySelector('#moduleTitle, h1')?.textContent || '').trim() });
        }
      }
      return {
        ok: names.length >= 5,
        modules: names.length,
        names,
        visited,
        href: location.href,
        title: document.title,
        modalBlocking: Boolean(document.querySelector('#modalMask:not([hidden])'))
      };
    })();
  })()`,
  t03realLogin: `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    return (async () => {
      const hint = document.body.innerText || '';
      const pass = /demo1234/.test(hint) ? 'demo1234' : 'demo123';
      const user = document.querySelector('#lg_user, #site-login-user, #login-user, #loginUser');
      const pw = document.querySelector('#lg_pass, #site-login-pass, #login-pass, #loginPass');
      if (!(user instanceof HTMLInputElement) || !(pw instanceof HTMLInputElement)) {
        return { ok: false, reason: 'no fields', href: location.href };
      }
      user.value = 'admin';
      pw.value = pass;
      user.dispatchEvent(new Event('input', { bubbles: true }));
      pw.dispatchEvent(new Event('input', { bubbles: true }));
      const form = document.querySelector('#loginForm, #siteLoginForm');
      if (form instanceof HTMLFormElement) form.requestSubmit();
      else document.querySelector('button[type=submit]')?.click();
      await sleep(900);
      return {
        ok: document.querySelectorAll('[data-module]').length >= 5,
        href: location.href,
        modules: document.querySelectorAll('[data-module]').length,
        usedHint: pass
      };
    })();
  })()`,
  t03addUser: `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    return (async () => {
      const users = document.querySelector('[data-module="users"]');
      if (users instanceof HTMLElement) users.click();
      await sleep(250);
      document.querySelector('#modalCancel')?.click();
      await sleep(150);
      const addBtn = document.querySelector('#userAddBtn, #btn-add-user') || Array.from(document.querySelectorAll('button')).find((b) => /新增用户/.test(b.textContent || ''));
      if (addBtn instanceof HTMLElement) addBtn.click();
      await sleep(300);
      const name = document.querySelector('#mf_name, #m-name, input[name="name"]');
      const email = document.querySelector('#mf_email, #m-email, input[name="email"]');
      const role = document.querySelector('#m-role');
      if (role instanceof HTMLInputElement && !role.value) role.value = '运营';
      if (name instanceof HTMLInputElement) {
        name.value = 'realuser';
        name.dispatchEvent(new Event('input', { bubbles: true }));
      }
      if (email instanceof HTMLInputElement) {
        email.value = 'realuser@demo.example.com';
        email.dispatchEvent(new Event('input', { bubbles: true }));
      }
      const fields = (document.querySelector('#modalFields')?.innerText || '').trim();
      return {
        ok: Boolean(name instanceof HTMLInputElement && name.value),
        fields: fields.slice(0, 200),
        modalTitle: (document.querySelector('#modalTitle')?.textContent || '').trim()
      };
    })();
  })()`,
  t04: `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const fire = (el) => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); };
    return (async () => {
      const city = document.querySelector('[data-city="hz"], [data-city="sz"], #chips-hangzhou, #chips-suzhou');
      if (city instanceof HTMLElement) city.click();
      const cap = document.querySelector('#budgetCap');
      if (cap instanceof HTMLInputElement) { cap.value = '2600'; fire(cap); }
      const mode = document.querySelector('#modeSelect, #scenario');
      if (mode instanceof HTMLSelectElement && mode.options.length > 1) { mode.selectedIndex = 1; fire(mode); }
      const dep = document.querySelector('#depDate');
      if (dep instanceof HTMLInputElement) { dep.value = '2026-09-10'; fire(dep); }
      await sleep(300);
      const text = document.body.innerText || '';
      return {
        ok: /苏州|杭州|预算/.test(text),
        hasControls: Boolean(cap || city || mode || dep),
        overBudget: /超预算/.test(text),
        snippet: text.slice(0, 500)
      };
    })();
  })()`,
  t06: `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    return (async () => {
      const gold = document.querySelector('#a_gold');
      if (gold instanceof HTMLInputElement) { gold.checked = false; gold.dispatchEvent(new Event('change', { bubbles: true })); }
      document.querySelector('#m_norm')?.click();
      document.querySelector('#s_dd')?.click();
      document.querySelector('#apply')?.click();
      await sleep(400);
      const canvas = document.querySelector('canvas');
      if (canvas instanceof HTMLCanvasElement) {
        canvas.dispatchEvent(new MouseEvent('mousemove', { clientX: canvas.getBoundingClientRect().left + 80, clientY: canvas.getBoundingClientRect().top + 80, bubbles: true }));
      }
      await sleep(200);
      const table = document.querySelector('table');
      return { ok: Boolean(canvas || table), title: document.title, hasTable: Boolean(table), text: (document.body.innerText || '').slice(0, 400) };
    })();
  })()`,
  t07: `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const fire = (el) => {
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    };
    return (async () => {
      const recEl = document.querySelector('#recName, .name');
      const before = (recEl?.textContent || document.body.innerText || '').slice(0, 120);
      const economy = document.querySelector('#btnEconomy');
      if (economy instanceof HTMLElement) economy.click();
      const mileage = document.querySelector('#mileage, #km');
      if (mileage instanceof HTMLInputElement) {
        mileage.value = String(Math.min(Number(mileage.max || 30000), 25000));
        fire(mileage);
      }
      const wTco = document.querySelector('#wTco, #wcost, #w-cost');
      if (wTco instanceof HTMLInputElement) {
        wTco.value = wTco.max && Number(wTco.max) > 100 ? '70' : '70';
        fire(wTco);
      }
      const budget = document.querySelector('#budget');
      if (budget instanceof HTMLInputElement && budget.id === 'budget') {
        budget.value = '200000';
        fire(budget);
      }
      await sleep(400);
      const afterRec = (document.querySelector('#recName, .name')?.textContent || '').trim();
      const after = document.body.innerText || '';
      return {
        ok: /TCO|总持有|推荐|万元|续航/.test(after),
        changed: before.trim() !== afterRec || /25000|20,000|经济/.test(after),
        recBefore: before.trim(),
        recAfter: afterRec || after.slice(0, 80),
        snippet: after.slice(0, 500)
      };
    })();
  })()`,
  t08: `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const fire = (el) => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); };
    return (async () => {
      const district = document.querySelector('#f-district');
      if (district instanceof HTMLSelectElement && district.options.length > 2) { district.selectedIndex = 2; fire(district); }
      const budget = document.querySelector('#f-budget');
      if (budget instanceof HTMLInputElement) { budget.value = '3000'; fire(budget); }
      const commute = document.querySelector('#f-commute');
      if (commute instanceof HTMLInputElement) { commute.value = '45'; fire(commute); }
      const wrent = document.querySelector('#w-rent');
      if (wrent instanceof HTMLInputElement) { wrent.value = '20'; fire(wrent); }
      await sleep(300);
      const text = document.body.innerText || '';
      const map = Boolean(document.querySelector('svg, #map, #mapbox, .map-svg, .map-box'));
      return { ok: /合同|风险|地图/.test(text) && map, map, hasContract: /合同条款|解约|噪音|维修/.test(text), snippet: text.slice(0, 500) };
    })();
  })()`,
  t09wrong: `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    return (async () => {
      for (let i = 0; i < 20; i += 1) {
        const loginA = document.querySelector('#login-view');
        const loginB = document.querySelector('#loginPanel');
        const visibleA = loginA instanceof HTMLElement && !loginA.classList.contains('hidden');
        const visibleB = loginB instanceof HTMLElement && !loginB.classList.contains('hidden');
        if (visibleA || visibleB || document.querySelector('#login-username, #loginUser')) break;
        await sleep(200);
      }
      const u = document.querySelector('#loginUser, #login-username');
      const p = document.querySelector('#loginPass, #login-password');
      if (u instanceof HTMLInputElement) u.value = 'nope';
      if (p instanceof HTMLInputElement) p.value = 'nope';
      const form = document.querySelector('#login-form');
      if (form instanceof HTMLFormElement) form.requestSubmit();
      else document.querySelector('#loginBtn')?.click();
      await sleep(900);
      const msg = (document.querySelector('#loginMsg, #login-error')?.textContent || '').trim();
      const stillOnLogin = Boolean(
        document.querySelector('#loginPanel:not(.hidden), #login-view:not(.hidden), #loginUser, #login-username')
      );
      return { ok: msg.length > 0 || stillOnLogin, msg, stillOnLogin };
    })();
  })()`,
  t09login: (user: string, pass: string) => `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    return (async () => {
      const u = document.querySelector('#loginUser, #login-username');
      const p = document.querySelector('#loginPass, #login-password');
      if (u instanceof HTMLInputElement) u.value = ${JSON.stringify(user)};
      if (p instanceof HTMLInputElement) p.value = ${JSON.stringify(pass)};
      const form = document.querySelector('#login-form');
      if (form instanceof HTMLFormElement) form.requestSubmit();
      else document.querySelector('#loginBtn')?.click();
      await sleep(1500);
      const mainA = document.querySelector('#main-view');
      const mainB = document.querySelector('#mainPanel');
      const ok = Boolean(
        (mainA && !mainA.classList.contains('hidden')) ||
        (mainB && !mainB.classList.contains('hidden'))
      );
      return {
        ok,
        who: (document.querySelector('#who, #current-user')?.textContent || '').trim(),
        flavor: document.querySelector('#login-username') ? 'A' : 'B'
      };
    })();
  })()`,
  t09use: `(() => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const fire = (el) => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); };
    return (async () => {
      try {
        const flavorA = Boolean(document.querySelector('#product-form, #login-username, #view-products'));
        if (flavorA) {
          document.querySelector('[data-view="products"]')?.click();
          await sleep(400);
          const form = document.querySelector('#product-form');
          const name = form?.querySelector('input[name="name"]');
          const price = form?.querySelector('input[name="price"]');
          const cat = form?.querySelector('input[name="category"]');
          if (name instanceof HTMLInputElement) name.value = '实机体验拿铁';
          if (price instanceof HTMLInputElement) price.value = '28';
          if (cat instanceof HTMLInputElement) cat.value = '咖啡';
          if (form instanceof HTMLFormElement) form.requestSubmit();
          await sleep(1200);
          document.querySelector('[data-view="inventory"]')?.click();
          await sleep(500);
          const invForm = document.querySelector('#inventory-form');
          const invSel = invForm?.querySelector('select[name="productId"]');
          if (invSel instanceof HTMLSelectElement && invSel.options.length > 1) {
            invSel.selectedIndex = 1;
            fire(invSel);
          }
          const qty = invForm?.querySelector('input[name="quantity"]');
          const th = invForm?.querySelector('input[name="lowThreshold"]');
          if (qty instanceof HTMLInputElement) qty.value = '12';
          if (th instanceof HTMLInputElement) th.value = '3';
          if (invForm instanceof HTMLFormElement) invForm.requestSubmit();
          await sleep(800);
          document.querySelector('[data-view="orders"]')?.click();
          await sleep(500);
          const orderForm = document.querySelector('#order-form');
          const cust = orderForm?.querySelector('input[name="customer"]');
          const op = orderForm?.querySelector('select[name="productId"]');
          const oq = orderForm?.querySelector('input[name="quantity"]');
          if (cust instanceof HTMLInputElement) cust.value = '真实用户探针';
          if (op instanceof HTMLSelectElement && op.options.length > 1) { op.selectedIndex = 1; fire(op); }
          if (oq instanceof HTMLInputElement) oq.value = '2';
          if (orderForm instanceof HTMLFormElement) orderForm.requestSubmit();
          await sleep(600);
          document.querySelector('#place-order-btn')?.click();
          await sleep(1000);
          document.querySelector('[data-view="admin"]')?.click();
          await sleep(400);
          const today = new Date().toISOString().slice(0, 10);
          const rf = document.querySelector('#revenue-form');
          const start = rf?.querySelector('input[name="start"]');
          const end = rf?.querySelector('input[name="end"]');
          if (start instanceof HTMLInputElement) start.value = today;
          if (end instanceof HTMLInputElement) end.value = today;
          if (rf instanceof HTMLFormElement) rf.requestSubmit();
          await sleep(800);
          const products = (document.querySelector('#product-table')?.innerText || '');
          const revenue = (document.querySelector('#rev-total')?.textContent || '') + ' ' + (document.querySelector('#rev-count')?.textContent || '');
          return {
            ok: /拿铁|Latte|Espresso/.test(document.body.innerText) || /¥/.test(revenue),
            flavor: 'A',
            productTable: products.slice(0, 400),
            inventory: (document.querySelector('#inventory-table')?.innerText || '').slice(0, 400),
            revenue: revenue.slice(0, 300),
            loggedOut: false
          };
        }
        const name = document.querySelector('#pName');
        const price = document.querySelector('#pPrice');
        const cat = document.querySelector('#pCategory');
        if (name instanceof HTMLInputElement) name.value = '实机体验拿铁';
        if (price instanceof HTMLInputElement) price.value = '28';
        if (cat instanceof HTMLInputElement) cat.value = '咖啡';
        document.querySelector('#addProductBtn')?.click();
        await sleep(1500);
        const prodText = (document.querySelector('#productTable')?.innerText || '') + (document.querySelector('#prodMsg')?.innerText || '');
        const invSel = document.querySelector('#invProduct');
        if (invSel instanceof HTMLSelectElement && invSel.options.length > 0) {
          invSel.selectedIndex = Math.min(1, invSel.options.length - 1);
          fire(invSel);
        }
        const invQty = document.querySelector('#invQty');
        const invTh = document.querySelector('#invThresh');
        if (invQty instanceof HTMLInputElement) invQty.value = '12';
        if (invTh instanceof HTMLInputElement) invTh.value = '3';
        document.querySelector('#setInvBtn')?.click();
        await sleep(800);
        const cust = document.querySelector('#custName');
        if (cust instanceof HTMLInputElement) cust.value = '真实用户探针';
        const orderSel = document.querySelector('#orderProduct');
        if (orderSel instanceof HTMLSelectElement && orderSel.options.length > 0) {
          orderSel.selectedIndex = Math.min(1, orderSel.options.length - 1);
          fire(orderSel);
        }
        const qty = document.querySelector('#orderQty');
        if (qty instanceof HTMLInputElement) qty.value = '2';
        document.querySelector('#addLineBtn')?.click();
        await sleep(200);
        document.querySelector('#placeOrderBtn')?.click();
        await sleep(1000);
        document.querySelector('#revBtn')?.click();
        await sleep(700);
        const invText = (document.querySelector('#invTable')?.innerText || '');
        const revText = (document.querySelector('#revBody')?.innerText || '');
        const products = (document.querySelector('#productTable')?.innerText || '') + ' ' + prodText;
        return {
          ok: /实机体验拿铁/.test(products) || /拿铁/.test(document.body.innerText) || /营收总额/.test(revText),
          flavor: 'B',
          productTable: products.slice(0, 400),
          inventory: invText.slice(0, 400),
          revenue: revText.slice(0, 300),
          loggedOut: false
        };
      } catch (err) {
        return { ok: false, error: String(err) };
      }
    })();
  })()`
}

async function playWeb(task: typeof TASKS[number], port: number): Promise<StepResult> {
  const shotDir = join(outRoot, `${task.batch}-${task.id}`, 'screenshots')
  const server = await serveStatic(task.source, port)
  const url = `http://127.0.0.1:${port}/`
  try {
    return await withChrome(url, shotDir, async (api) => {
      const notes: StepResult = { id: task.id, batch: task.batch, source: task.source }
      await api.screenshot('01-open.png')
      if (task.id === 'T01') {
        notes.play = await api.evaluate(js.t01)
        await api.screenshot('02-after-play.png')
      } else if (task.id === 'T02') {
        notes.play = await api.evaluate(js.t02)
        await api.screenshot('02-after-play.png')
      } else if (task.id === 'T03') {
        notes.home = await api.evaluate(js.t03home)
        await api.screenshot('01-home.png')
        const hasInlineLogin = await api.evaluate(`Boolean(document.querySelector('#lg_user, #site-login-user, #login-user'))`)
        if (hasInlineLogin) {
          notes.wrong = await api.evaluate(js.t03wrong)
          await api.screenshot('02-wrong-login.png')
        } else if (existsSync(join(task.source, 'login.html'))) {
          await api.navigate(`${url}login.html`)
          notes.wrong = await api.evaluate(js.t03wrong)
          await api.screenshot('02-wrong-login.png')
          await api.navigate(url)
          await delay(500)
        }
        notes.demo = await api.evaluate(js.t03demo)
        await delay(1000)
        let href = String(await api.evaluate('location.href'))
        if (!/admin\\.html/i.test(href) && existsSync(join(task.source, 'admin.html'))) {
          // Stay in the same origin; do not invent a new session. Click demo again if still on home.
          notes.demoRetry = await api.evaluate(js.t03demo)
          await delay(1000)
          href = String(await api.evaluate('location.href'))
        }
        await api.screenshot('03-after-demo.png')
        const onLogin = /login\\.html/i.test(href) || Boolean(await api.evaluate(`Boolean(document.querySelector('#loginForm, #lg_user, #login-user')) && document.querySelectorAll('[data-module]').length === 0`))
        if (onLogin || Number(notes.demo?.modules ?? 0) === 0) {
          notes.realLogin = await api.evaluate(js.t03realLogin)
          await delay(800)
          await api.screenshot('03b-password-login.png')
        }
        notes.admin = await api.evaluate(js.t03admin)
        await api.screenshot('04-admin-modules.png')
        for (const name of ['orders', 'content', 'settings', 'analytics']) {
          await api.evaluate(`document.querySelector('[data-module="${name}"]')?.click()`)
          await delay(350)
          await api.screenshot(`05-module-${name}.png`)
        }
        notes.addUser = await api.evaluate(js.t03addUser)
        await api.screenshot('06-add-user-modal.png')
        await api.evaluate(`(() => {
          const form = document.querySelector('#modalForm');
          if (form instanceof HTMLFormElement) form.requestSubmit();
          const save = document.querySelector('[data-modal="save"]');
          if (save instanceof HTMLElement) save.click();
        })()`)
        await delay(400)
        await api.screenshot('07-after-add-user.png')
        await api.evaluate(`document.querySelector('#logoutBtn')?.click()`)
        await delay(500)
        await api.screenshot('08-after-logout.png')
      } else if (task.id === 'T04') {
        notes.play = await api.evaluate(js.t04)
        await api.screenshot('02-filters.png')
      } else if (task.id === 'T06') {
        notes.play = await api.evaluate(js.t06)
        await api.screenshot('02-filters.png')
      } else if (task.id === 'T07') {
        notes.play = await api.evaluate(js.t07)
        await api.screenshot('02-weights.png')
      } else if (task.id === 'T08') {
        notes.play = await api.evaluate(js.t08)
        await api.screenshot('02-filter-map.png')
      }
      notes.ok = Boolean(notes.play?.ok ?? notes.admin?.ok ?? notes.addUser?.ok ?? notes.home?.ok)
      return notes
    })
  } finally {
    server.close()
  }
}

function compileSwing(source: string, mainClass: string, classOut: string): string | null {
  mkdirSync(classOut, { recursive: true })
  const files = mainClass.includes('.')
    ? [join(source, 'src', 'numberbomb', 'NumberBombApp.java'), join(source, 'src', 'numberbomb', 'GameModel.java')].filter((f) => existsSync(f))
    : [join(source, 'NumberBomb.java'), join(source, 'NumberBombEngine.java')].filter((f) => existsSync(f))
  if (files.length === 0) return 'no java sources'
  const compile = spawnSync('javac', ['-encoding', 'UTF-8', '-d', classOut, ...files], { encoding: 'utf8', windowsHide: true })
  if (compile.status !== 0) return String(compile.stderr || compile.stdout).slice(0, 800)
  return null
}

function playSwing(task: typeof TASKS[number]): StepResult {
  const shotDir = join(outRoot, `${task.batch}-${task.id}`, 'screenshots')
  mkdirSync(shotDir, { recursive: true })
  const classOut = join(outRoot, `${task.batch}-${task.id}`, 'classes')
  const probeOut = join(outRoot, `${task.batch}-${task.id}`, 'probe-classes')
  mkdirSync(probeOut, { recursive: true })
  const compileError = compileSwing(task.source, task.mainClass ?? '', classOut)
  if (compileError) return { id: task.id, batch: task.batch, ok: false, error: compileError }
  const probeSrc = join(scriptDir, 'SwingRealUserProbe.java')
  const probeCompile = spawnSync('javac', ['-encoding', 'UTF-8', '-d', probeOut, probeSrc], { encoding: 'utf8', windowsHide: true })
  if (probeCompile.status !== 0) return { id: task.id, batch: task.batch, ok: false, error: String(probeCompile.stderr).slice(0, 800) }
  const sep = process.platform === 'win32' ? ';' : ':'
  const run = spawnSync('java', ['-cp', `${classOut}${sep}${probeOut}`, 'SwingRealUserProbe', task.mainClass ?? '', shotDir], {
    encoding: 'utf8',
    windowsHide: false,
    timeout: 30_000
  })
  let parsed: StepResult = {}
  try { parsed = JSON.parse((run.stdout || '').trim().split(/\r?\n/).at(-1) || '{}') } catch { parsed = { raw: run.stdout } }
  return {
    id: task.id,
    batch: task.batch,
    ok: run.status === 0 && parsed.ok === true,
    status: run.status,
    stderr: String(run.stderr || '').slice(0, 400),
    ...parsed
  }
}

async function waitHttp(url: string, timeoutMs: number, child: ChildProcess | null = null): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (child !== null && child.exitCode !== null) return false
    try {
      const res = await fetch(url)
      if (res.ok || res.status === 401 || res.status === 403) return true
    } catch {}
    await delay(500)
  }
  return false
}

function findMvn(source: string): string | null {
  const local = join(source, '.tools', 'apache-maven-3.9.16', 'bin', 'mvn.cmd')
  return existsSync(local) ? local : null
}

async function playSpring(task: typeof TASKS[number], port: number): Promise<StepResult> {
  const shotDir = join(outRoot, `${task.batch}-${task.id}`, 'screenshots')
  mkdirSync(shotDir, { recursive: true })
  const existing = process.env.PLAY_SPRING_URL
  const env = { ...process.env, ...mysqlEnv(), SERVER_PORT: String(port), PORT: String(port) }
  if (!env.APP_ADMIN_USERNAME) env.APP_ADMIN_USERNAME = 'admin'
  if (!env.APP_ADMIN_PASSWORD) env.APP_ADMIN_PASSWORD = env.T09_ADMIN_PASSWORD || 't09-demo-login'
  let child: ChildProcess | null = null
  const url = existing && existing.length > 0 ? existing : `http://127.0.0.1:${port}/`
  const logFile = join(outRoot, `${task.batch}-${task.id}`, 'spring-boot.log')
  if (!existing) {
    const mvn = findMvn(task.source)
    if (mvn === null) return { id: task.id, batch: task.batch, ok: false, error: 'project-local Maven missing' }
    mkdirSync(dirname(logFile), { recursive: true })
    child = spawn(process.env.ComSpec || 'cmd.exe', ['/d', '/s', '/c', `${mvn} -f pom.xml spring-boot:run "-Dspring-boot.run.arguments=--server.port=${port}"`], {
      cwd: task.source,
      env,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe']
    })
    let log = ''
    const append = (chunk: unknown) => {
      log += String(chunk)
      if (log.length > 400_000) log = log.slice(-300_000)
      writeFileSync(logFile, log)
    }
    child.stdout?.on('data', append)
    child.stderr?.on('data', append)
    const ready = await waitHttp(url, 180_000, child)
    if (!ready) {
      stopProcess(child)
      return { id: task.id, batch: task.batch, ok: false, error: 'spring did not listen', logTail: redactLog(log.slice(-2500)) }
    }
  }
  try {
    const user = String(env.APP_ADMIN_USERNAME)
    const pass = String(env.APP_ADMIN_PASSWORD)
    return await withChrome(url, shotDir, async (api) => {
      await delay(800)
      await api.screenshot('01-login.png')
      const wrong = await api.evaluate(js.t09wrong)
      await api.screenshot('02-wrong-login.png')
      const login = await api.evaluate(js.t09login(user, pass))
      await delay(800)
      await api.screenshot('03-logged-in.png')
      const used = await api.evaluate(js.t09use)
      await api.screenshot('04-after-order.png')
      return {
        id: task.id,
        batch: task.batch,
        ok: Boolean(login.ok && (used.ok || /营收|¥|收入/.test(String(used.revenue || '')))),
        wrong,
        login,
        used
      }
    })
  } finally {
    if (!existing) stopProcess(child)
  }
}

async function main(): Promise<void> {
  mkdirSync(outRoot, { recursive: true })
  const only = new Set((process.argv.find((arg) => arg.startsWith('--only='))?.slice('--only='.length) ?? '').split(',').filter(Boolean))
  const selected = TASKS.filter((task) => existsSync(task.source) && (only.size === 0 || only.has(`${task.batch}-${task.id}`) || only.has(task.id)))
  const resultPath = join(outRoot, 'playthrough-results.json')
  const previous = existsSync(resultPath) ? JSON.parse(readFileSync(resultPath, 'utf8')).results as StepResult[] : []
  const results: StepResult[] = previous.filter((item) => !selected.some((task) => task.id === item.id && task.batch === item.batch))
  let port = 18821
  for (const task of selected) {
    console.log(`REAL_USER ${task.batch}-${task.id} ${task.kind}`)
    try {
      if (task.kind === 'web') results.push(await playWeb(task, port++))
      else if (task.kind === 'swing') results.push(playSwing(task))
      else results.push(await playSpring(task, port++))
    } catch (caught) {
      results.push({ id: task.id, batch: task.batch, ok: false, error: caught instanceof Error ? caught.message : String(caught) })
    }
    writeFileSync(join(outRoot, 'playthrough-results.json'), JSON.stringify({ generated_at: new Date().toISOString(), results }, null, 2))
  }
  const failures = results.filter((item) => item.ok !== true)
  console.log(JSON.stringify({ outRoot, count: results.length, failures: failures.map((item) => ({ id: item.id, batch: item.batch, error: item.error })) }, null, 2))
  if (failures.length > 0) process.exitCode = 1
}

void main().catch((error) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error))
  process.exitCode = 1
})
