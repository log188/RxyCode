#!/usr/bin/env node
/**
 * Phase4 Desktop stress driver: 15 user-shaped business flows in a real
 * Electron window.  The deterministic appserver isolates renderer defects
 * from paid model variance while replaying protocol events for tools, Skills,
 * MCP, approvals, cancellation, errors, multi-session navigation and scroll.
 */
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const appDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const outDir = resolve(process.argv[2] ?? join(appDir, '..', '..', 'artifacts', 'desktop-stress'))
const vite = join(appDir, 'node_modules', 'electron-vite', 'bin', 'electron-vite.js')
const profile = mkdtempSync(join(tmpdir(), 'rxycode-desktop-stress-'))
const dataDir = mkdtempSync(join(tmpdir(), 'rxycode-desktop-stress-data-'))
const cases = [
  '审计一个 Python 服务的启动链路：读取配置、检索调用点、列出风险，并给出可执行验证命令。',
  '为订单缓存模块实现 TTL 策略：分析现有测试，读取代码，写出修复，并运行回归测试。',
  '调查生产错误日志：搜索相关文件和调用链，形成根因、影响范围、修复优先级报告。',
  '使用 coding-workflow Skill 规划一个 API 迁移：先加载 Skill，读取契约文件，输出分阶段清单。',
  '通过 workspace MCP 检索三个业务文档，交叉核对字段命名，并写一份兼容性摘要。',
  '调研竞品功能：调用 websearch、读取本地需求、写出带来源的产品决策记录。',
  '检查 Git 工作区和 CI 配置：搜索失败测试，读取 workflow，给出最小修复方案与验证命令。',
  '审查支付模块的敏感变更：读取代码、搜索密钥使用点、运行静态检查并输出风险表。',
  '执行需要写入 approval 的数据库迁移预检，说明变更范围并等待用户确认。 approval',
  '执行第二个需要写入 approval 的临时文件清理，确认后保存一次性授权规则。 approval',
  '生成较长的多工具分析并在会话之间切换，确认历史会话不串消息和工具卡。',
  '启动耗时依赖诊断，在流式输出和运行工具卡出现后由用户取消。 slow demo',
  '模拟外部 MCP 服务失败：显示错误、停止运行，并允许用户继续创建新会话。 fail demo',
  '分析一个多文件重构：调用 Skill、MCP 搜索、读取、写入和测试工具，输出实施摘要。',
  '完成发布前检查：搜索变更、读取版本清单、运行命令验证、写出最终上线说明。'
]

const delay = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))
async function waitFor<T>(probe: () => Promise<T | null>, timeout: number, label: string): Promise<T> {
  const until = Date.now() + timeout
  while (Date.now() < until) { const found = await probe(); if (found !== null) return found; await delay(150) }
  throw new Error(`timeout: ${label}`)
}

async function main(): Promise<void> {
  if (!existsSync(vite)) throw new Error(`missing electron-vite: ${vite}`)
  mkdirSync(outDir, { recursive: true })
  const dev = spawn(process.execPath, [vite, 'dev', '--', '--port=0', '--remote-debugging-port=0', `--user-data-dir=${profile}`], {
    cwd: appDir,
    env: {
      ...process.env,
      RXYCODE_DESKTOP_FAKE_APPSERVER: '1',
      RXYCODE_DESKTOP_WIDTH: '1100',
      RXYCODE_DESKTOP_HEIGHT: '760',
      RXYCODE_DATA_DIR: dataDir,
      RXYCODE_DESKTOP_USER_DATA: profile,
      RXYCODE_REPO_DIR: resolve(appDir, '..', '..')
    },
    windowsHide: true, stdio: ['ignore', 'pipe', 'pipe']
  })
  let ws: WebSocket | null = null
  try {
    const activePortFile = join(profile, 'DevToolsActivePort')
    const debugPort = await waitFor(async () => {
      if (!existsSync(activePortFile)) return null
      const value = Number(readFileSync(activePortFile, 'utf8').split(/\r?\n/)[0])
      return Number.isInteger(value) && value > 0 ? value : null
    }, 90_000, 'Electron DevTools port')
    const target = await waitFor(async () => {
      try {
        const pages = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json() as Array<{ type: string; webSocketDebuggerUrl?: string }>
        return pages.find((p) => p.type === 'page' && p.webSocketDebuggerUrl !== undefined)?.webSocketDebuggerUrl ?? null
      } catch { return null }
    }, 30_000, 'Electron CDP')
    ws = new WebSocket(target)
    await new Promise<void>((ok, bad) => { ws!.onopen = () => ok(); ws!.onerror = () => bad(new Error('CDP websocket')) })
    let id = 0
    const pending = new Map<number, (v: any) => void>()
    ws.onmessage = (e) => { const m = JSON.parse(String(e.data)); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } }
    const send = (method: string, params: unknown = {}): Promise<any> => new Promise((ok, bad) => { const n = ++id; pending.set(n, (m) => m.error ? bad(new Error(JSON.stringify(m.error))) : ok(m.result)); ws!.send(JSON.stringify({ id: n, method, params })) })
    const evalJs = async (expression: string): Promise<any> => { const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails)); return r.result?.value }
    const exists = (selector: string): Promise<boolean> => evalJs(`Boolean(document.querySelector(${JSON.stringify(selector)}))`)
    const waitSel = (selector: string, label: string): Promise<true> => waitFor(async () => (await exists(selector)) ? true : null, 30_000, label)
    const openNavigation = async (): Promise<void> => {
      await evalJs(`document.querySelector('.nav-toggle:not(:disabled)')?.click()`)
      await waitSel('.nav-sheet.open .new-session:not(:disabled)', 'task navigation')
    }
    const closeNavigation = async (): Promise<void> => {
      if (await exists('.nav-sheet.open')) await evalJs(`document.querySelector('.nav-sheet.open .sheet-close')?.click()`)
    }
    const typePrompt = async (text: string): Promise<void> => { await evalJs(`(() => { const e=document.querySelector('.composer textarea'); const s=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set; s.call(e,${JSON.stringify(text)}); e.dispatchEvent(new Event('input',{bubbles:true})); })()`); await delay(100) }
    const shot = async (name: string): Promise<void> => { const r = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(join(outDir, name), Buffer.from(r.data, 'base64')) }
    await send('Runtime.enable')
    await waitSel('.nav-toggle:not(:disabled)', 'renderer ready')
    const results: Array<Record<string, unknown>> = []
    for (let idx = 0; idx < cases.length; idx += 1) {
      const number = String(idx + 1).padStart(2, '0'); const prompt = `[DTS-${number}] ${cases[idx]}`; const executionPrompt = [8, 9].includes(idx) ? `${prompt} demo` : prompt; const started = Date.now()
      console.log(`DTS-${number} START`)
      await openNavigation()
      await evalJs(`document.querySelector('.nav-sheet.open .new-session')?.click()`)
      await waitFor(async () => (await evalJs(`document.querySelectorAll('.nav-sheet .session-item').length`)) === idx + 1 ? true : null, 20_000, `DTS-${number} session`)
      await closeNavigation()
      await waitSel('[data-testid="composer-input"]:not(:disabled)', `DTS-${number} composer ready`)
      await typePrompt(executionPrompt)
      try {
        await waitFor(async () => (await evalJs(`Boolean(document.querySelector('[data-testid="composer-send"]:not(:disabled)'))`)) ? true : null, 20_000, `DTS-${number} send button`)
      } catch (error) {
        const debug = await evalJs(`(() => ({
          status: document.querySelector('.connection-status')?.textContent ?? '',
          input: document.querySelector('[data-testid="composer-input"]')?.value ?? '',
          inputDisabled: document.querySelector('[data-testid="composer-input"]')?.disabled ?? null,
          sendDisabled: document.querySelector('[data-testid="composer-send"]')?.disabled ?? null,
          active: document.querySelector('.session-item.active .session-id')?.textContent ?? '',
          runState: document.querySelector('.task-status')?.textContent ?? document.querySelector('.session-item.active .session-state')?.textContent ?? ''
        }))()`)
        throw new Error(`${error instanceof Error ? error.message : String(error)}; composer=${JSON.stringify(debug)}`)
      }
      await evalJs(`document.querySelector('[data-testid="composer-send"]')?.click()`)
      let status = 'succeeded'
      if (executionPrompt.includes('approval demo')) { await waitSel('.approval-dialog', `DTS-${number} approval`); await evalJs(`document.querySelector('.approve, .save-rule')?.click()`); await waitFor(async () => !(await exists('.approval-dialog')) ? true : null, 20_000, `DTS-${number} approval completion`) }
      else if (prompt.includes('slow demo')) { await waitFor(async () => (await exists('.tool-activity.running')) ? true : null, 5_000, `DTS-${number} running tool`); await evalJs(`document.querySelector('[data-testid="composer-stop"]')?.click()`); await waitFor(async () => !(await exists('.running-indicator')) ? true : null, 5_000, `DTS-${number} cancel`); status = 'cancelled' }
      else if (prompt.includes('fail demo')) { await waitSel('.timeline-error, [role="alert"]', `DTS-${number} error state`); status = 'failed' }
      else { await waitFor(async () => (await exists('[data-testid="final-answer"]')) ? true : null, 30_000, `DTS-${number} completion`) }
      await delay(150)
      const snapshot = await evalJs(`(() => ({ final: document.querySelector('[data-testid="final-answer"] .timeline-prose')?.textContent ?? '', error: document.querySelector('.timeline-error')?.textContent ?? '', tools: Array.from(document.querySelectorAll('.tool-activity')).map(x=>({name:x.querySelector('.activity-label')?.textContent,status:Array.from(x.classList).find((name) => ['running','ok','error','recovering'].includes(name)) ?? 'unknown'})), scrollTop: document.querySelector('.chat-area')?.scrollTop ?? 0, scrollHeight: document.querySelector('.chat-area')?.scrollHeight ?? 0, pageScrollY: window.scrollY, pageHeight: document.documentElement.scrollHeight, viewportHeight: window.innerHeight, topbarHeight: document.querySelector('.topbar')?.getBoundingClientRect().height ?? 0, composerHeight: document.querySelector('.composer')?.getBoundingClientRect().height ?? 0 }))()`)
      if (status === 'succeeded' && !executionPrompt.includes('approval demo')) {
        if (!String(snapshot.final).includes(`DTS-${number}`)) throw new Error(`DTS-${number} final answer belongs to another session`)
        if (!Array.isArray(snapshot.tools) || snapshot.tools.length !== 3) throw new Error(`DTS-${number} expected exactly three session-local tool activities`)
        if (snapshot.tools.some((tool: { status: string }) => tool.status !== 'ok')) throw new Error(`DTS-${number} left a tool card unfinished`)
      }
      if (status === 'cancelled') {
        if (String(snapshot.final).includes(`DTS-${number} 已完成`)) throw new Error(`DTS-${number} rendered a completed answer after cancellation`)
        if (!Array.isArray(snapshot.tools) || !snapshot.tools.some((tool: { status: string }) => tool.status === 'error')) throw new Error(`DTS-${number} did not mark its interrupted tool card`)
      }
      if (status === 'failed' && !String(snapshot.error).includes('demo failure')) throw new Error(`DTS-${number} did not retain its error result`)
      if (Number(snapshot.pageScrollY) !== 0 || Number(snapshot.pageHeight) > Number(snapshot.viewportHeight)) throw new Error(`DTS-${number} allowed the desktop shell to scroll instead of keeping its panes fixed`)
      if (Number(snapshot.topbarHeight) < 40 || Number(snapshot.composerHeight) < 80) throw new Error(`DTS-${number} let session growth collapse the fixed desktop chrome`)
      results.push({ id: `DTS-${number}`, prompt, status, duration_ms: Date.now() - started, token_usage: { input: null, output: null, cache_hit: null, note: 'deterministic UI transport has no provider usage payload' }, ...snapshot })
      console.log(`DTS-${number} ${status}`)
      if ([4, 9, 14].includes(idx)) await shot(`DTS-${number}.png`)
    }
    await openNavigation()
    await evalJs(`document.querySelectorAll('.nav-sheet .session-item')[0]?.click()`)
    await waitFor(async () => (await evalJs(`document.querySelector('.timeline-prompt')?.textContent?.includes('[DTS-01]') ?? false`)) ? true : null, 10_000, 'DTS session isolation')
    if (await evalJs(`document.querySelector('.timeline-prompt')?.textContent?.includes('[DTS-15]') ?? false`)) throw new Error('DTS session isolation leaked the final session into the first session')
    writeFileSync(join(outDir, 'desktop-stress-results.json'), JSON.stringify({ generated_at: new Date().toISOString(), transport: 'electron-vite + deterministic appserver', results }, null, 2))
    console.log(`DESKTOP_STRESS_OK ${outDir}`)
  } finally {
    ws?.close(); if (process.platform === 'win32') spawnSync('taskkill', ['/pid', String(dev.pid), '/T', '/F'], { stdio: 'ignore' }); else { try { process.kill(dev.pid, 'SIGKILL') } catch {} }
    await delay(400)
    try { rmSync(profile, { recursive: true, force: true, maxRetries: 3 }) } catch {}
    try { rmSync(dataDir, { recursive: true, force: true, maxRetries: 3 }) } catch {}
  }
}
void main()
