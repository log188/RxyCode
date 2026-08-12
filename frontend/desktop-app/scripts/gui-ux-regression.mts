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
    await harness.waitForSelector('.new-session:not(:disabled)', 60_000)
    await harness.evaluate(`document.querySelector('.new-session:not(:disabled)')?.click()`)
    await harness.waitForSelector('[data-testid="composer-input"]:not(:disabled)', 20_000)

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
      const taskId = await harness.evaluate<string>(`document.querySelector('.session-item.active .session-id')?.textContent ?? ''`)
      const started = Date.now()
      await harness.evaluate(`document.querySelector('[data-testid="trash-task-${taskId}"]')?.click()`)
      await harness.waitForSelector('.trash-toggle', 2_000)
      if (Date.now() - started > 1_000) throw new Error('task list waited for the server cleanup')
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
