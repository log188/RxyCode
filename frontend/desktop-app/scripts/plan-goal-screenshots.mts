#!/usr/bin/env node
/** Step-by-step Electron screenshots for Desktop plan / goal / workspace UI. */
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { DesktopCdpHarness, waitFor } from './cdp-harness.mts'

const artifactDir = process.env.RXYCODE_GUI_ARTIFACTS ?? join(process.cwd(), 'artifacts', `desktop-plan-goal-${Date.now()}`)
mkdirSync(artifactDir, { recursive: true })

async function typeInto(
  harness: DesktopCdpHarness,
  selector: string,
  text: string
): Promise<void> {
  await harness.evaluate(`(() => {
    const element = document.querySelector(${JSON.stringify(selector)});
    if (!(element instanceof HTMLTextAreaElement)) throw new Error(${JSON.stringify(selector)} + ' missing');
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
    if (setter === undefined) throw new Error('textarea value setter missing');
    setter.call(element, ${JSON.stringify(text)});
    element.focus();
    element.dispatchEvent(new Event('input', { bubbles: true }));
  })()`)
}

async function pressEnterOn(harness: DesktopCdpHarness, selector: string): Promise<void> {
  await harness.evaluate(`(() => {
    const element = document.querySelector(${JSON.stringify(selector)});
    if (!(element instanceof HTMLTextAreaElement)) throw new Error(${JSON.stringify(selector)} + ' missing');
    element.focus();
    element.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Enter',
      code: 'Enter',
      bubbles: true,
      cancelable: true
    }));
  })()`)
}

async function main(): Promise<void> {
  const harness = new DesktopCdpHarness({
    artifactDir,
    fakeAppserver: true,
    width: 1280,
    height: 900
  })
  let cleaned = false
  try {
    await harness.start()
    await harness.waitForSelector('[data-testid="task-command-center"]', 60_000)
    await harness.screenshot('01-shell.png')

    await harness.waitForSelector('.nav-toggle:not(:disabled)', 60_000)
    await harness.evaluate(`document.querySelector('.nav-toggle:not(:disabled)')?.click()`)
    await harness.waitForSelector('.nav-sheet.open .new-session:not(:disabled)', 5_000)
    await harness.screenshot('02-nav-open.png')
    await harness.evaluate(`document.querySelector('.nav-sheet.open .new-session:not(:disabled)')?.click()`)
    await harness.waitForSelector('[data-testid="composer-input"]:not(:disabled)', 20_000)
    await harness.evaluate(`document.querySelector('.nav-sheet .sheet-close')?.click()`)
    await waitFor(async () => (await harness.has('.nav-sheet.open')) ? null : true, 2_000, 'nav close')
    await harness.screenshot('03-empty-task.png')

    await harness.evaluate(`document.querySelector('[data-testid="composer-plus"]')?.click()`)
    await harness.waitForSelector('[data-testid="composer-plus-menu"]', 2_000)
    await harness.screenshot('04-plus-menu.png')

    await harness.evaluate(`document.querySelector('[data-testid="plus-plan-mode"]')?.click()`)
    await waitFor(async () => (await harness.has('[data-testid="composer-plan-chip"]')) ? true : null, 2_000, 'plan chip')
    await harness.screenshot('05-plan-mode-on.png')

    await harness.evaluate(`document.querySelector('[data-testid="composer-plus"]')?.click()`)
    await harness.waitForSelector('[data-testid="plus-plan-mode"].is-active', 2_000)
    await harness.screenshot('06-plus-menu-plan-active.png')
    await harness.evaluate(`document.querySelector('[data-testid="plus-goal"]')?.click()`)
    await harness.waitForSelector('[data-testid="goal-dialog"]', 2_000)
    await harness.screenshot('07-goal-dialog.png')

    await typeInto(harness, '[data-testid="goal-input"]', '把 1+1 做成可演示的计算')
    await harness.screenshot('08-goal-typed.png')
    await harness.evaluate(`document.querySelector('[data-testid="goal-save"]')?.click()`)
    await waitFor(async () => (await harness.has('[data-testid="composer-goal-chip"]')) ? true : null, 2_000, 'goal chip')
    await harness.screenshot('09-goal-chip.png')

    await typeInto(harness, '[data-testid="composer-input"]', '规划一个 1+1 计算演示')
    await harness.screenshot('10-plan-prompt-typed.png')
    await pressEnterOn(harness, '[data-testid="composer-input"]')
    await harness.waitForSelector('[data-testid="plan-document"]', 10_000)
    await waitFor(async () => (await harness.has('[data-testid="plan-actions"]')) ? true : null, 5_000, 'plan actions')
    await harness.screenshot('11-plan-document.png')

    const title = await harness.evaluate<string>(`document.querySelector('[data-testid="plan-document-title"]')?.textContent ?? ''`)
    if (!title.includes('1+1')) throw new Error(`unexpected plan title: ${title}`)
    if (!(await harness.has('[data-testid="plan-build"]'))) throw new Error('Build it row missing')
    const placeholder = await harness.evaluate<string>(`document.querySelector('[data-testid="plan-revise-input"]')?.getAttribute('placeholder') ?? ''`)
    if (!placeholder.includes('补充说明')) throw new Error(`revise placeholder missing: ${placeholder}`)

    await typeInto(harness, '[data-testid="plan-revise-input"]', '步骤里加上单元测试')
    await harness.screenshot('12-revise-typed.png')
    await pressEnterOn(harness, '[data-testid="plan-revise-input"]')
    await waitFor(async () => {
      const ready = await harness.evaluate<{ running: boolean; enabled: boolean }>(`(() => {
        const build = document.querySelector('[data-testid="plan-build"]')
        return {
          running: Boolean(document.querySelector('[data-testid="composer-stop"]')),
          enabled: build instanceof HTMLButtonElement && !build.disabled
        }
      })()`)
      return !ready.running && ready.enabled ? true : null
    }, 10_000, 'revised plan ready to build')
    await harness.screenshot('13-plan-revised.png')

    await harness.evaluate(`(() => {
      const button = document.querySelector('[data-testid="plan-build"]')
      if (!(button instanceof HTMLButtonElement) || button.disabled) throw new Error('plan-build not ready')
      button.scrollIntoView({ block: 'center' })
      button.click()
    })()`)
    await waitFor(async () => (await harness.has('[data-testid="composer-plan-chip"]')) ? null : true, 5_000, 'left plan mode')
    await harness.waitForSelector('[data-testid^="timeline-tool-"]', 8_000)
    await harness.screenshot('14-build-running.png')
    await waitFor(async () => {
      const finals = await harness.evaluate<number>(`document.querySelectorAll('[data-testid="final-answer"]').length`)
      return finals > 0 ? true : null
    }, 10_000, 'build final answer')
    await harness.screenshot('15-build-complete.png')

    const body = await harness.evaluate<string>(`document.body.innerText`)
    if (!body.includes('1 + 1 = 2') && !body.includes('已按计划完成')) {
      throw new Error(`build result missing: ${body.slice(-400)}`)
    }
  } finally {
    if (!cleaned) {
      try {
        await harness.cleanup()
        cleaned = true
      } catch (error) {
        console.error(`PLAN_GOAL_CLEANUP_ERROR ${error instanceof Error ? error.message : String(error)}`)
      }
    }
  }
  console.log(JSON.stringify({ artifactDir, status: 'passed' }, null, 2))
}

void main().catch((error) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error))
  process.exitCode = 1
})
