import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import { createHash } from 'node:crypto'
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync
} from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const desktopAppDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
export const repositoryDir = resolve(process.env.RXYCODE_REPO_DIR ?? resolve(desktopAppDir, '..', '..'))
const vite = join(desktopAppDir, 'node_modules', 'electron-vite', 'bin', 'electron-vite.js')

const delay = (ms: number): Promise<void> => new Promise((resolveDelay) => setTimeout(resolveDelay, ms))

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
  lease_count: number | null
  pending_rpc_count: number | null
  passed: boolean
}

export interface HarnessOptions {
  artifactDir: string
  fakeAppserver: boolean
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
  readonly stdout: Array<{ at_ms: number; line: string }> = []
  readonly stderr: Array<{ at_ms: number; line: string }> = []
  readonly startedAt = Date.now()
  private readonly sourceHashes: Record<string, string | null>
  private readonly options: HarnessOptions
  private child: ChildProcess | null = null
  private socket: WebSocket | null = null
  private sequence = 0
  private pending = new Map<number, { resolve: (value: any) => void; reject: (error: Error) => void }>()
  debugPort = 0

  constructor(options: HarnessOptions) {
    this.options = options
    this.artifactDir = resolve(options.artifactDir)
    mkdirSync(this.artifactDir, { recursive: true })
    this.tempRoot = mkdtempSync(join(tmpdir(), 'rxycode-desktop-cd-'))
    this.profileDir = join(this.tempRoot, 'electron-profile')
    this.dataDir = join(this.tempRoot, 'rxycode-data')
    this.workspaceDir = join(this.tempRoot, 'workspace')
    for (const path of [this.profileDir, this.dataDir]) {
      mkdirSync(path, { recursive: true })
    }
    const worktree = spawnSync(
      'git',
      ['worktree', 'add', '--detach', this.workspaceDir, 'HEAD'],
      { cwd: repositoryDir, windowsHide: true, encoding: 'utf8' }
    )
    if (worktree.status !== 0) {
      throw new Error(`failed to create isolated test worktree: ${worktree.stderr}`)
    }
    this.sourceHashes = copyIsolatedConfiguration(this.dataDir)
  }

  async start(): Promise<void> {
    if (!existsSync(vite)) throw new Error(`electron-vite missing: ${vite}`)
    this.child = spawn(
      process.execPath,
      [vite, 'dev', '--', '--remote-debugging-port=0', `--user-data-dir=${this.profileDir}`],
      {
        cwd: desktopAppDir,
        env: {
          ...process.env,
          ...this.options.extraEnv,
          RXYCODE_REPO_DIR: repositoryDir,
          RXYCODE_DATA_DIR: this.dataDir,
          RXYCODE_DESKTOP_USER_DATA: this.profileDir,
          RXYCODE_DESKTOP_WIDTH: String(this.options.width ?? 1280),
          RXYCODE_DESKTOP_HEIGHT: String(this.options.height ?? 800),
          ...(this.options.fakeAppserver ? { RXYCODE_DESKTOP_FAKE_APPSERVER: '1' } : {})
        },
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

    const activePortFile = join(this.profileDir, 'DevToolsActivePort')
    this.debugPort = await waitFor(async () => {
      if (!existsSync(activePortFile)) return null
      const value = Number(readFileSync(activePortFile, 'utf8').split(/\r?\n/)[0])
      return Number.isInteger(value) && value > 0 ? value : null
    }, 90_000, 'dynamic DevToolsActivePort')
    const target = await waitFor(async () => {
      try {
        const pages = await (
          await fetch(`http://127.0.0.1:${this.debugPort}/json/list`)
        ).json() as Array<{ type: string; webSocketDebuggerUrl?: string }>
        return pages.find((page) => page.type === 'page')?.webSocketDebuggerUrl ?? null
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
    await this.evaluate(`localStorage.setItem(
      'rxycode.desktop.workspaceSettings.v1',
      JSON.stringify({workspaceRoot:${JSON.stringify(this.workspaceDir)}})
    )`)
    await this.send('Page.reload', { ignoreCache: true })
    await this.waitForSelector('[data-testid="task-command-center"]', 30_000)
  }

  send(method: string, params: unknown = {}): Promise<any> {
    if (this.socket === null || this.socket.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('CDP websocket is not open'))
    }
    return new Promise((resolveSend, rejectSend) => {
      const id = ++this.sequence
      this.pending.set(id, { resolve: resolveSend, reject: rejectSend })
      this.socket!.send(JSON.stringify({ id, method, params }))
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
      const element = document.querySelector('.composer textarea');
      if (!(element instanceof HTMLTextAreaElement)) throw new Error('composer textarea missing');
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
      setter.call(element, ${JSON.stringify(text)});
      element.dispatchEvent(new Event('input', { bubbles: true }));
    })()`)
  }

  async screenshot(relativePath: string): Promise<string> {
    const path = join(this.artifactDir, relativePath)
    mkdirSync(dirname(path), { recursive: true })
    const image = await this.send('Page.captureScreenshot', { format: 'png' })
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
    const worktreeRemoval = spawnSync(
      'git',
      ['worktree', 'remove', '--force', this.workspaceDir],
      { cwd: repositoryDir, windowsHide: true, encoding: 'utf8' }
    )
    const workspaceWorktreeRemoved = worktreeRemoval.status === 0 && !existsSync(this.workspaceDir)
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
