import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  buildBatchPrompts,
  buildMissingFileRepairPrompt,
  parseMissingFilenames,
  realBusinessScenarios
} from './real-business-scenarios.mts'
import {
  aggregateUsage,
  cacheHitRate,
  evaluateLayoutSnapshot,
  gameEnteredPlayableState,
  isMeaningfulProtocolEvent,
  missingWebDeliverables,
  parseHudScore,
  playProbeUrl,
  staticFilePath,
  terminalOutcomeIssue,
  hasInFlightTool,
  timelineKinds
} from './real-business-metrics.mts'
import { screenshotPath } from './cdp-harness.mts'

test('CDP screenshots accept both artifact-relative and absolute paths', () => {
  assert.equal(
    screenshotPath('C:\\artifacts\\run', 'screenshots\\T01.png'),
    'C:\\artifacts\\run\\screenshots\\T01.png'
  )
  assert.equal(
    screenshotPath('C:\\artifacts\\run', 'D:\\evidence\\T01.png'),
    'D:\\evidence\\T01.png'
  )
})

test('real business suite defines nine complete user scenarios', () => {
  assert.equal(realBusinessScenarios.length, 9)
  assert.equal(new Set(realBusinessScenarios.map((scenario) => scenario.id)).size, 9)
  for (const scenario of realBusinessScenarios) {
    assert.ok(scenario.prompt.length > 500, `${scenario.id} prompt is too short`)
    assert.equal(scenario.prompt.includes('\uFFFD'), false, `${scenario.id} prompt contains replacement characters`)
    assert.equal(scenario.prompt.includes('\uFFFD'), false, `${scenario.id} prompt contains replacement characters`)
    assert.ok(scenario.outputDir.startsWith(scenario.id), `${scenario.id} output dir is not isolated`)
    assert.ok(scenario.expectedTools.length >= 2, `${scenario.id} lacks tool expectations`)
    assert.ok(scenario.visualCheckpoints.length >= 2, `${scenario.id} lacks visual checkpoints`)
    assert.equal(scenario.maxInputTokens, 200_000)
    assert.equal(scenario.maxOutputTokens, 48_000)
    assert.equal(scenario.timeoutMs, 45 * 60 * 1000)
  }
})

test('real business prompts preserve the required implementation boundaries', () => {
  const byId = Object.fromEntries(realBusinessScenarios.map((scenario) => [scenario.id, scenario.prompt]))
  assert.match(byId.T01, /localStorage|HTML|JavaScript|T01-runner/)
  assert.match(byId.T01, /write tool|TEST-REPORT/)
  assert.match(byId.T02, /HTML|JavaScript|T02-platformer|two|T02/)
  assert.match(byId.T02, /README.md|TEST-REPORT/)
  assert.match(byId.T03, /websearch|webfetch|Skill|T03-company/)
  assert.match(byId.T04, /datetime|3000|T04-travel|sources/)
  assert.match(byId.T05, /Java 17|Swing|javac|T05-number-bomb/)
  assert.match(byId.T06, /CSV|BI|T06-market-bi|websearch/)
  assert.match(byId.T07, /TCO|T07-ev|websearch/)
  assert.match(byId.T08, /3500|60|T08-rental|websearch/)
  assert.match(byId.T09, /Spring Boot 4.1.0|Maven 3.9.16|MySQL 8|Flyway/)
})

test('missing-file repair prompt writes documents instead of re-reading source', () => {
  assert.deepEqual(
    parseMissingFilenames('web artifact is incomplete; missing README.md, TEST-REPORT.md'),
    ['README.md', 'TEST-REPORT.md']
  )
  const prompt = buildMissingFileRepairPrompt('T02-platformer', ['README.md', 'TEST-REPORT.md'])
  assert.match(prompt, /T02-platformer\/README\.md/)
  assert.match(prompt, /T02-platformer\/TEST-REPORT\.md/)
  assert.match(prompt, /write tool/)
  assert.match(prompt, /Do not read existing/)
  assert.doesNotMatch(prompt, /Inspect every file/)
  assert.doesNotMatch(prompt, /play the page/)
  assert.deepEqual(parseMissingFilenames('generated page is not playable: no start control'), [])
})

test('batch prompt builder gives one isolated run and one ordered long-session run', () => {
  const prompts = buildBatchPrompts()
  assert.equal(prompts.independent.length, 9)
  assert.equal(prompts.sequential.length, 9)
  assert.deepEqual(prompts.sequential.map((item) => item.id), realBusinessScenarios.map((item) => item.id))
  assert.ok(prompts.independent.every((item) => item.prompt.includes(item.outputDir)))
  assert.ok(prompts.sequential.every((item) => item.prompt.includes(item.outputDir)))
})

test('usage aggregation keeps null unreported values and uses input as cache denominator', () => {
  const summary = aggregateUsage([
    { input_tokens: 1000, output_tokens: 200, cache_hit_tokens: 700, cache_miss_tokens: 300, reporting_status: 'reported' },
    { input_tokens: null, output_tokens: null, cache_hit_tokens: null, cache_miss_tokens: null, reporting_status: 'not_reported' },
    { input_tokens: 500, output_tokens: 100, cache_hit_tokens: 100, cache_miss_tokens: 400, reporting_status: 'partial' }
  ])
  assert.equal(summary.input_tokens, 1500)
  assert.equal(summary.output_tokens, 300)
  assert.equal(summary.cache_hit_tokens, 800)
  assert.equal(summary.cache_miss_tokens, 700)
  assert.equal(summary.total_tokens, 1800)
  assert.equal(summary.reporting_status, 'partial')
  assert.equal(cacheHitRate(summary), 800 / 1500)
})

test('usage aggregation does not turn entirely unknown provider metrics into zero', () => {
  const summary = aggregateUsage([
    { input_tokens: null, output_tokens: null, cache_hit_tokens: null, cache_miss_tokens: null, reporting_status: 'not_reported' }
  ])
  assert.equal(summary.input_tokens, null)
  assert.equal(summary.output_tokens, null)
  assert.equal(summary.cache_hit_tokens, null)
  assert.equal(summary.cache_miss_tokens, null)
  assert.equal(summary.total_tokens, null)
  assert.equal(cacheHitRate(summary), null)
})

test('desktop geometry contract keeps the transcript above a fixed composer', () => {
  const css = readFileSync(new URL('../src/renderer/src/assets/main.css', import.meta.url), 'utf8')
  assert.match(css, /\.task-main \{\s*display: flex;\s*flex-direction: column;\s*min-height: 0;\s*overflow: hidden;/)
  assert.match(css, /\.chat-area \{\s*min-height: 0;\s*flex: 1 1 auto;\s*overflow: auto;/)
  assert.match(css, /\.composer \{\s*flex: 0 0 auto;\s*min-height: 0;\s*position: relative;\s*z-index: 1;/)
})

test('successful GUI runs must expose a non-empty Final Answer', () => {
  assert.equal(terminalOutcomeIssue('succeeded', ''), 'succeeded task has no non-empty Final Answer')
  assert.equal(terminalOutcomeIssue('succeeded', 'Done'), null)
  assert.equal(terminalOutcomeIssue('failed', ''), null)
})

test('web artifacts cannot pass with only an index.html', () => {
  assert.deepEqual(missingWebDeliverables(['index.html', 'game.js', 'styles.css', 'PLAN.md']), ['README.md', 'TEST-REPORT.md'])
  assert.deepEqual(missingWebDeliverables(['index.html', 'README.md', 'TEST-REPORT.md']), [])
})

test('game play probe accepts Chinese running state and rejects the menu', () => {
  assert.equal(gameEnteredPlayableState('运行中', 0), true)
  assert.equal(gameEnteredPlayableState('菜单', 0), false)
  assert.equal(gameEnteredPlayableState('菜单', 12), true)
  assert.equal(gameEnteredPlayableState('running', 0), true)
  assert.equal(parseHudScore('得分 33'), 33)
})

test('play probe reads the http url even when Electron leaves switches in argv', () => {
  assert.equal(
    playProbeUrl(['C:\\\\electron.exe', '--disable-gpu', 'play-probe.cjs', 'http://127.0.0.1:9/', 'shot.png']),
    'http://127.0.0.1:9/'
  )
})

test('static file server keeps /game.js inside the artifact root on Windows', () => {
  const root = 'D:\\\\artifact\\\\T01-runner'
  assert.equal(staticFilePath(root, '/game.js'), resolve(root, 'game.js'))
  assert.equal(staticFilePath(root, '/'), resolve(root, 'index.html'))
  assert.equal(staticFilePath(root, '/../secret.js'), null)
})

test('web play probe prefers explicit start buttons over the first button on the page', () => {
  const probe = readFileSync(new URL('./play-generated-page-probe.cjs', import.meta.url), 'utf8')
  assert.match(probe, /#startBtn, #btn-start/)
  const suite = readFileSync(new URL('./real-business-suite.mts', import.meta.url), 'utf8')
  assert.match(suite, /#start-btn/)
  assert.match(suite, /开始\|start\|play/)
  assert.match(suite, /canvasPainted|getImageData/)
  assert.match(suite, /data-action="newgame"/)
  assert.match(suite, /#screen-menu/)
  assert.match(suite, /#stat-score/)
  assert.match(suite, /headless=new/)
  assert.match(suite, /Chrome may keep the profile directory locked/)
})

test('a follow-up prompt stops a still-running task before typing into the composer', () => {
  const suite = readFileSync(new URL('./real-business-suite.mts', import.meta.url), 'utf8')
  assert.match(suite, /async function stopActiveTask/)
  assert.match(suite, /if \(await harness\.has\('\[data-testid="composer-stop"\]'\)\)/)
  assert.match(suite, /composer-stop/)
})

test('synthetic waiting progress does not reset the real-work watchdog', () => {
  assert.equal(isMeaningfulProtocolEvent({ method: 'event/progress', params: { text: '正在等待模型响应…' } }), false)
  assert.equal(isMeaningfulProtocolEvent({ method: 'event/progress', params: { text: 'Build in progress... 30s' } }), false)
  assert.equal(isMeaningfulProtocolEvent({ method: 'event/progress', params: { text: 'Thinking... (round 1)' } }), true)
  assert.equal(isMeaningfulProtocolEvent({ method: 'event/message_delta', params: { text: 'token' } }), true)
})

test('an in-flight tool is not treated as GUI silence', () => {
  const begin = { method: 'event/tool_begin', params: { session_id: 's1', call_id: 'c1' }, __at_ms: 1000 }
  const waiting = { method: 'event/progress', params: { session_id: 's1', text: '正在等待模型响应…' }, __at_ms: 20000 }
  const ended = { method: 'event/tool_end', params: { session_id: 's1', call_id: 'c1' }, __at_ms: 62000 }
  assert.equal(hasInFlightTool([begin, waiting], 's1', 1000), true)
  assert.equal(hasInFlightTool([begin, waiting, ended], 's1', 1000, 62000), true)
  assert.equal(hasInFlightTool([begin, waiting, ended], 's1', 62000), false)
})

test('layout evaluator catches overlap, clipping and composer coverage', () => {
  const result = evaluateLayoutSnapshot({
    viewport: { width: 800, height: 700 },
    horizontalScroll: 0,
    elements: [
      { id: 'timeline', left: 80, top: 80, right: 780, bottom: 620 },
      { id: 'composer', left: 80, top: 560, right: 780, bottom: 720 },
      { id: 'button', left: 760, top: 20, right: 820, bottom: 50 }
    ]
  })
  assert.ok(result.issues.some((issue) => issue.kind === 'overlap'))
  assert.ok(result.issues.some((issue) => issue.kind === 'clipped'))
  assert.ok(result.issues.some((issue) => issue.kind === 'composer_coverage'))
})

test('layout evaluator tolerates subpixel sibling boundaries but catches real overlap', () => {
  assert.deepEqual(evaluateLayoutSnapshot({
    viewport: { width: 100, height: 100 },
    horizontalScroll: 0,
    elements: [
      { id: 'chat', left: 0, top: 0, right: 100, bottom: 60.0001 },
      { id: 'composer', left: 0, top: 60.0002, right: 100, bottom: 100.0001 }
    ]
  }).issues, [])
  assert.ok(evaluateLayoutSnapshot({
    viewport: { width: 100, height: 100 },
    horizontalScroll: 0,
    elements: [
      { id: 'chat', left: 0, top: 0, right: 100, bottom: 61 },
      { id: 'composer', left: 0, top: 60, right: 100, bottom: 100 }
    ]
  }).issues.some((issue) => issue.kind === 'overlap'))
})

test('timeline checker requires chronological tool results and final answer', () => {
  assert.deepEqual(
    timelineKinds([
      { kind: 'prompt' },
      { kind: 'assistant' },
      { kind: 'tool' },
      { kind: 'tool_result' },
      { kind: 'recovery' },
      { kind: 'tool' },
      { kind: 'tool_result' },
      { kind: 'final' }
    ]),
    { valid: true, issue: null }
  )
  assert.equal(
    timelineKinds([{ kind: 'tool_result' }, { kind: 'tool' }, { kind: 'final' }]).valid,
    false
  )
})
