# RxyCode 工程审计报告（Engineering Audit）

> 范围：RxyCode（`d:/agent-demo/RxyCode/RxyCode1_1_0`）
> 后端：Python（asyncio + LangChain + FastAPI SSE）｜前端：TypeScript/React/Ink 终端 UI
> 对标对象：opencode、claude-code、aider、gemini-cli、goose、hermes
> 形式：**报告 + 全部实现**（差距、可借鉴的开源代码位置、具体改法，且改进项已落地）

---

## 0. 摘要（已交付状态）

| 维度 | 已落地改进 | 状态 |
|------|-----------|------|
| Prompt Engineering | 系统提示加入工具调用契约 / 失败自纠 / plan-mode / 结构化输出 | ✅ 已实现 |
| Context 管理 | 工具循环内主动触发 `ContextCompressor` 三档压缩 + 持久会话压缩 | ✅ 已实现 |
| Harness | 工具统一 `1800s` 上限、任务总上限 `7200s`、默认关闭静默误杀、失败回灌 LLM 自我修正、并行竞速 web 搜索 | ✅ 已实现（Bug 4） |
| TUI | 滚动回看（PgUp/PgDn）、思考块实时展开、表格按显示宽度对齐、原生细闪烁光标精确定位 | ✅ 已实现（Bug 1–3, 5） |
| Observability | 每个工具调用落 `NodeSpan`（status/error/duration）到 JSONL trace | ✅ 已实现 |
| Safety | 审批门新增「本次允许(o)」粒度，对齐 claude-code 权限模型 | ✅ 已实现 |

---

## 1. Prompt Engineering

### 1.1 现状（`core/prompts/templates.py`）
系统提示 `SYSTEM_PROMPT_TEMPLATE` 采用 OpenHands 风格 XML 分段（`<ROLE>/<CAPABILITIES>/<OPERATIONAL_RULES>/<LANGUAGE>/<TOOLS>`），阶段角色提示通过 `PromptSpec` 版本化（`core/prompts/registry.py`）。工具描述运行时由 `ToolRegistry` 注入。

### 1.2 差距（vs opencode / claude-code / aider）
- **缺少工具调用契约**：`<TOOLS>` 只注入工具描述，没有「一次调一个工具、拿到结果再决定下一步、不得编造工具输出、参数必须与声明一致」的硬约束。claude-code 的系统提示明确写有 tool-use 纪律。
- **缺少失败自纠指令**：`<OPERATIONAL_RULES>` 没有「工具返回 `[error` 时分析原因并重试/换工具」的指令。
- **plan-mode 弱**：默认 fast path 直接 bind 工具循环，没有「先想后做」提示；claude-code 的 plan mode 是显式模式开关 + 专门提示。
- **无统一结构化输出约定**写入系统提示（各阶段各自 `OUTPUT_FORMAT`）。

### 1.3 借鉴与改法（已落地）
- 仿 claude-code / opencode：在 `SYSTEM_PROMPT_TEMPLATE` 新增四个 XML 段：
  - `<TOOL_USE>`：一次一工具、等待结果、不编造输出、参数严格匹配。
  - `<SELF_CORRECTION>`：遇 `[error` 先读错、改参数重试或换工具，绝不编造结果。
  - `<PLAN_MODE>`：多步/多文件任务先列计划再行动；plan mode 下只描述不改写。
  - `<STRUCTURED_OUTPUT>`：Markdown + 代码块 + 表格 + 结尾确认保存路径。

参考位置：opencode `system_prompt`（`tool_use` / `plan_mode` 段）、claude-code `system-prompt.md`（"Use the tools to do X, never guess the tool's output"）。

---

## 2. Context 管理

### 2.1 现状（`memory/compressor.py`）
`ContextCompressor` 已实现 Codex 风格三档压缩：
- Tier 1 无损截断（长工具输出中间截断、长回复保留前两句）
- Tier 2 规则化简（受保护区 + 旧消息移入长期记忆）
- Tier 3 LLM 增量摘要（受 LLM 触发）

`needs_compression` 阈值 `max_tokens*trigger_ratio`（默认 258000×0.9）。

### 2.2 差距
`compress_if_needed` 仅在 `_fast_reply_with_tools` **回合结束后**（`context_used > 0.85*max`）触发一次，**工具循环内部不触发**。长工具驱动的多轮对话在当下这一回合就可能撑爆上下文窗口或变慢。

### 2.3 借鉴与改法（已落地）
仿 Codex/claude-code 的「循环内上下文预算」：
- 新增 `AgentV2._maybe_compress_context(messages)`：
  - 超过 ~70% 上下文预算时，对最旧的 `ToolMessage` 内容做中间截断（保留 `ToolMessage` 对象以维持 `tool_call_id` 契约），不破坏消息结构；
  - 真正超预算时再 `await self._memory.compress_if_needed(session_id)` 压缩持久会话供下一回合使用，并通过 TUI 提示。
- 在 `_fast_reply_with_tools` 每轮开头调用。

---

## 3. Harness（工具鲁棒性）

### 3.1 现状
工具循环 `_fast_reply_with_tools`（`core/agent_v2.py`）`max_rounds=10`；`websearch` 旧实现顺序遍历 6 引擎 × 2 次 × 15s，`bash` 默认 60s 且输出截断。

### 3.2 差距
- web 搜索最坏 ~190s，冷门词表现为「超时/卡死」；
- 慢工具（挂起搜索 / 长 shell）会冻结或中途掐断整个运行；
- 工具失败仅把错误字符串塞回消息，提示层未要求模型利用它自我修正。

### 3.3 借鉴与改法（已落地，Bug 4）
- 仿 gemini-cli / goose 的 web tool：
  - `websearch.py` 引入全局 `TOTAL_BUDGET=25s` + `ThreadPoolExecutor` 并行竞速（首个非空结果即返回），每引擎 `timeout=8s`；引擎顺序把可靠源（GitHub API / Baidu / DDG Lite）前置。
  - 保留同步 `StructuredTool` 接口（内部线程跑竞速）。
- `ToolOrchestrator.execute_tool()` 统一执行 `execution.tool_timeout_seconds`；默认 `1800` 秒且仅包实际 tool invocation。fast path 与 graph proxy 共用该边界，显式取消始终向上传播；`task_stall_timeout_seconds=0` 默认关闭旧的静默 600 秒固定终止，`task_max_time_seconds=7200` 仍提供单任务总上限；
- 系统提示新增 `<SELF_CORRECTION>` 明确「遇错重试/换工具」。

---

## 4. TUI

### 4.1 现状与差距
- **Bug 1 思考不显示**：`ChatPanel` 折叠逻辑 `showExpand = done ? expanded : true` 在运行结束后把思考内容折叠为空（仅剩转圈）；前端 `expandThinking` 默认 `false`；后端 `reasoning_content` 抽取对部分 SDK 不完整。
- **Bug 2 历史被挤出**：`ChatPanel` 用 `overflow="hidden" justifyContent="flex-end"` + 固定高度，旧消息被永久裁掉，无滚动回看。
- **Bug 3 内容错乱**：`Markdown.renderTable` 用 `.length`（字符数）算列宽，CJK 全角更宽导致错位换行。
- **Bug 5 光标掉到下一行**：`InputBox` 光标按整行 `termWidth` 换行且 `startCell=4`，未计入边框 + `> ` 前缀真实左距与盒内换行宽度。

### 4.2 借鉴与改法（已落地）
- 仿 claude-code / opencode 滚动回看：`App.tsx` 引入 `scrollOffset` + `followTail`，PgUp/↑ 上翻、PgDn/↓ 回到尾部（非流式时），`StatusBar` 显示 `(↑ N 更早消息)`；`ChatPanel` 按估算行高做窗口化裁剪，避免每帧全量重渲。
- 仿 opencode thinking panel：`useApi.ts` 把 reasoning 增量实时映射为 `role:'thinking'` 消息并更新；`expandThinking` 默认 `true`，`showExpand = !done || expanded` 让思考块流式展开并保留。
- 表格/代码用 `string-width@^7.2.0`（`Markdown.tsx` 列宽与 `pad` 改用 `stringWidth`）；长代码块改为可折叠而非生硬截断。
- 光标按盒内真实换行宽度 `innerW = termWidth-6` 与左距 `startCell=4` 定位，换行时 `row/col` 精确计算。

---

## 5. Observability

### 5.1 现状（`core/tracing.py`）
`Tracer` + `NodeSpan` 已支持节点级 span（node_name/task_id/token_usage/status/error/duration）→ JSONL 持久化 + replay CLI + p50/p99。但**工具调用级别未接入**。

### 5.2 差距
工具循环内没有 span；慢/失败工具无法在 trace 回放中定位。

### 5.3 借鉴与改法（已落地）
仿 goose / claude-code 的 per-tool span：
- 每个 `_fast_reply_with_tools` 回合创建 `Tracer()`；在 `_execute_tool` 用 `start_span(f"tool:{name}")` / `end_span(status=ok|timeout|error)`，记录耗时、超时、错误。
- trace 文件位置不变（`~/.rxycode/logs/traces/{run_id}.jsonl`，符合既有契约）。

Token 核算已通过 `UsageTrackingLLM` + `utils.streaming.token_stats` 覆盖；评估套件 `evals/` 已含多轮 / 长输出 / 网页搜索任务集，本报告不改其结构。

---

## 6. Safety

### 6.1 现状（`core/safety/`）
`policy.py` 三档风险（READ/WRITE/DANGER，仿 OpenHands）、写路径白名单、dry-run、`classify_bash_command` 动态升级；`approval.py` 有 TUI / SSE 两种审批通道，决策枚举 `APPROVED/REJECTED/ALWAYS_ALLOW_LEVEL`，fail-closed 超时拒绝。

### 6.2 差距
权限粒度只有「批准 / 拒绝 / 始终允许该级别」，缺 claude-code 式的「本次允许（allow once）」——用户常需对某次特定调用放行但不污染全局白名单。

### 6.3 借鉴与改法（已落地）
对齐 claude-code 权限模型：
- `ApprovalDecision` 新增 `ALLOW_ONCE = "allow_once"`；
- `request_approval` 对 `ALLOW_ONCE` 本次放行但**不**写入 `_always_allowed`；
- TUI 提示增加 `[o]nce`，`Answer` 解析 `o/once → ALLOW_ONCE`；
- SSE 通道 `resolve()` 已能解析 `"allow_once"`（枚举构造），无需改动 API 契约。

---

## 7. 防回归说明
- 所有改动不改变既有 API/数据契约与保存路径（`~/.rxycode/output/`）。
- 前端光标写入仅作用于真实 `process.stdout` 且 `if (!out.isTTY) return`，命令面板隐藏原生光标，不污染 `ink-testing-library` 的 `lastFrame()`。
- 工具循环硬化保持 `AIMessage/ToolMessage` 结构不变；安全审批向后兼容（`allow_once` 是纯增量枚举值）。
- 滚动回看窗口化仅在 `scrollOffset`/`messages` 变化时重算，避免每帧全量重渲。
