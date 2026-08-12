#!/usr/bin/env node
/** Focused real-Electron regression suite for the Desktop shell. */
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { DesktopCdpHarness, waitFor } from './cdp-harness.mts'

const artifactDir = process.env.RXYCODE_GUI_ARTIFACTS ?? join(process.cwd(), 'artifacts', `gui-ux-${Date.now()}`)
mkdirSync(artifactDir, { recursive: true })

async function main(): Promise<void> {
  const harness = new DesktopCdpHarness({
    artifactDir,
    fakeAppserver: true,
    width: 1440,
    height: 900
  })
  let cleaned = false
  const pendingRpc = async (): Promise<number> => harness.evaluate<number>(`Number((document.querySelector('[data-testid="diagnostics-pending-rpc"]')?.textContent ?? '').match(/\\d+/)?.[0] ?? 0)`)
  const results: Array<{ id: string; status: 'passed' | 'failed'; detail?: string }> = []
  const check = async (id: string, action: () => Promise<void>): Promise<void> => {
    try {
      await action()
      results.push({ id, status: 'passed' })
    } catch (error) {
      results.push({ id, status: 'failed', detail: error instanceof Error ? error.message : String(error) })
    }
  }
  try {
    await harness.start()
    await harness.evaluate(`(() => {
      window.__rxyGuiUxLines = [];
      window.api.appserver.onLine((line) => window.__rxyGuiUxLines.push(line));
    })()`)
    await harness.waitForSelector('.nav-toggle:not(:disabled)', 60_000)
    await harness.evaluate(`document.querySelector('.nav-toggle:not(:disabled)')?.click()`)
    await harness.waitForSelector('.nav-sheet.open .new-session:not(:disabled)', 5_000)
    await harness.evaluate(`document.querySelector('.nav-sheet.open .new-session:not(:disabled)')?.click()`)
    await harness.waitForSelector('[data-testid="composer-input"]:not(:disabled)', 20_000)
    await harness.evaluate(`document.querySelector('.nav-sheet.open .sheet-close')?.click()`)

    await check('UX-01 composer structure', async () => {
      if (!(await harness.has('[data-testid="composer-surface"]'))) throw new Error('Codex-like composer surface missing')
      if (!(await harness.has('[data-testid="composer-send"]'))) throw new Error('send arrow missing')
      if (!(await harness.has('[data-testid="composer-permission-mode"]'))) throw new Error('task permission switch missing')
    })
    await check('UX-02 Enter submits', async () => {
      await harness.typePrompt('enter sends a real task')
      await harness.pressKey('Enter')
      await harness.waitForSelector('[data-testid="composer-stop"]', 10_000)
      await waitFor(async () => (await harness.has('[data-testid="composer-stop"]')) ? null : true, 20_000, 'Enter task terminal')
    })
    await check('UX-03 approval closes after decision', async () => {
      await harness.typePrompt('approval demo')
      await harness.pressKey('Enter')
      await waitFor(async () => (await harness.has('.approval-dialog .approve')) ? true : null, 20_000, 'approval dialog')
      await harness.evaluate(`document.querySelector('.approval-dialog .approve')?.click()`)
      await waitFor(async () => (await harness.has('.approval-dialog')) ? null : true, 2_000, 'approval dialog close')
      await waitFor(async () => (await harness.has('[data-testid="composer-stop"]')) ? null : true, 20_000, 'approved task terminal')
      await waitFor(async () => {
        const pending = await harness.evaluate<number>(`Number((document.querySelector('[data-testid="diagnostics-pending-rpc"]')?.textContent ?? '').match(/\\d+/)?.[0] ?? 0)`)
        return pending === 0 ? true : null
      }, 5_000, 'approval RPC reconciliation')
    })
    await check('UX-04 light theme uses semantic light surfaces', async () => {
      await harness.evaluate(`document.documentElement.dataset.theme = 'light'`)
      const colors = await harness.evaluate<{ body: string; composer: string; settings?: string }>(`(() => ({
        body: getComputedStyle(document.body).backgroundColor,
        composer: getComputedStyle(document.querySelector('.composer-surface')).backgroundColor
      }))()`)
      if (colors.body === 'rgb(17, 19, 24)' || colors.composer === 'rgb(17, 19, 24)') throw new Error(`dark surface leaked into light theme: ${JSON.stringify(colors)}`)
      await harness.evaluate(`document.documentElement.dataset.theme = 'dark'`)
    })
    await check('UX-05 full access requires confirmation', async () => {
      await harness.evaluate(`(() => { const select = document.querySelector('[data-testid="composer-permission-mode"]'); if (!(select instanceof HTMLSelectElement)) throw new Error('permission selector missing'); select.value = 'full_auto'; select.dispatchEvent(new Event('change', { bubbles: true })); })()`)
      await harness.waitForSelector('#full-auto-title', 2_000)
      await harness.evaluate(`document.querySelector('.confirm-actions button')?.click()`)
      if (await harness.has('#full-auto-title')) throw new Error('confirmation did not close')
    })
    await check('UX-06 settings closes with Escape', async () => {
      await harness.evaluate(`document.querySelector('.settings-button')?.click()`)
      await harness.waitForSelector('.settings-page', 2_000)
      await harness.pressKey('Escape')
      await waitFor(async () => (await harness.has('.settings-page')) ? null : true, 2_000, 'settings close')
      await waitFor(async () => (await pendingRpc()) === 0 ? true : null, 5_000, 'settings RPC reconciliation')
    })
    await check('UX-07 delete is optimistic', async () => {
      await harness.evaluate(`document.querySelector('.nav-toggle')?.click()`)
      await harness.waitForSelector('.nav-sheet.open', 2_000)
      const taskId = await harness.evaluate<string>(`document.querySelector('.nav-sheet .session-item.active .session-id')?.textContent ?? ''`)
      const started = Date.now()
      await harness.evaluate(`document.querySelector('.nav-sheet [data-testid="trash-task-${taskId}"]')?.click()`)
      await harness.waitForSelector('[data-testid="task-toast"]', 2_000)
      const feedback = await harness.evaluate<string>(`document.querySelector('[data-testid="task-toast"]')?.textContent ?? ''`)
      if (!feedback.includes('正在打开')) throw new Error(`active task was not protected: ${feedback}`)
      if (!(await harness.has(`.session-item.active .session-id`))) throw new Error('active task disappeared after delete')
      if (Date.now() - started > 1_000) throw new Error('active-task protection was not immediate')
      await harness.evaluate(`document.querySelector('.nav-sheet .sheet-close')?.click()`)
    })
    await check('UX-08 default layout centers task content without an inspector column', async () => {
      const layout = await harness.evaluate<{ columns: string; inspector: boolean }>(`(() => {
        const node = document.querySelector('.command-layout')
        if (!(node instanceof HTMLElement)) throw new Error('command layout missing')
        return {
          columns: getComputedStyle(node).gridTemplateColumns,
          inspector: document.querySelector('.contextual-inspector-slot') !== null
        }
      })()`)
      if (layout.inspector) throw new Error('inspector is open by default')
      if (layout.columns.trim().split(/\\s+/).length > 1) throw new Error(`default layout reserves extra columns: ${layout.columns}`)
    })
    await check('UX-09 non-active task delete and restore give immediate feedback', async () => {
      await harness.evaluate(`document.querySelector('.nav-toggle')?.click()`)
      await harness.waitForSelector('.nav-sheet.open', 2_000)
      const originalId = await harness.evaluate<string>(`document.querySelector('.nav-sheet .session-item.active .session-id')?.textContent ?? ''`)
      await harness.evaluate(`document.querySelector('.nav-sheet .new-session')?.click()`)
      await waitFor(async () => {
        const next = await harness.evaluate<string>(`document.querySelector('.nav-sheet .session-item.active .session-id')?.textContent ?? ''`)
        return next !== '' && next !== originalId ? true : null
      }, 3_000, 'second task creation')
      const secondId = await harness.evaluate<string>(`document.querySelector('.nav-sheet .session-item.active .session-id')?.textContent ?? ''`)
      await harness.evaluate(`document.querySelector('.nav-sheet [data-testid="session-${originalId}"]')?.click()`)
      await harness.waitForSelector('.nav-sheet .session-item.active', 2_000)
      await harness.evaluate(`document.querySelector('.nav-sheet [data-testid="trash-task-${secondId}"]')?.click()`)
      await waitFor(async () => (await harness.evaluate<string>(`document.querySelector('[data-testid="task-toast"]')?.textContent ?? ''`)).includes('删除成功') ? true : null, 2_000, 'delete success toast')
      await harness.evaluate(`document.querySelector('.nav-sheet .trash-toggle')?.click()`)
      await harness.waitForSelector(`.nav-sheet [data-testid="restore-task-${secondId}"]`, 2_000)
      await harness.evaluate(`document.querySelector('.nav-sheet [data-testid="restore-task-${secondId}"]')?.click()`)
      await waitFor(async () => (await harness.evaluate<string>(`document.querySelector('[data-testid="task-toast"]')?.textContent ?? ''`)).includes('恢复成功') ? true : null, 2_000, 'restore success toast')
      await harness.evaluate(`document.querySelector('.nav-sheet .sheet-close')?.click()`)
    })
    await check('UX-10 inspector opens only on demand from a tool activity', async () => {
      await harness.evaluate(`(() => { const details = document.querySelector('.tool-activity'); if (details instanceof HTMLDetailsElement) details.open = true; const button = details?.querySelector('.activity-inspect-button'); if (button instanceof HTMLElement) button.click(); })()`)
      await harness.waitForSelector('.contextual-inspector-slot', 2_000)
      if (!(await harness.has('[data-testid="inspector"]'))) throw new Error('task inspector content missing')
      await harness.evaluate(`document.querySelector('[data-testid="inspector"] .inspector-header button')?.click()`)
      await waitFor(async () => (await harness.has('.contextual-inspector-slot')) ? null : true, 2_000, 'inspector close')
    })
    await waitFor(async () => (await pendingRpc()) === 0 ? true : null, 5_000, 'all GUI RPCs settled').catch(async (error) => {
      console.error(`GUI_UX_PENDING ${JSON.stringify({ snapshot: await harness.domSnapshot(), lines: await harness.evaluate('window.__rxyGuiUxLines ?? []') })}`)
      throw error
    })
    await harness.screenshot('ux-final.png')
    const proof = await harness.cleanup()
    cleaned = true
    if (!proof.passed) throw new Error(`cleanup proof failed: ${JSON.stringify(proof)}`)
  } finally {
    // cleanup is idempotent and the final proof is still written when a case fails
    if (!cleaned) {
      try { await harness.cleanup() } catch (error) {
        console.error(`GUI_UX_CLEANUP_ERROR ${error instanceof Error ? error.message : String(error)}`)
      }
    }
  }
  const failed = results.filter((item) => item.status === 'failed')
  console.log(JSON.stringify({ artifactDir, results }, null, 2))
  if (failed.length > 0) process.exitCode = 1
}

void main()
