import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  buildBatchPrompts,
  realBusinessScenarios
} from './real-business-scenarios.mts'
import {
  aggregateUsage,
  cacheHitRate,
  evaluateLayoutSnapshot,
  isMeaningfulProtocolEvent,
  terminalOutcomeIssue,
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
  assert.match(byId.T02, /HTML|JavaScript|T02-platformer|two|T02/)
  assert.match(byId.T03, /websearch|webfetch|Skill|T03-company/)
  assert.match(byId.T04, /datetime|3000|T04-travel|sources/)
  assert.match(byId.T05, /Java 17|Swing|javac|T05-number-bomb/)
  assert.match(byId.T06, /CSV|BI|T06-market-bi|websearch/)
  assert.match(byId.T07, /TCO|T07-ev|websearch/)
  assert.match(byId.T08, /3500|60|T08-rental|websearch/)
  assert.match(byId.T09, /Spring Boot 4.1.0|Maven 3.9.16|MySQL 8|Flyway/)
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

test('synthetic waiting progress does not reset the real-work watchdog', () => {
  assert.equal(isMeaningfulProtocolEvent({ method: 'event/progress', params: { text: '正在等待模型响应…' } }), false)
  assert.equal(isMeaningfulProtocolEvent({ method: 'event/progress', params: { text: 'Build in progress... 30s' } }), false)
  assert.equal(isMeaningfulProtocolEvent({ method: 'event/progress', params: { text: 'Thinking... (round 1)' } }), true)
  assert.equal(isMeaningfulProtocolEvent({ method: 'event/message_delta', params: { text: 'token' } }), true)
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
