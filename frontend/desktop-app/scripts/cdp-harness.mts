import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import { createHash } from 'node:crypto'
import {
  copyFileSync,
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync
} from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { dirname, isAbsolute, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const desktopAppDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
export const repositoryDir = resolve(process.env.RXYCODE_REPO_DIR ?? resolve(desktopAppDir, '..', '..'))
const vite = join(desktopAppDir, 'node_modules', 'electron-vite', 'bin', 'electron-vite.js')

export function screenshotPath(artifactDir: string, requestedPath: string): string {
  return isAbsolute(requestedPath) ? requestedPath : join(artifactDir, requestedPath)
}

const delay = (ms: number): Promise<void> => new Promise((resolveDelay) => setTimeout(resolveDelay, ms))

export function electronViteDevArgs(profileDir: string): string[] {
  return [
    vite,
    'dev',
    '--',
    '--port=0',
    '--remote-debugging-port=0',
    `--user-data-dir=${profileDir}`
  ]
}

export function electronViteNodeOptions(existing?: string): string {
  const extra = '--max-old-space-size=8192'
  const current = existing?.trim() ?? ''
  if (/(^|\s)--max-old-space-size=/.test(current)) return current
  return current.length > 0 ? `${current} ${extra}` : extra
}

export async function captureScreenshotWithRetry(
  send: (method: string, params?: unknown, timeoutMs?: number) => Promise<any>,
  attempts = 3
): Promise<{ data: string }> {
  let lastError: Error | null = null
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      try {
        await send('Page.bringToFront', {}, 5_000)
      } catch {
        // Screenshot itself is still useful when bringToFront is unsupported.
      }
      const image = await send(
        'Page.captureScreenshot',
        attempt === 1 ? { format: 'png' } : { format: 'png', optimizeForSpeed: true },
        10_000
      )
      if (typeof image?.data !== 'string' || image.data.length === 0) {
        throw new Error('captureScreenshot returned no data')
      }
      return image
    } catch (caught) {
      lastError = caught instanceof Error ? caught : new Error(String(caught))
      if (attempt >= attempts) break
      await delay(200)
    }
  }
  throw lastError ?? new Error('captureScreenshot failed')
}

export async function waitFor<T>(
  probe: () => Promise<T | null>,
  timeoutMs: number,
  label: string
): Promise<T> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const value = await probe()
    if (value !== null) return value
    await delay(100)
  }
  throw new Error(`timeout waiting for ${label}`)
}

export interface DevToolsPageTarget {
  type: string
  url?: string
  webSocketDebuggerUrl?: string
}

export function selectRendererTarget(pages: DevToolsPageTarget[]): string | null {
  const candidates = pages.filter((page) => page.type === 'page' && page.webSocketDebuggerUrl !== undefined)
  const renderer = candidates.find((page) => !String(page.url ?? '').startsWith('devtools://'))
  return (renderer ?? candidates[0])?.webSocketDebuggerUrl ?? null
}

function sha256(path: string): string | null {
  if (!existsSync(path)) return null
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

function copyIsolatedConfiguration(targetDataDir: string): Record<string, string | null> {
  const sourceDataDir = resolve(process.env.RXYCODE_SOURCE_DATA_DIR ?? join(homedir(), '.RxyCode'))
  const hashes: Record<string, string | null> = {}
  for (const name of ['config.yaml', 'credentials.yaml']) {
    const source = join(sourceDataDir, name)
    hashes[source] = sha256(source)
    if (existsSync(source)) copyFileSync(source, join(targetDataDir, name))
  }
  return hashes
}

function sourceConfigurationUnchanged(hashes: Record<string, string | null>): boolean {
  return Object.entries(hashes).every(([path, before]) => sha256(path) === before)
}

function directoryFingerprint(root: string): string | null {
  if (!existsSync(root)) return null
  const files: string[] = []
  const walk = (directory: string): void => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name)
      if (entry.isDirectory()) walk(path)
      else files.push(path)
    }
  }
  walk(root)
  const hash = createHash('sha256')
  for (const path of files.sort()) hash.update(path).update(readFileSync(path))
  return hash.digest('hex')
}

async function portClosed(port: number): Promise<boolean> {
  try {
    await fetch(`http://127.0.0.1:${port}/json/version`, { signal: AbortSignal.timeout(300) })
    return false
  } catch {
    return true
  }
}

function processExists(pid: number): boolean {
  if (process.platform === 'win32') {
    const result = spawnSync('tasklist', ['/FI', `PID eq ${pid}`, '/FO', 'CSV', '/NH'], {
      encoding: 'utf8',
      windowsHide: true
    })
    return result.stdout.includes(`"${pid}"`)
  }
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

export interface CleanupProof {
  websocket_closed: boolean
  pending_cdp_requests: number
  electron_pid: number
  electron_process_gone: boolean
  appserver_pid: number | null
  appserver_process_gone: boolean
  workspace_worktree_removed: boolean
  debug_port: number
  debug_port_closed: boolean
  temp_root_removed: boolean
  source_config_unchanged: boolean
  source_skills_unchanged: boolean
  lease_count: number | null
  pending_rpc_count: number | null
  passed: boolean
}

export interface HarnessOptions {
  artifactDir: string
  fakeAppserver: boolean
  /** Real artifact tests need an empty workspace; repo audits need a worktree. */
  workspaceMode?: 'git-worktree' | 'empty'
  width?: number
  height?: number
  extraEnv?: NodeJS.ProcessEnv
}

export class DesktopCdpHarness {
  readonly artifactDir: string
  readonly tempRoot: string
  readonly profileDir: string
  readonly dataDir: string
  readonly workspaceDir: string
  readonly skillDir: string
  readonly stdout: Array<{ at_ms: number; line: string }> = []
  readonly stderr: Array<{ at_ms: number; line: string }> = []
  readonly startedAt = Date.now()
  private readonly sourceHashes: Record<string, string | null>
  private readonly sourceSkillRoot: string
  private readonly sourceSkillHash: string | null
  private readonly options: HarnessOptions
  private readonly workspaceIsGitWorktree: boolean
  private child: ChildProcess | null = null
  private childExit: { code: number | null; signal: NodeJS.Signals | null } | null = null
  private socket: WebSocket | null = null
  private sequence = 0
  private pending = new Map<number, { resolve: (value: any) => void; reject: (error: Error) => void }>()
  debugPort = 0

  constructor(options: HarnessOptions) {
    this.options = options
    this.workspaceIsGitWorktree = options.workspaceMode !== 'empty'
    this.artifactDir = resolve(options.artifactDir)
    mkdirSync(this.artifactDir, { recursive: true })
    this.tempRoot = mkdtempSync(join(tmpdir(), 'rxycode-desktop-cd-'))
    this.profileDir = join(this.tempRoot, 'electron-profile')
    this.dataDir = join(this.tempRoot, 'rxycode-data')
    this.workspaceDir = join(this.tempRoot, 'workspace')
    this.skillDir = join(this.tempRoot, 'skills')
    for (const path of [this.profileDir, this.dataDir]) {
      mkdirSync(path, { recursive: true })
    }
    mkdirSync(this.skillDir, { recursive: true })
    if (this.workspaceIsGitWorktree) {
      const worktree = spawnSync(
        'git',
        ['worktree', 'add', '--detach', this.workspaceDir, 'HEAD'],
        { cwd: repositoryDir, windowsHide: true, encoding: 'utf8' }
      )
      if (worktree.status !== 0) {
        throw new Error(`failed to create isolated test worktree: ${worktree.stderr}`)
      }
    } else {
      // A generated app must not receive RxyCode's own source tree as its
      // initial project.  Exposing that tree makes the model spend turns
      // indexing unrelated files and bloats the first tool result/context.
      mkdirSync(this.workspaceDir, { recursive: true })
    }
    this.sourceHashes = copyIsolatedConfiguration(this.dataDir)
    this.sourceSkillRoot = resolve(
      process.env.RXYCODE_TEST_SKILL_SOURCE ??
        join(homedir(), '.codex', 'skills', 'ui-ux-pro-max')
    )
    this.sourceSkillHash = directoryFingerprint(this.sourceSkillRoot)
    if (this.sourceSkillHash !== null) {
      cpSync(this.sourceSkillRoot, join(this.skillDir, 'ui-ux-pro-max'), { recursive: true })
    }
  }

  async start(): Promise<void> {
    if (!existsSync(vite)) throw new Error(`electron-vite missing: ${vite}`)
    const spawnEnv = {
      ...process.env,
      ...this.options.extraEnv,
      RXYCODE_REPO_DIR: repositoryDir,
      RXYCODE_DATA_DIR: this.dataDir,
      RXYCODE_DESKTOP_USER_DATA: this.profileDir,
      RXYCODE_DESKTOP_WIDTH: String(this.options.width ?? 1280),
      RXYCODE_DESKTOP_HEIGHT: String(this.options.height ?? 800),
      RXYCODE_SKILLS_DIR: this.skillDir,
      RXYCODE_SKILLS_DIRS: this.skillDir,
      ...(this.options.fakeAppserver ? { RXYCODE_DESKTOP_FAKE_APPSERVER: '1' } : {})
    }
    spawnEnv.NODE_OPTIONS = electronViteNodeOptions(spawnEnv.NODE_OPTIONS)
    this.child = spawn(
      process.execPath,
      electronViteDevArgs(this.profileDir),
      {
        cwd: desktopAppDir,
        env: spawnEnv,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe']
      }
    )
    const capture = (target: Array<{ at_ms: number; line: string }>) => (chunk: Buffer): void => {
      for (const line of chunk.toString('utf8').split(/\r?\n/).filter(Boolean)) {
        target.push({ at_ms: Date.now() - this.startedAt, line })
      }
    }
    this.child.stdout?.on('data', capture(this.stdout))
    this.child.stderr?.on('data', capture(this.stderr))
    this.child.once('exit', (code, signal) => {
      this.childExit = { code, signal }
    })

    const activePortFile = join(this.profileDir, 'DevToolsActivePort')
    this.debugPort = await waitFor(async () => {
      if (this.childExit !== null) {
        const stderr = this.stderr.map((entry) => entry.line).join('\n')
        const oom = /heap out of memory/i.test(stderr)
        throw new Error(
          `Electron/vite exited ${this.childExit.code ?? this.childExit.signal} before DevToolsActivePort` +
          `${oom ? ' (JavaScript heap out of memory)' : ''}` +
          (stderr.length > 0 ? `: ${stderr.slice(-1500)}` : '')
        )
      }
      if (!existsSync(activePortFile)) return null
      const value = Number(readFileSync(activePortFile, 'utf8').split(/\r?\n/)[0])
      return Number.isInteger(value) && value > 0 ? value : null
    }, 90_000, 'dynamic DevToolsActivePort')
    const target = await waitFor(async () => {
      try {
        const pages = await (
          await fetch(`http://127.0.0.1:${this.debugPort}/json/list`)
        ).json() as DevToolsPageTarget[]
        return selectRendererTarget(pages)
      } catch {
        return null
      }
    }, 30_000, 'Electron page target')
    this.socket = new WebSocket(target)
    await new Promise<void>((resolveOpen, rejectOpen) => {
      this.socket!.onopen = () => resolveOpen()
      this.socket!.onerror = () => rejectOpen(new Error('CDP websocket failed'))
    })
    this.socket.onmessage = (event) => {
      const message = JSON.parse(String(event.data)) as { id?: number; error?: unknown; result?: unknown }
      if (message.id === undefined) return
      const entry = this.pending.get(message.id)
      if (entry === undefined) return
      this.pending.delete(message.id)
      if (message.error !== undefined) entry.reject(new Error(JSON.stringify(message.error)))
      else entry.resolve(message.result)
    }
    await this.send('Runtime.enable')
    await this.send('Page.enable')
    // A newly-created Electron profile can briefly expose a page target before
    // its storage origin is ready. Wait for the renderer, then write the
    // isolated workspace; retry once after a reload instead of leaking a
    // partially initialized run into the next stress round.
    await this.send('Page.reload', { ignoreCache: true })
    await this.waitForSelector('[data-testid="task-command-center"]', 30_000)
    const setWorkspace = (): Promise<unknown> => this.evaluate(`localStorage.setItem(
      'rxycode.desktop.workspaceSettings.v1',
      JSON.stringify({workspaceRoot:${JSON.stringify(this.workspaceDir)}})
    )`)
    try {
      await setWorkspace()
    } catch (firstError) {
      await this.send('Page.reload', { ignoreCache: true })
      await this.waitForSelector('[data-testid="task-command-center"]', 30_000)
      try {
        await setWorkspace()
      } catch {
        throw new Error(`renderer storage origin was not ready: ${firstError instanceof Error ? firstError.message : String(firstError)}`)
      }
    }
    await this.send('Page.reload', { ignoreCache: true })
    await this.waitForSelector('[data-testid="task-command-center"]', 30_000)
  }

  send(method: string, params: unknown = {}, timeoutMs = 30_000): Promise<any> {
    if (this.socket === null || this.socket.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('CDP websocket is not open'))
    }
    return new Promise((resolveSend, rejectSend) => {
      const id = ++this.sequence
      const timer = setTimeout(() => {
        this.pending.delete(id)
        rejectSend(new Error(`CDP request timed out after ${timeoutMs}ms: ${method}`))
      }, timeoutMs)
      this.pending.set(id, {
        resolve: (value) => {
          clearTimeout(timer)
          resolveSend(value)
        },
        reject: (error) => {
          clearTimeout(timer)
          rejectSend(error)
        }
      })
      try {
        this.socket!.send(JSON.stringify({ id, method, params }))
      } catch (error) {
        clearTimeout(timer)
        this.pending.delete(id)
        rejectSend(error instanceof Error ? error : new Error(String(error)))
      }
    })
  }

  async evaluate<T = any>(expression: string): Promise<T> {
    const response = await this.send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true
    })
    if (response.exceptionDetails !== undefined) {
      throw new Error(JSON.stringify(response.exceptionDetails))
    }
    return response.result?.value as T
  }

  has(selector: string): Promise<boolean> {
    return this.evaluate(`Boolean(document.querySelector(${JSON.stringify(selector)}))`)
  }

  async waitForSelector(selector: string, timeoutMs = 30_000): Promise<void> {
    await waitFor(async () => (await this.has(selector)) ? true : null, timeoutMs, selector)
  }

  async typePrompt(text: string): Promise<void> {
    await this.evaluate(`(() => {
      const element = document.querySelector('[data-testid="composer-input"]');
      if (!(element instanceof HTMLTextAreaElement)) throw new Error('composer textarea missing');
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
      setter.call(element, ${JSON.stringify(text)});
      element.dispatchEvent(new Event('input', { bubbles: true }));
    })()`)
  }

  async pressKey(key: string, options: { shiftKey?: boolean } = {}): Promise<void> {
    await this.evaluate(`(() => {
      const element = document.querySelector('[data-testid="composer-input"]');
      if (!(element instanceof HTMLTextAreaElement)) throw new Error('composer input missing');
      element.focus();
      element.dispatchEvent(new KeyboardEvent('keydown', {
        key: ${JSON.stringify(key)},
        code: ${JSON.stringify(key)},
        bubbles: true,
        cancelable: true,
        shiftKey: ${Boolean(options.shiftKey)}
      }));
    })()`)
  }

  async screenshot(relativePath: string): Promise<string> {
    const path = screenshotPath(this.artifactDir, relativePath)
    mkdirSync(dirname(path), { recursive: true })
    // A long T09 transcript can stall one 10s capture. Retry at the same
    // bound instead of raising it; a blocked renderer still fails the run.
    const image = await captureScreenshotWithRetry((method, params, timeoutMs) => this.send(method, params, timeoutMs))
    writeFileSync(path, Buffer.from(image.data, 'base64'))
    return path
  }

  async setViewport(width: number, height: number): Promise<void> {
    await this.send('Emulation.setDeviceMetricsOverride', {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: false
    })
    await delay(100)
  }

  async setZoom(factor: number): Promise<void> {
    if (!Number.isFinite(factor) || factor < 1 || factor > 3) {
      throw new Error(`zoom factor must be between 1 and 3, received ${factor}`)
    }
    await this.send('Emulation.setPageScaleFactor', { pageScaleFactor: factor })
    await delay(100)
  }

  async domSnapshot(): Promise<Record<string, unknown>> {
    return this.evaluate(`(() => ({
      bodyText: document.body.innerText,
      viewport: { width: innerWidth, height: innerHeight },
      shell: { scrollY, scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth, scrollHeight: document.documentElement.scrollHeight, clientHeight: document.documentElement.clientHeight },
      activeSession: document.querySelector('.session-item.active .session-id')?.textContent ?? null,
      runningTools: document.querySelectorAll('.tool-card.running').length,
      childRows: Array.from(document.querySelectorAll('.agent-row')).map((row) => row.textContent),
      dialogs: Array.from(document.querySelectorAll('[role=dialog]')).map((dialog) => dialog.textContent)
    }))()`)
  }

  private terminateOwnProcessTree(): void {
    const child = this.child
    if (child?.pid === undefined) return
    if (process.platform === 'win32') {
      spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], {
        windowsHide: true,
        stdio: 'ignore'
      })
    } else {
      try { process.kill(-child.pid, 'SIGKILL') } catch {
        try { process.kill(child.pid, 'SIGKILL') } catch {}
      }
    }
  }

  async cleanup(): Promise<CleanupProof> {
    const pid = this.child?.pid ?? -1
    let pendingRpcCount: number | null = null
    let leaseCount: number | null = null
    let appserverPid: number | null = null
    let appserverLogs: string[] = []
    try {
      const diagnostics = await this.evaluate(`(async () => {
        const pendingText = document.querySelector('[data-testid="diagnostics-pending-rpc"]')?.textContent ?? '';
        const rootSessionId = document.querySelector('.session-item.active .session-id')?.textContent?.trim() ?? '';
        const info = await window.api.appserver.getInfo();
        const id = 'cd-cleanup-' + Date.now();
        const capability = await new Promise((resolve) => {
          const timeout = setTimeout(() => { off(); resolve(null); }, 3000);
          const off = window.api.appserver.onLine((line) => {
            try {
              const message = JSON.parse(line);
              if (message.id !== id) return;
              clearTimeout(timeout); off(); resolve(message.result ?? null);
            } catch {}
          });
          window.api.appserver.sendLine(JSON.stringify({
            jsonrpc:'2.0', id, method:'subagents/capability',
            params: rootSessionId ? {root_session_id: rootSessionId} : {}
          }));
        });
        return {
          pendingRpcCount: Number((pendingText.match(/\\d+/) || [])[0] ?? NaN),
          appserverPid: info.appserverPid ?? null,
          leaseCount: capability && Number.isFinite(capability.active_lease_count)
            ? capability.active_lease_count : null
        };
      })()`)
      pendingRpcCount = Number.isFinite(diagnostics.pendingRpcCount) ? diagnostics.pendingRpcCount : null
      appserverPid = Number.isFinite(diagnostics.appserverPid) ? diagnostics.appserverPid : null
      leaseCount = diagnostics.leaseCount
      appserverLogs = await this.evaluate<string[]>(`window.__rxyCdAppserverLogs ?? []`)
    } catch {}
    this.socket?.close()
    for (const entry of this.pending.values()) entry.reject(new Error('harness cleanup'))
    this.pending.clear()
    this.terminateOwnProcessTree()
    const waitUntilGone = async (targetPid: number | null): Promise<boolean> => {
      if (targetPid === null || targetPid <= 0) return true
      try {
        await waitFor(async () => !processExists(targetPid) ? true : null, 5_000, `process ${targetPid} exit`)
        return true
      } catch {
        return false
      }
    }
    const processGone = await waitUntilGone(pid)
    const appserverProcessGone = await waitUntilGone(appserverPid)
    const debugClosed = this.debugPort <= 0 || await portClosed(this.debugPort)
    let tempRemoved = false
    let workspaceWorktreeRemoved = !this.workspaceIsGitWorktree
    if (this.workspaceIsGitWorktree) {
      const worktreeRemoval = spawnSync(
        'git',
        ['worktree', 'remove', '--force', this.workspaceDir],
        { cwd: repositoryDir, windowsHide: true, encoding: 'utf8' }
      )
      workspaceWorktreeRemoved = worktreeRemoval.status === 0 && !existsSync(this.workspaceDir)
    }
    try {
      rmSync(this.tempRoot, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 })
      tempRemoved = !existsSync(this.tempRoot)
    } catch {
      tempRemoved = false
    }
    const proof: CleanupProof = {
      websocket_closed: this.socket === null || this.socket.readyState !== WebSocket.OPEN,
      pending_cdp_requests: this.pending.size,
      electron_pid: pid,
      electron_process_gone: processGone,
      appserver_pid: appserverPid,
      appserver_process_gone: appserverProcessGone,
      workspace_worktree_removed: workspaceWorktreeRemoved,
      debug_port: this.debugPort,
      debug_port_closed: debugClosed,
      temp_root_removed: tempRemoved,
      source_config_unchanged: sourceConfigurationUnchanged(this.sourceHashes),
      source_skills_unchanged: directoryFingerprint(this.sourceSkillRoot) === this.sourceSkillHash,
      lease_count: leaseCount,
      pending_rpc_count: pendingRpcCount,
      passed: false
    }
    proof.passed =
      proof.websocket_closed &&
      proof.pending_cdp_requests === 0 &&
      proof.electron_process_gone &&
      proof.appserver_process_gone &&
      proof.workspace_worktree_removed &&
      proof.debug_port_closed &&
      proof.temp_root_removed &&
      proof.source_config_unchanged &&
      proof.source_skills_unchanged &&
      proof.lease_count === 0 &&
      proof.pending_rpc_count === 0
    writeFileSync(
      join(this.artifactDir, 'process-output.json'),
      JSON.stringify({ stdout: this.stdout, stderr: this.stderr, appserver: appserverLogs }, null, 2)
    )
    writeFileSync(join(this.artifactDir, 'cleanup-proof.json'), JSON.stringify(proof, null, 2))
    return proof
  }
}
