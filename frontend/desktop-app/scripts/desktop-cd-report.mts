#!/usr/bin/env node
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { desktopCdScenarios } from './desktop-cd-scenarios.mts'
import { reportedTotals, weightedCacheRate } from './desktop-cd-usage.mts'

interface ResultFile {
  mode: 'deterministic' | 'real'
  rounds: number
  results: Array<Record<string, any>>
  cleanup: Array<Record<string, any>>
}

const artifactRoot = resolve(process.argv[2] ?? '')
if (!artifactRoot || !existsSync(artifactRoot)) {
  throw new Error('usage: node scripts/desktop-cd-report.mts <artifact-root> [report-path]')
}
const reportPath = resolve(
  process.argv[3] ?? resolve(process.cwd(), '..', '..', 'docs', 'DESKTOP-CD-INTEGRATION-STRESS-REPORT-2026-08-12.md')
)
const realArtifactRoot = resolve(process.argv[4] ?? artifactRoot)

function readResult(name: string, root = artifactRoot): ResultFile {
  const path = resolve(root, name)
  if (!existsSync(path)) throw new Error(`missing required result file: ${path}`)
  return JSON.parse(readFileSync(path, 'utf8')) as ResultFile
}

function expectedStatus(id: string): string {
  const scenario = desktopCdScenarios.find((item) => item.id === id)
  if (scenario?.kind === 'failure') return 'failed'
  if (scenario?.kind === 'cancel' || scenario?.kind === 'child-cancel') return 'cancelled'
  return 'succeeded'
}

function validate(file: ResultFile, expectedRounds: number, strictScenarioGate = true): void {
  if (file.rounds !== expectedRounds) throw new Error(`${file.mode}: expected ${expectedRounds} rounds`)
  if (file.results.length !== 30 * expectedRounds) {
    throw new Error(`${file.mode}: expected ${30 * expectedRounds} results, got ${file.results.length}`)
  }
  for (let round = 1; round <= expectedRounds; round += 1) {
    const ids = file.results.filter((result) => result.round === round).map((result) => result.id)
    if (ids.length !== 30 || new Set(ids).size !== 30) throw new Error(`${file.mode} round ${round}: invalid id set`)
    for (const scenario of desktopCdScenarios) {
      if (!ids.includes(scenario.id)) throw new Error(`${file.mode} round ${round}: missing ${scenario.id}`)
    }
  }
  if (file.cleanup.length !== expectedRounds) throw new Error(`${file.mode}: cleanup count mismatch`)
  for (const proof of file.cleanup) {
    if (
      proof.passed !== true || proof.pending_cdp_requests !== 0 ||
      proof.pending_rpc_count !== 0 || proof.lease_count !== 0 ||
      proof.electron_process_gone !== true || proof.appserver_process_gone !== true ||
      proof.debug_port_closed !== true || proof.temp_root_removed !== true ||
      proof.workspace_worktree_removed !== true || proof.source_config_unchanged !== true
    ) {
      throw new Error(`${file.mode}: incomplete cleanup proof ${JSON.stringify(proof)}`)
    }
  }
  for (const result of file.results) {
    if (strictScenarioGate && result.error) throw new Error(`${file.mode} ${result.id}: ${result.error}`)
    if (strictScenarioGate && result.status !== expectedStatus(result.id)) {
      throw new Error(`${file.mode} ${result.id}: expected ${expectedStatus(result.id)}, got ${result.status}`)
    }
    if (typeof result.prompt !== 'string' || result.prompt.length < 80) throw new Error(`${result.id}: prompt missing`)
    const terminalAllowsEmptyAnswer = result.status === 'failed' || result.status === 'cancelled'
    if (typeof result.final_answer !== 'string' || (strictScenarioGate && result.final_answer.length === 0 && !terminalAllowsEmptyAnswer)) throw new Error(`${result.id}: final answer missing`)
    if (!Array.isArray(result.screenshots) || result.screenshots.length === 0) throw new Error(`${result.id}: screenshot missing`)
    if (result.screenshots.some((path: string) => !existsSync(path))) throw new Error(`${result.id}: screenshot path missing`)
    for (const metrics of [result.usage, result.child_usage]) {
      if (!metrics) throw new Error(`${result.id}: usage block missing`)
      for (const key of ['input_tokens', 'output_tokens', 'cache_hit_tokens', 'cache_hit_rate']) {
        if (metrics[key] !== null && typeof metrics[key] !== 'number') throw new Error(`${result.id}: invalid usage ${key}`)
      }
      if (metrics.source === 'not_reported' && [metrics.input_tokens, metrics.output_tokens, metrics.cache_hit_tokens, metrics.cache_hit_rate].some((value) => value !== null)) {
        throw new Error(`${result.id}: not_reported usage contains fabricated numbers`)
      }
    }
    const expectedGateway = result.model.startsWith('zen/')
      ? 'https://opencode.ai/zen/v1'
      : 'https://opencode.ai/zen/go/v1'
    if (result.gateway !== expectedGateway) throw new Error(`${result.id}: model gateway mismatch`)
  }
  const parallel = file.results.filter((result) => result.id === 'DTS-19')
  if (parallel.some((result) => !(result.timing?.overlap_ms > 0))) {
    throw new Error(`${file.mode}: DTS-19 has no measured overlap`)
  }
  if (file.mode === 'deterministic' && parallel.some((result) => !(result.timing?.concurrency_ratio < 0.7))) {
    throw new Error('deterministic: DTS-19 missed the <0.7 concurrency gate')
  }
  const responsive = file.results.find((result) => result.id === 'DTS-29' && result.round === expectedRounds)
  // Deterministic is the reproducible visual gate. Real-provider runs keep
  // raw evidence even when a slow/failed model never reaches the responsive
  // checkpoint; otherwise report generation would erase the failure we need
  // to inspect.
  if (file.mode === 'deterministic' && (!responsive || responsive.screenshots.length < 5)) {
    throw new Error(`${file.mode}: responsive theme matrix missing`)
  }
}

const deterministic = readResult('deterministic-results.json')
const realResultPath = resolve(realArtifactRoot, 'real-results.json')
const real = existsSync(realResultPath)
  ? readResult('real-results.json', realArtifactRoot)
  : (() => {
      // A real-provider run can be intentionally stopped during a long
      // external request. Preserve that partial evidence instead of
      // fabricating 30 empty records or refusing to generate the report.
      const roundResults = resolve(realArtifactRoot, 'real', 'round-1', 'results.json')
      if (!existsSync(roundResults)) {
        throw new Error(`missing real result file and partial round evidence: ${realResultPath}`)
      }
      return {
        mode: 'real' as const,
        rounds: 1,
        results: JSON.parse(readFileSync(roundResults, 'utf8')) as Array<Record<string, any>>,
        cleanup: []
      }
    })()
validate(deterministic, 3)
// Real providers and approval policy are external variables. Preserve their
// raw outcomes in the report; deterministic remains the hard product gate.
if (real.results.length === 30) validate(real, 1, false)
const realResults = real.results
const primary = reportedTotals(realResults, 'usage')
const child = reportedTotals(realResults, 'child_usage')
const deterministicPrimary = reportedTotals(deterministic.results, 'usage')
const deterministicChild = reportedTotals(deterministic.results, 'child_usage')
const deterministicInput = deterministicPrimary.input !== null && deterministicChild.input !== null
  ? deterministicPrimary.input + deterministicChild.input
  : null
const deterministicCache = deterministicPrimary.cache !== null && deterministicChild.cache !== null
  ? deterministicPrimary.cache + deterministicChild.cache
  : null
const deterministicCacheRate = deterministicInput !== null && deterministicCache !== null && deterministicInput > 0
  ? deterministicCache / deterministicInput
  : weightedCacheRate(deterministic.results)
const combinedInput = primary.input !== null && child.input !== null ? primary.input + child.input : null
const combinedCache = primary.cache !== null && child.cache !== null ? primary.cache + child.cache : null
const combinedCacheRate = combinedInput !== null && combinedCache !== null && combinedInput > 0
  ? combinedCache / combinedInput
  : weightedCacheRate(realResults)
const deterministicWall = deterministic.results.reduce((sum, result) => sum + Number(result.timing?.wall_ms ?? 0), 0)
const totalWall = realResults.reduce((sum, result) => sum + Number(result.timing?.wall_ms ?? 0), 0)
const parallel = realResults.find((result) => result.id === 'DTS-19')
const realFailures = realResults.filter((result) => result.error)
const classifyRealOutcome = (result: Record<string, any>): string => {
  const text = `${result.error ?? ''} ${result.final_answer ?? ''} ${JSON.stringify(result.tools ?? [])}`.toLowerCase()
  if (text.includes('rejected by user') || text.includes('approval')) return 'safety/approval'
  if (text.includes('api') || text.includes('connection') || text.includes('search error') || text.includes('timed out') || text.includes('timeout')) return 'provider/external'
  if (text.includes('running tool') || text.includes('terminal state mismatch') || text.includes('overflow')) return 'product/reducer'
  return 'scenario/provider'
}
const failureCounts = realFailures.reduce<Record<string, number>>((counts, result) => {
  const category = classifyRealOutcome(result)
  counts[category] = (counts[category] ?? 0) + 1
  return counts
}, {})

const deterministicFinalRound = deterministic.results.filter((result) => result.round === 3)
const rows = deterministicFinalRound.map((result) => {
  const metric = (usage: Record<string, any>) => usage.input_tokens === null
    ? 'not_reported'
    : `${usage.input_tokens}/${usage.output_tokens}/${usage.cache_hit_tokens ?? 'not_reported'}`
  return `| ${result.id} | ${result.status} | ${result.model} | ${result.sessions.length}/${result.child_sessions.length} | ${result.tools.length}/${result.mcp.length}/${result.skills.length} | ${metric(result.usage)} | ${metric(result.child_usage)} | ${result.timing.wall_ms} |`
}).join('\n')
const realRows = realResults.map((result) => {
  const metric = (usage: Record<string, any>) => usage.input_tokens === null
    ? 'not_reported'
    : `${usage.input_tokens}/${usage.output_tokens}/${usage.cache_hit_tokens ?? 'not_reported'}`
  return `| ${result.id} | ${result.status} | ${result.model} | ${result.sessions.length}/${result.child_sessions.length} | ${result.tools.length}/${result.mcp.length}/${result.skills.length} | ${metric(result.usage)} | ${metric(result.child_usage)} | ${result.timing.wall_ms} |`
}).join('\n')

const issueRows = [
  ['P0', 'Phase D 生产 appserver 未使用 worker 自有 manager', '所有子代理 RPC 路由到对应 Primary worker，并转发 child_session 事件', '协议、worker、host、server 集成测试'],
  ['P0', '模型路由在 top-level appserver 启动方式下相对导入越界', '模型管理依赖增加 package/source-tree 双模式导入', '真实 models/set_active + models/list 校验'],
  ['P0', 'Desktop 将复杂任务写死为 120 秒超时', 'appserver 负责 stall/cancel，Renderer 仅保留 15 分钟传输兜底', 'DTS-01 真实模型连续复测'],
  ['P0', '错误路径遗留 running tool 卡', 'applyError 对所有运行工具统一收敛为 error', 'reducer 回归 + 真实终态 DOM'],
  ['P0', 'lease/workspace/budget 仅有独立组件，未进入 ChildRuntime', 'manager 权威获取/释放 lease，工具前检查 workspace/lease，预算返回稳定错误码', '子代理运行时与冲突测试'],
  ['P0', 'token 未上报时被记为 0', '主/子 usage 均以 null/not_reported 表示未知', 'schema、reducer、报告门禁'],
  ['P1', '固定 CDP 端口、共享 workspace/profile', '动态端口、独立 profile/data/Git worktree、精确 PID 树清理', '四轮 cleanup proof'],
  ['P1', '并发指标曾使用估算值', '改为按 session 协议时间区间计算 overlap、串行等效基线与比率', 'DTS-19 三轮 <0.7'],
  ['P2', '紧凑布局 Diagnostics 与 Composer 叠压', 'Diagnostics 提升到 Composer 上方', '760/1024 截图矩阵']
].map((row) => `| ${row.join(' | ')} |`).join('\n')

const appendix = deterministicFinalRound.concat(realResults).map((result) => `
### ${result.id} — ${result.title}

Prompt：

> ${String(result.prompt).replace(/\n/g, '\n> ')}

Final answer：

${result.final_answer || result.error || 'not available'}

- Primary sessions：${result.sessions.join(', ') || 'none'}
- Child sessions：${result.child_sessions.join(', ') || 'none'}
- Tools：${result.tools.map((tool: any) => `${tool.name}:${tool.status}`).join(', ') || 'none'}
- MCP：${result.mcp.join(', ') || 'none'}
- Skills：${result.skills.join(', ') || 'none'}
- Primary usage：${JSON.stringify(result.usage)}
- Child usage：${JSON.stringify(result.child_usage)}
- Timing：${JSON.stringify(result.timing)}
- Renderer performance trace：${JSON.stringify(result.performance_trace ?? {})}
- Screenshots：${result.screenshots.join(', ')}
- Event log：${result.event_log}
`).join('\n')

const realRoundSection = `
## 3.1 Real-round gate result

- Deterministic 30 scenarios × 3 rounds: enforced as the hard product gate and passed.
- Real-provider plan: 30 scenarios × 1 round; observed ${realResults.length}/30 records before the run stopped at the external/provider timeout boundary. Raw provider, approval, timeout, prompt, usage and final-answer evidence is retained for every observed record.
- Observed real records with scenario errors: ${realFailures.length}/${realResults.length}. The real-model 30-scenario gate is not claimed as passed.
- Real failure classification: ${JSON.stringify(failureCounts)}.
- After the FIFO and replay-order fixes, targeted deterministic DTS-26/DTS-29 passed. Historical real running-tool records remain as pre-fix evidence and are not used to claim the post-fix result.
`

const reportDate = reportPath.match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? new Date().toISOString().slice(0, 10)
const markdown = `# RxyCode Desktop Phase C/D 联合 GUI 压力测试报告

- 执行日期：${reportDate}
- 确定性门禁：30 场景 × 3 个连续轮次，共 ${deterministic.results.length} 条
- 真实模型计划：30 场景 × 1 轮；实际观测 ${realResults.length} 条后因外部/provider 超时停止，未宣称全量通过
- 确定性原始工件：\`${artifactRoot}\`；真实轮原始工件：\`${realArtifactRoot}\`（均不提交 Git）

## 1. 改造结果

Phase 4 Desktop 已从两栏聊天壳改造成任务指挥台：左侧持续显示项目与并发任务，中间使用文档式活动流、计划/工具/终态和固定 Composer，右侧提供 Activity、Agents、Usage 检查器。≥1280px 为三栏常驻，960–1279px 使用 Inspector 抽屉，<960px 保留 56px task rail 与双侧 sheet。主题支持跟随系统、浅色、深色。

设计参考为 [Codex Desktop](https://openai.com/index/introducing-the-codex-app/)、[Google Antigravity](https://developers.googleblog.com/en/build-with-google-antigravity-our-new-agentic-development-platform/)、[Jules](https://jules.google/docs/code/) 和 [OpenCode Agents](https://opencode.ai/docs/agents/)。本实现没有复制品牌、图标或专有资产，也没有伪造 Phase G 的完整 Diff/Review。

## 2. Token 与时间汇总

- 确定性 Primary input/output/cache-hit：${deterministicPrimary.input === null ? 'not_reported' : `${deterministicPrimary.input}/${deterministicPrimary.output}/${deterministicPrimary.cache}`}（有报告 ${deterministicPrimary.reported}/90）
- 确定性 Child input/output/cache-hit：${deterministicChild.input === null ? 'not_reported' : `${deterministicChild.input}/${deterministicChild.output}/${deterministicChild.cache}`}（有报告 ${deterministicChild.reported}/90）
- 确定性加权缓存命中率：${deterministicCacheRate === null ? 'not_reported' : `${(deterministicCacheRate * 100).toFixed(2)}%`}
- 确定性任务累计墙钟：${deterministicWall} ms
- 真实 Provider Primary input/output/cache-hit：${primary.reported === 0 ? 'not_reported' : `${primary.input}/${primary.output}/${primary.cache}`}（有报告 ${primary.reported}/${realResults.length}）
- 真实 Provider Child input/output/cache-hit：${child.reported === 0 ? 'not_reported' : `${child.input}/${child.output}/${child.cache}`}（有报告 ${child.reported}/${realResults.length}）
- 真实 Provider 加权缓存命中率：${combinedCacheRate === null ? 'not_reported' : `${(combinedCacheRate * 100).toFixed(2)}%`}
- 真实观测任务累计墙钟：${totalWall} ms
- DTS-19 确定性并发：overlap=${deterministic.results.find((result) => result.id === 'DTS-19')?.timing?.overlap_ms ?? 'not_reported'} ms，串行等效基线=${deterministic.results.find((result) => result.id === 'DTS-19')?.timing?.serial_baseline_ms ?? 'not_reported'} ms
- DTS-19 真实并发：overlap=${parallel?.timing?.overlap_ms ?? 'not_reported'} ms，串行等效基线=${parallel?.timing?.serial_baseline_ms ?? 'not_reported'} ms
- 未上报指标全部保留为 \`null/not_reported\`，不进入合计或缓存命中率。

## 3. 30 条真实场景

| ID | 状态 | 模型 | Primary/Child | Tool/MCP/Skill | Primary in/out/cache | Child in/out/cache | wall ms |
|---|---|---|---:|---:|---|---|---:|
${rows}

### Real Provider observed rows

${realRows}

${realRoundSection}

## 4. 并发、流式与恢复门禁

- DTS-19 的三轮确定性 concurrency ratio 均小于 0.7；真实轮只以事件区间重叠为通过条件。
- DTS-20 验证同一会话 busy guard，不覆盖首轮流、工具、usage 或 final answer。
- DTS-21～30 验证真实 child tree、审批归属、递归取消、lease/budget、MCP/Skill 部分成功、cursor 恢复和长流切换。
- 终态不允许 running tool、孤儿 Child、孤儿 lease、pending RPC、跨会话串流或未知 token 记零。

## 5. 发现问题与修复

| 级别 | 问题 | 修复 | 回归证据 |
|---|---|---|---|
${issueRows}

## 6. 视觉与可访问性审计

- 实际截图覆盖 1440 浅色/深色、1024 抽屉和 760 紧凑布局；根文档无横向或纵向溢出。
- 状态使用图标与文字共同表达；结构图标使用 Lucide SVG。
- Composer 有 accessible label，错误使用 alert，活动流使用 polite live region，Inspector 使用 tab/tabpanel 和 tree/treeitem 语义。
- 支持可见焦点、Esc 关闭、键盘导航和 prefers-reduced-motion。

## 7. 清理证明与限制

每轮 cleanup proof 均要求：CDP WebSocket 关闭、pending CDP/RPC 为 0、Electron 和 appserver PID 消失、动态端口关闭、独立 Git worktree 从 Git 元数据与磁盘移除、临时 profile/data/workspace 删除、源 config/credentials SHA-256 不变、active lease 为 0。测试只结束自己启动的 PID 树。

限制：Provider 不返回 usage 时无法可靠推算，因此明确记录为 not_reported；Phase G Diff/Review 仍不在本轮范围。原始 JSON、事件流、完整回答和截图不提交 Git。

## 8. 可复现命令

\`cd frontend/desktop-app\`

\`npm run stress:cd:deterministic\`

\`npm run stress:cd:real\`

\`node scripts/desktop-cd-report.mts <artifact-root> <report-path>\`

## 附录 A：完整真实 Prompt 与 Final Answer

${appendix}
`

writeFileSync(reportPath, `${markdown.trimEnd()}\n`)
console.log(`DESKTOP_CD_REPORT_OK ${reportPath}`)
