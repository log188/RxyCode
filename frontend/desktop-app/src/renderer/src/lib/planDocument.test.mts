import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildImplementPrompt,
  buildRevisePrompt,
  looksLikePlanDocument,
  parsePlanDocument,
  stripPlanHint
} from './planDocument.mts'

const SAMPLE = `# 1+1 计算演示

## Summary
计算两个整数 1 和 1 的和。

## Steps
1. 确认输入为整数 1 和 1
2. 相加得到 2
3. 向用户报告结果

---
**下一步**：按 Tab 切换到 **Build** 模式，然后输入「开始」
`

test('parsePlanDocument extracts title summary and steps and strips the build hint', () => {
  const parsed = parsePlanDocument(SAMPLE)
  assert.equal(parsed.title, '1+1 计算演示')
  assert.equal(parsed.summary, '计算两个整数 1 和 1 的和。')
  assert.deepEqual(parsed.steps, ['确认输入为整数 1 和 1', '相加得到 2', '向用户报告结果'])
  assert.equal(parsed.raw.includes('切换到 **Build**'), false)
})

test('looksLikePlanDocument accepts structured plans', () => {
  assert.equal(looksLikePlanDocument(SAMPLE), true)
  assert.equal(looksLikePlanDocument('hello'), false)
})

test('buildImplementPrompt asks the agent to follow the plan in build mode', () => {
  const prompt = buildImplementPrompt(parsePlanDocument(SAMPLE))
  assert.match(prompt, /严格按照以下计划实施/)
  assert.match(prompt, /1\+1 计算演示/)
  assert.match(prompt, /相加得到 2/)
})

test('buildRevisePrompt keeps the previous plan and the user feedback', () => {
  const prompt = buildRevisePrompt(parsePlanDocument(SAMPLE), '步骤里加上单元测试')
  assert.match(prompt, /改写上一份计划文档/)
  assert.match(prompt, /步骤里加上单元测试/)
  assert.match(prompt, /## Steps/)
})

test('stripPlanHint leaves a document without a footer unchanged', () => {
  assert.equal(stripPlanHint('# Title\n\n## Summary\nHi'), '# Title\n\n## Summary\nHi')
})
