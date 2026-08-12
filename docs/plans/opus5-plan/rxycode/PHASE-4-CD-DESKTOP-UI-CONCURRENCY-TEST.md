# Phase 4-CD · Desktop 任务指挥台、并发与子代理联合验收

> **执行模型：**Composer 2.5 主写、主审、主合并；Terra 按本卡实施并把每项产出转为可复现测试或验收记录。Grok 4.5 只可协助截图观察、视觉问题清单和小范围前端建议，**不得**修改 `protocol/`、`appserver/`、权限、预算或 Child Runtime。
>
> **执行规范：**全部 CD 卡遵循 [`../COMPOSER-2.5-PLAYBOOK.md`](../COMPOSER-2.5-PLAYBOOK.md) 的 C1–C8 硬性规则、卡结构与 Review 清单；本 Phase 的额外隔离、清理和真实模型约束见 0.4 与 §6。
>
> **基线：**本地 `master` 的 `b90d565`（Phase C 已合入）。**任务卡：**CD1–CD17。**预计：**按卡独立评审；不把模型速度当作排期承诺。

---

## 目录

| 章节 | 内容 |
|---|---|
| §0 | Terra 执行手册、七步回路、ownership 与硬约束 |
| §1 | 当前代码真相和可复现证据 |
| §2 | Codex、Antigravity、Jules、OpenCode 的采用边界 |
| §3 | 任务指挥台布局、主题、状态与响应式设计 |
| §4 | JSON-RPC、事件、类型与兼容契约 |
| §5 | CD1–CD17 实施任务卡 |
| §6 | 耦合风险、回滚、清理与故障闭环 |
| §7 | 30 条真实 Electron 场景矩阵 |
| §8 | 验收命令、报告模板与完成定义 |

---

## §0 执行手册（必读）

### 0.1 角色与文件 ownership

| 角色 | 可以做 | 不可以做 |
|---|---|---|
| Composer 2.5 / Terra | React/Electron、Python、schema、测试、报告、接口决策、最终验收 | 将未验证的辅助建议直接当作协议 |
| Grok 4.5 | 主题/布局截图核对、可访问性观察、视觉回归问题单 | 修改 protocol、appserver、权限、预算、Child Runtime |
| 真实 Provider | 只提供外部模型响应 | 不能作为确定性测试的唯一判断器 |

| 范围 | 唯一 owner | 消费者 |
|---|---|---|
| `frontend/desktop-app/src/renderer/**` | Desktop renderer | Desktop CDP suite |
| `frontend/protocol-client/**`、`protocol/*.json` | 协议层 | Desktop/OpenTUI/未来 LinkAgent |
| `appserver/**` | appserver host/worker | protocol 客户端 |
| `core/subagents/**` | Child Runtime | appserver（仅通过契约） |
| `frontend/desktop-app/scripts/**` | GUI 测试工具 | CI/人工复跑 |

### 0.2 每张卡固定七步回路

```text
1. LOCATE  用 rg 找真实符号、调用链、消费者和相邻测试。
2. READ    读目标实现、协议定义、相邻 Phase 契约和现有测试。
3. WRITE   先写失败测试/schema，再写该卡白名单文件中的最小实现。
4. LINT    运行 Python/TypeScript 静态检查。
5. TEST    运行本卡命令和受影响回归。
6. CHECK   对照完成判据检查事件顺序、隔离、清理和 git diff。
7. COMMIT  每卡一个可回滚提交；跨卡合并仅发生在验收通过后。
```

发生文档/实现冲突必须暂停并记录：预期、实际证据、冲突接口、已改文件、需要的最小决策。不得在 Renderer 绕过协议，也不得以“前端先模拟”掩盖 Runtime 缺口。

### 0.3 开工自检

```powershell
cd "D:\agent-demo\RxyCode\RxyCode1_1_0"
git status --short
python -m ruff check appserver core/subagents tests
python -m pytest tests/contract/test_concurrent_api.py tests/test_subagents -q
cd frontend/desktop-app
npm ci
npm run typecheck
npm test -- --run
```

基线失败先分类为环境、已有失败或本卡回归；不可把失败直接归为“Phase C/D 正常”。任何临时 profile、配置、data dir、端口、Electron 或 worker 都必须由创建它的 runner 在 `finally` 清理。

### 0.4 八条硬约束

| 编号 | 约束 | 违反判定 |
|---|---|---|
| CD-S1 | Desktop 只使用 `protocol-client`，不 import Python、不直读 EventStore、不在 Renderer 判断权限/预算 | 跨层依赖即失败 |
| CD-S2 | 每个 Primary worker 只有一棵权威 ChildSessionManager 树 | appserver/worker 两棵树即失败 |
| CD-S3 | 事件带 `event_id/seq/timestamp/root_session_id/parent_session_id/request_id`，重放可去重并能报告 gap | 无法恢复或重复终态即失败 |
| CD-S4 | Child 的权限、审批、预算、workspace scope、lease、取消由 Runtime 执行 | 仅返回 blocked 文本即失败 |
| CD-S5 | Token 未上报必须为 `null` / `not_reported`，禁止写成 0 | 统计伪零即失败 |
| CD-S6 | runner 使用动态 CDP 端口、独立 profile/data/workspace/artifacts；只清理由自己启动的进程 | 固定端口或按名称全局杀进程即失败 |
| CD-S7 | 不复制品牌、图标或专有资产；若复用 OpenCode MIT 源码，记录 commit、license、文件和变更 | 无来源记录即失败 |
| CD-S8 | 旧 `.session-item`、`.tool-card`、`.composer` 等选择器在迁移完成前保持；新测试只依赖 `data-testid` | 旧测试无迁移即被破坏 |

### 0.5 非目标

- 不嵌入完整代码编辑器，不伪造 Phase G 的完整 Diff/Review。
- 不让子代理按角色切换模型（Phase H 范围）；Child 默认继承 Primary。
- 不改变主会话的 Phase C 并发模型，也不把 UI 状态写回 PermissionPolicy。
- 不通过复制 OpenCode 内部实现替代 RxyCode 的隔离、审计或协议设计。

---

## §1 当前代码真相

开工时重新运行下列命令，代码而不是本文件是唯一事实来源：

```powershell
rg -n "applyProtocolNotification|event/(message_delta|final|job_status|tool_begin|tool_end|done)" frontend/desktop-app/src
rg -n "ChildSessionManager|init_manager|set_event_emitter|EventStore" appserver core/subagents
rg -n "agent/invoke|task/start|subagents/capability|child_sessions" appserver protocol frontend
rg -n "9342|9371|extractTerminalMetrics|taskkill" frontend/desktop-app/scripts
```

| 接缝 | 已有事实 | 本 Phase 闭环 |
|---|---|---|
| Phase C | 跨会话并发、取消、超时和 StreamCoalescer 已有实现；C3 仍缺 GUI 无抖动证据 | CD3、CD6、CD13 |
| Renderer store | 仅消费普通 message/tool/done；无 plan/step/usage/Child tree | CD3、CD4、CD9 |
| Phase D Runtime | definitions/manager/events/tests 已存在；生产 appserver capability 默认关闭 | CD7–CD10 |
| appserver host | 主要转发 `event/*`，非 prompt Child 通知链不完整 | CD8 |
| EventStore | 有 cursor/event 类型但未成为生产 Child tree 权威日志 | CD7、CD9 |
| GUI probes | 固定 9342/9371；token 未上报曾被归零 | CD11、CD12 |

### 1.1 现状边界

`task/start` 和 `agent/invoke` 必须被路由到 parent 对应的 `AgentHost`/worker，而不是调用进程单例 manager。Child event 不可被转换成聊天文本再回传；Desktop 需要结构化通知以显示树、审批归属、时间线和 usage。EventStore 必须存入 RxyCode data directory，绝不写入用户 workspace。

---

## §2 公开产品研究与采用边界

| 来源 | 观察到的公开行为 | 本 Phase 采用 | 明确不采用 |
|---|---|---|---|
| [Codex Desktop](https://openai.com/index/introducing-the-codex-app/) | 项目/线程组织、并行任务、线程内审查、任务中心 | 三栏任务指挥台、会话状态、并行可见性、右侧检查器 | 品牌、资产、完整 review/diff |
| [Google Antigravity](https://developers.googleblog.com/en/build-with-google-antigravity-our-new-agentic-development-platform/) | Manager 与编辑器分离，artifact/evidence 优先 | Activity、产物/证据摘要、后台任务 | 专有 UI/命名 |
| [Jules](https://jules.google/docs/code/) | 活动流、可伸缩检查器、完成摘要 | 文档式事件流、Inspector、最终摘要 | 其代码审查实现 |
| [OpenCode Agents](https://opencode.ai/docs/agents/) | `@agent`、Primary/child、父子导航、状态语义 | `agent/invoke`、Child tree、显式导航 | 内部实现复制 |

若未来实际复用 OpenCode：提交说明和报告必须写 `anomalyco/opencode` 的精确 commit、MIT LICENSE、复用文件、保留 notice 与改动摘要。仅参考公开文档不构成源码复用。

---

## §3 任务指挥台设计

### 3.1 布局与信息层级

```text
┌──────────────── project / connection / diagnostics ────────────────┐
│ Projects · sessions          Task activity                Inspector │
│ search · states · child cnt  requirement · plan · steps    Activity │
│ running / approval / failed  tools · final · composer      Agents   │
│                                                          Usage        │
└─────────────────────────────────────────────────────────────────────┘
```

| 宽度 | 结构 | 不可退化行为 |
|---:|---|---|
| ≥1280px | `248px / minmax(0,1fr) / 400px` 三栏常驻 | 三栏独立滚动，Composer 固定在中栏 |
| 960–1279px | 左栏约 208px，右栏为可开关 sheet | 会话和 active task 仍常驻 |
| <960px | 56px 图标 rail；导航/检查器为按钮打开的 sheet | 不可直接隐藏会话入口 |

根文档 `overflow: hidden`；每栏自己的 `overflow:auto`。标题区显示工作区、分支、模型和连接摘要；Start/Stop 只在 Diagnostics，顶栏只留轻量连接状态。工具、MCP、Skill、子代理都是可折叠事件行，文本/图标/aria-label 三者共同表达状态。

### 3.2 主题和可访问性

- `system | light | dark` 三态持久化在 renderer localStorage；默认 system，主题仅通过 `data-theme` 语义 token 改写。
- 采用 4/8px 间距、12/14/16/20px 层级、系统 UI 字体；不下载外部字体。
- 使用 Lucide SVG；无 emoji 作为结构图标；图标按钮最小 40px，带 `aria-label` 与 tooltip。
- 焦点环可见，tab 顺序等于视觉顺序，错误用 `role=alert`，`Esc` 关闭 dialogs/sheets 并还原触发焦点。
- 支持 `prefers-reduced-motion`；流式文本仅批量更新，不以宽高动画制造抖动。

### 3.3 UI 状态模型

```ts
type RunState = 'queued' | 'running' | 'approval' | 'succeeded' |
  'failed' | 'cancelled' | 'timed_out'
type TokenCount = number | null
interface UsageSnapshot { input_tokens: TokenCount; output_tokens: TokenCount; cache_hit_tokens: TokenCount }
interface ChildSessionView { session_id: string; root_session_id: string; parent_session_id: string | null; agent_id: string; state: RunState }
```

每个 root session 独立保存 messages、tools、plan、steps、progress、job state、usage、children 和事件去重集合。切换会话只改变 selector，绝不共享流文本/工具卡。缺少 token 显示为 `not reported`，缓存命中率仅在 input/cache-hit 都是数字且 input 大于零时计算。

---

## §4 协议和兼容契约

### 4.1 版本与路由

主协议升为**向后兼容的 minor**。旧客户端可以忽略未知 `child_session/*` 通知；新客户端 capability 不可用时隐藏 Agents 功能，不显示假数据。

| 方法 | 请求 | 响应 | 权威 owner |
|---|---|---|---|
| `subagents/capability` | `{parent_session_id?}` | feature flags、protocol version | AgentHost/worker |
| `subagents/list` | `{parent_session_id}` | 可见 AgentDefinition[] | AgentHost/worker |
| `agent/invoke` | `{parent_session_id, agent_id, prompt, request_id}` | child task accepted | AgentHost/worker |
| `task/start` | `TaskRequest` | task accepted | AgentHost/worker |
| `child_sessions/list` | `{root_session_id}` | `{sessions,cursor}` | EventStore/manager |
| `child_sessions/events` | `{root_session_id,cursor,subtree_session_id?}` | `{events,next_cursor,gap_detected}` | EventStore |
| `child_sessions/cancel` | `{root_session_id,session_id}` | `{cancelled,affected_session_ids}` | manager |
| `child_sessions/retry` | `{root_session_id,session_id,request_id}` | accepted retry descriptor | manager |

### 4.2 ChildSessionEvent

```json
{
  "event_id": "cse_01", "seq": 12, "timestamp": "2026-08-11T10:00:00Z",
  "root_session_id": "root_01", "parent_session_id": "root_01",
  "session_id": "child_01", "request_id": "req_01",
  "type": "child_session/tool_call", "payload": {"tool_name":"read"}
}
```

通知集合：`created|queued|started|context_ready|tool_call|approval_required|progress|partial_result|completed|failed|cancelled|timed_out|denied|recovered`。event_id 去重，seq 单调；cursor 缺口必须响应 `gap_detected: true`，客户端调用 list/events 重建树，不能猜测遗漏事件。Parent interrupt 递归取消所有后代、工具和 lease；显式 child cancel 只取消目标子树。

### 4.3 审批与权限

Child 的 `ask` 复用既有审批 broker，界面同时显示 child session、agent、匹配规则、风险、路径/命令与影响范围。Renderer 只能提交 approved/rejected；ChildRuntime 才执行 permission、budget、scope、lease/cancel。写入 lease 冲突需稳定报 conflict，释放后 retry 才能取得 lease。

### 4.4 自动恢复协议（本 Phase 的强制补充）

Desktop 不把一次工具错误直接渲染成任务终态。恢复生命周期由请求级 `RecoveryTracker` 唯一拥有，状态只允许沿以下路径变化：

```text
idle → detected → analyzing → retrying → recovered
                                      └→ exhausted
```

恢复分为三类，不能互相冒充：

| 类型 | 触发 | 是否调用模型 | 可重复动作 |
|---|---|---:|---|
| `transport_retry` | READ 工具或 LLM 的网络、超时、429/5xx 等瞬态错误 | 否 | 仅限无副作用的同一请求，指数退避 |
| `model_recovery` | ToolMessage 返回参数错误、工具失败或可替代工具提示 | 是 | 修正参数、选择替代工具或停止 |
| `graph_replan` | Validator/Reflection 发现任务失败 | 是 | governed retry/replan，受 graph step/replan budget 限制 |

新增通知的公共字段必须包含 `event_id/seq/timestamp/session_id/run_id/recovery_id`：

```json
{
  "method": "event/recovery_attempt",
  "params": {
    "session_id": "root_01", "run_id": "run_01", "recovery_id": "rec_01",
    "event_id": "evt_12", "seq": 12, "timestamp": "2026-08-11T10:00:00Z",
    "attempt": 2, "strategy": "corrected_arguments",
    "replacement_call_id": "tool_03",
    "display_summary": "正在修正参数后重试"
  }
}
```

不得把 chain-of-thought、完整凭据或未经脱敏的异常堆栈发送给 Renderer。GUI/CLI 默认只显示一行灰色摘要；成功时折叠为“遇到问题并已自动恢复 · N 次尝试”，只有展开才显示安全摘要。只有 `exhausted` 才能生成主时间线的最终错误和失败 Final Answer。

安全边界不可由前端绕过：READ 才允许 transport retry；WRITE/DANGER 必须先查 Tool Journal，结果未知时禁止重放；用户取消要同时停止模型分析、backoff、工具、Child 和 lease。Parent、Child、sibling 各自拥有独立的 tracker 和 token 账本。

---

## §5 任务卡

### CD1 · 协议类型基线

**优先级：**P0　**工时：**4h　**依赖：**无　**owner：**Composer/Terra

**文件：**修改 `protocol/schema.json`、`protocol/subagents_schema.json`、`frontend/protocol-client/**`；测试 `tests/contract/**`、protocol-client type tests。

1. 先写失败测试：新路由和 `child_session/*` 类型在 generated TS 可导入。
2. 只增加兼容 minor 定义和生成入口；不让 renderer 自行声明重复类型。
3. 运行 codegen/typecheck。

**完成判据：**

- [ ] 路由、请求/响应、notification union 和兼容版本可由 Python/TS 两侧消费。
- [ ] unknown notification 对旧 reducer 是 no-op。

**验收：**`python -m pytest tests/contract -q; cd frontend/protocol-client; npm run generate; npm run typecheck`

### CD2 · 主题 token 与三栏壳

**优先级：**P0　**工时：**8h　**依赖：**CD1　**owner：**Terra

**文件：**修改 `App.tsx`、`assets/main.css`；测试 renderer layout/theme tests。

先为 `data-theme`、断点、root 无滚动、独立 pane scroll、窄屏 navigation sheet 写 DOM/CSS regression tests，再实现 token 化外壳。保留 `.topbar`、`.main-layout`、`.chat-column` 等兼容 class；添加 `data-testid="task-command-center|session-nav|task-main|inspector"`。

**完成判据：**

- [ ] dark/light/system 不使用组件内硬编码颜色。
- [ ] 1280/1024/768/375 截图均可访问会话入口和 Composer。
- [ ] 旧 selectors 仍命中。

**验收：**`npm test -- --run; npm run typecheck; npm run build`

### CD3 · Phase C 任务、计划、步骤与 usage reducer

**优先级：**P0　**工时：**6h　**依赖：**CD1　**owner：**Terra

**文件：**修改 `conversationStore.mts`；测试 store/reducer。

先写每会话隔离的 queued/running/approval、plan、step、progress、usage、null token tests；再消费 `event/plan`、`event/step`、`event/progress`、`event/task_started`、`event/task_complete`、`event/token_usage`。每条通知只改变其 session_id 对应分片。

**完成判据：**

- [ ] 两会话并发时消息、工具、进度和 usage 不串流。
- [ ] 缺少 token 字段显示/导出为 `not_reported` 而非 0。

**验收：**`npm test -- --run conversationStore; npm run typecheck`

### CD4 · Activity/Agents/Usage 检查器

**优先级：**P0　**工时：**8h　**依赖：**CD2、CD3　**owner：**Terra

**文件：**新增 focused renderer components；修改 `ChatArea.tsx`、`SessionList.tsx`；测试 renderer。

将 Assistant 内容改为文档式活动流：要求、plan、steps、工具/MCP/Skill 可折叠行、final summary 和 Composer。右栏只实现 Activity/Agents/Usage；没有 capability 时不显示空 Diff。左栏列出 running/queued/approval/failed 和 child 数量。

**完成判据：**

- [ ] 状态不只靠颜色，工具卡可折叠且包含文本状态。
- [ ] Activity 的 DOM 更新批次可由测试采样，流式切换不会把其它 session 的 delta 写入当前任务。

**验收：**`npm test -- --run renderer; npm run screenshots:desktop`

### CD5 · Dialog、Diagnostics 与键盘行为

**优先级：**P1　**工时：**4h　**依赖：**CD2　**owner：**Terra

先写焦点、Esc、恢复焦点、风险摘要和错误 aria-live 的失败 tests；后实现 dialog/sheet primitive。Start/Stop 移入 Diagnostics，顶栏只显示连接状态。审批显示 session/agent/rule/path/command，且 child 标识不可省略。

**完成判据：**

- [ ] Esc 不会误取消运行，仅关闭最上层 dialog/sheet。
- [ ] 焦点不逃逸，键盘可完成 approve/reject。

**验收：**`npm test -- --run approval settings; npm run typecheck`

### CD6 · StreamCoalescer GUI 证据

**优先级：**P0　**工时：**4h　**依赖：**CD3、CD4　**owner：**Terra

为连续 delta、会话快速切换和主线程长任务写 deterministic Electron test。采集 MutationObserver 批次、event seq、frame/long-task 计数，证据写入 artifact；不以肉眼“看起来平滑”替代证据。

**完成判据：**

- [ ] 非 active session 的 stream 不污染 active DOM。
- [ ] C3 记录了合并前后批次和无持续长任务证据。

**验收：**`npm run stress:desktop -- --scenario stream-isolation`

### CD7 · Worker 内 ChildSessionManager bootstrap

**优先级：**P0　**工时：**6h　**依赖：**CD1　**owner：**Composer/Terra

**文件：**修改 `appserver/agent_worker.py`、`core/subagents/registry_provider.py`；测试 execution bridge/routes/events。

先写 worker bootstrap 后 capability 从显式 `RXYCODE_SUBAGENTS*` 开关读取、默认关闭、每 Primary 一棵 manager 和 data-dir EventStore 的失败测试；再把 manager/definitions/policy/event store 放入 worker state。禁止进程 singleton 同时成为权威树。

**完成判据：**

- [ ] 未设置开关 capability 为 disabled；测试开关才 enabled。
- [ ] EventStore 路径位于 RxyCode data directory，非 workspace。

**验收：**`python -m pytest tests/test_subagents/test_execution_bridge.py tests/test_subagents/test_appserver_routes.py -q`

### CD8 · AgentHost 路由和 Child 通知转发

**优先级：**P0　**工时：**6h　**依赖：**CD7　**owner：**Composer/Terra

先写 host 对 `agent/invoke`、`task/start`、`child_sessions/*` 的 worker RPC tests，及 prompt 之外 Child notification 持续转发 tests；后实现稳定 notification emitter 和 per-parent routing。task/start 要异步接受，不能阻塞 stdio dispatch。

**完成判据：**

- [ ] 多 Primary 的方法路由到各自 worker。
- [ ] child_session/* 能从 worker 穿过 host/server 到 protocol client。

**验收：**`python -m pytest tests/test_subagents/test_appserver_routes.py tests/test_appserver -q`

### CD9 · Child 事件规范化、重放与 Desktop tree

**优先级：**P0　**工时：**8h　**依赖：**CD3、CD7、CD8　**owner：**Terra

先写 event_id 去重、seq gap、cursor replay、parent/child tree 和 child terminal state reducer tests；后将 manager 原始事件包装成 §4.2 的 ChildSessionEvent，并以 EventStore 重放。Desktop Agents 面板仅根据协议树渲染和导航。

**完成判据：**

- [ ] 断线恢复不重复 completed/final，gap 可见并可重建。
- [ ] Parent/Child navigation 不改变另一 Primary 的 tree。

**验收：**`python -m pytest tests/test_subagents/test_events.py -q; npm test -- --run childSession`

### CD10 · ChildRuntime 权限、审批、预算、scope、lease 和取消

**优先级：**P0　**工时：**10h　**依赖：**CD7–CD9　**owner：**Composer/Terra

按每个边界分别写 red test：ask→broker→approved/rejected、budget/step/wall/depth terminal reason、lease conflict/retry、parent recursive cancel、child subtree cancel。最小实现必须在真正 tool execution 前执行 policy/scope/lease/budget，清理 tool/lease/descendant。

**完成判据：**

- [ ] 任何 denied/timeout/cancel 都是结构化终态并写 event store。
- [ ] sibling 只读 Child 不被写入 Child 审批阻塞。

**验收：**`python -m pytest tests/test_subagents -q; python -m pytest tests/contract/test_concurrent_api.py -q`

### CD11 · 共用 CDP harness 与资源隔离

**优先级：**P0　**工时：**6h　**依赖：**CD2–CD6　**owner：**Terra

抽取动态调试端口、独立 profile/data/workspace/config backup/artifact、WebSocket/Electron/appserver 进程树 cleanup。只保存启动时 PID，finally 精确关闭所属树；禁止 `taskkill /IM` 和固定 9342/9371。

**完成判据：**

- [ ] 两 runner 并发启动无端口冲突。
- [ ] 成功、断言失败、超时三条路径都恢复配置并无残留端口/lease/RPC。

**验收：**`npm run stress:desktop -- --self-test-cleanup --parallel 2`

### CD12 · token/结果/清理可审计采集

**优先级：**P0　**工时：**4h　**依赖：**CD11　**owner：**Terra

先写无 usage payload 输出 `not_reported` 的失败 test；后实现 token、cache ratio、wall/active/queue、timeline、DOM/protocol/screenshot、final answer/产物、cleanup proof 的 JSON 采集。缓存率为加权 `sum(cache_hit)/sum(input)`，未知值不得参与分母。

**完成判据：**

- [ ] API key 从日志、artifact 和报告中脱敏。
- [ ] 配置 byte-for-byte restore 可证明。

**验收：**`npm run probe:gui -- --self-test-usage`

### CD13 · 确定性 30 场景三轮

**优先级：**P0　**工时：**8h　**依赖：**CD1–CD12　**owner：**Terra

保留 DTS-01–18 入口并扩展 DTS-19–30。Fake appserver 必须按真实协议模拟多 session、Child tree、approval、cursor/connection、lease 和 usage null；不能只断言 mock 被调用。每轮将结果存入独立 artifacts。

**完成判据：**

- [ ] 30/30 连续三轮通过。
- [ ] N=2 deterministic wall time `< serial × 0.7`。

**验收：**`npm run stress:desktop -- --suite cd30 --rounds 3`

### CD14 · 真实模型 30 场景与失败闭环

**优先级：**P0　**工时：**按 provider 限流　**依赖：**CD13　**owner：**Terra

28 条使用 `opencode-go/deepseek-v4-flash`；DTS-15、DTS-30 固定 `zen/gpt-5.6-luna`，禁止 Luna 走 Go gateway。Child 继承 Primary。每场运行前备份 active model 和 MCP 配置，finally byte-for-byte 恢复。真实失败先缩小为 protocol/reducer/runtime/layout，先写复现，再作最小修复；偶发失败需连续两次真实通过才回全量。

**完成判据：**

- [ ] 30 个真实 Electron 场景都产生 prompt、provider/gateway、timeline、截图、final/产物和 cleanup evidence。
- [ ] 真实并发以事件时间线证明重叠，不以 provider latency 判断性能。

**验收：**`npm run stress:desktop:real -- --suite cd30 --provider-plan artifacts/provider-plan.json`

### CD15 · 视觉/响应式审计

**优先级：**P1　**工时：**4h　**依赖：**CD13、CD14　**owner：**Terra（Grok 仅观察）

运行 1440/1024/768/375 深浅主题矩阵，检查根滚动、pane 溢出、Composer 遮挡、会话入口、focus、reduced motion、dialogs。Grok 可提交问题单；Terra 将每个结论转为截图 + 可重复 test 或列为明确限制。

**验收：**`npm run screenshots:desktop -- --themes dark,light --widths 1440,1024,768,375`

### CD16 · 最终报告、全量验证与本地 master 合并

**优先级：**P0　**工时：**4h　**依赖：**CD1–CD15　**owner：**Composer/Terra

报告按 §8 模板写入。只 force-add 本文档；不改 `.gitignore`，不批量添加其它被忽略的计划。验证全部通过后，合并隔离分支到本地 master 并提交；不 push、不建 PR。

**验收：**见 §8.1 的机械命令与 §8.3 完成定义。

---

### CD17 · 自动恢复、Final Answer 与 CLI/GUI 语义一致性补充卡

**优先级：**P0　**工时：**8h　**依赖：**CD1、CD3、CD4、CD6、CD10　**owner：**Composer/Terra

**文件：**修改 `recovery/tracker.py`、`appserver/tui.py`、`core/graph.py`、`core/agent_v2.py`、`execution/tool_orchestrator.py`、`frontend/desktop-app/src/renderer/src/lib/conversationStore.mts`、`ChatArea.tsx`；测试 recovery、graph、protocol-client、Desktop reducer、CDP suite。

1. 先写四类失败测试：READ 瞬态错误退避成功；工具错误回灌模型并由修正参数/替代工具成功；Reflection 选择 retry/replan；恢复耗尽前不出现最终错误。
2. 为每个请求建立唯一 `RecoveryTracker`，把 transport/model/graph 三类事件映射到 §4.4 schema；不得把模型内部思考发送给客户端。
3. 对 WRITE/DANGER 在自动恢复前查询 Tool Journal；`unknown` 结果停止并显示需人工确认，禁止重复写入。
4. GUI reducer 按原时间线位置更新同一个 ToolActivity；恢复成功只显示折叠摘要，`recovery_exhausted` 才追加 ErrorItem 和失败 FinalAnswerItem。
5. CLI 使用同一事件语义；中间错误不得被渲染成任务终态。Parent、Child、sibling 的 tracker、usage 和取消必须相互隔离。

**示例验收序列：**

```text
UserPrompt → ToolBegin(read) → ToolEnd(error)
→ RecoveryStarted(model_recovery) → RecoveryAttempt(corrected_arguments)
→ ToolBegin(read, replacement_call_id) → ToolEnd(ok)
→ RecoveryResolved → FinalAnswer
```

**完成判据：**

- [ ] transport retry、model recovery、graph replan 均有结构化事件和计数。
- [ ] 恢复产生的 input/output/cache token 计入正确的 Parent 或 Child，不重复累计。
- [ ] 恢复成功不产生正式错误；耗尽后才生成失败 Final Answer。
- [ ] 取消会停止 backoff、模型分析、后续 tool call 和 Child descendants。
- [ ] 无 secrets、chain-of-thought、原始堆栈进入 Renderer 或 task replay store。

**验收：**`python -m pytest tests/test_core/test_reflection_graph.py tests/test_appserver/test_protocol_tui_recovery.py tests/test_appserver/test_desktop_task_store.py -q; cd frontend/desktop-app; npm test -- --run; npm run typecheck; node scripts/desktop-cd-suite.mts --mode=deterministic --rounds=1 --only=DTS-12,DTS-13,DTS-21,DTS-24,DTS-25,DTS-28,DTS-30`

---

## §6 耦合风险、回滚和故障闭环

| 风险 | 防线 | 回滚范围 |
|---|---|---|
| store 共享状态导致串流 | 每 session 分片、通知 contract tests、快速切换 CDP | 仅 reducer/component commit |
| schema 升级破坏旧客户端 | minor、unknown no-op、codegen/typecheck | schema + generated type commit |
| manager 双权威树 | worker ownership integration test | bootstrap/routing commit |
| Child 写入绕过 policy/lease | Runtime pre-tool gates、lease/cancel tests | runtime commit |
| test 清理误杀用户进程 | PID ownership、finally、port/process assertions | harness commit |
| 外部模型波动 | deterministic 先行、真实重试规则、明示 not_reported | real-suite config only |

修复循环：捕获协议/DOM/事件/进程证据 → 用最小 deterministic test 复现 → 判断 root cause 所在层 → 一项最小修改 → 本卡与受影响 suite → 共享 store/protocol/routing/layout token 变更必须重跑全部 30 → 同一偶发真实问题连续两次通过 → 最终全量。连续三次不同修复均失败时停止扩展修复，重新审计架构和 owner。

---

## §7 CD30 真实业务场景矩阵

| ID | 真实用户任务与断言重点 | 模型 |
|---|---|---|
| DTS-01–18 | 保留原 Desktop 压力场景：多轮代码任务、工具、MCP、Skill、审批、取消、错误恢复、模型/工作区设置 | Go Flash，DTS-15 Zen Luna |
| DTS-19 | 四个发布审计同时运行；比较 session 流、usage、并发重叠 | Go Flash |
| DTS-20 | 同一会话重复提交；第二次稳定 busy，不损坏第一轮 | Go Flash |
| DTS-21 | 生产事故调查；Primary 并发 `explore`/`scout`，含 Skill、代码和外部资料 | Go Flash |
| DTS-22 | 两个 Primary 各派 Child；两棵树、工具/usage 完全隔离 | Go Flash |
| DTS-23 | 支付模块审查；用户 `@reviewer`，在 Parent/Child 间导航 | Go Flash |
| DTS-24 | 数据迁移 Child 等审批；只读 sibling 继续，审批归属 Child | Go Flash |
| DTS-25 | 工作区选错后取消 Parent；所有 Child 停止，另一会话完成 | Go Flash |
| DTS-26 | 两 leased-write Child 争同一文件；一方冲突，释放后 retry | Go Flash |
| DTS-27 | 成本受限审计；concurrency/steps/token/wall/depth 可解释终态 | Go Flash |
| DTS-28 | 发票对账；本机 MCP 失败而 Skill 成功，Parent 部分成功摘要 | Go Flash |
| DTS-29 | worker/appserver 中断后 cursor 恢复；无重复终态/事件 gap | Go Flash |
| DTS-30 | Zen Luna 长流发布审计；快速切换 Parent/Child/会话，C3 无抖动、无串流、usage 正确 | Zen Luna |

每条必须记录完整 prompt（贴近表中业务，不写“test”指令）、provider/gateway/model、Parent/Child IDs、事件/并发时间线、工具/MCP/Skill/审批/文件、完整 final answer 或结果文件、input/output/cache-hit/ratio 或 `not_reported`、wall/active/queue、截图/DOM/protocol/error/cleanup artifact。原始 JSON、完整回答、事件和截图只存未跟踪 `artifacts/desktop-cd-suite-<timestamp>/`。

---

## §8 验收与完成定义

### 8.1 机械验收

```powershell
python -m ruff check appserver core/subagents tests
python -m pytest tests/contract/test_concurrent_api.py tests/contract/test_stream_coalescing.py -q
python -m pytest tests/test_subagents -q
python -m pytest tests/test_appserver -q
cd frontend/protocol-client; npm run generate; npm run typecheck
cd ../desktop-app; npm test -- --run; npm run typecheck; npm run build
npm run stress:desktop -- --suite cd30 --rounds 3
npm run stress:desktop:real -- --suite cd30 --provider-plan artifacts/provider-plan.json
cd ../..; python -m pytest tests -q
git diff --check
```

### 8.2 最终报告模板

`docs/DESKTOP-CD-INTEGRATION-STRESS-REPORT-<执行日期>.md` 至少包含：

1. 基线、范围、官方参考链接与“采用/未采用”说明；改造前后布局截图。
2. 深/浅、1440/1024/768/375 的截图审计和已知限制。
3. DTS-01–30 逐项 prompt、模型/provider/gateway、Parent/Child、时间线、工具/MCP/Skill/审批/产物、final answer/文件、token 和 cleanup 结果。
4. 总 token、Parent/Child 分项、加权 cache hit ratio（并列 not_reported）。
5. 并发 overlap、deterministic serial baseline、取消延迟、C3 stream batch/long-task 证据。
6. 所有问题的根因、修复 commit、回归命令、最终状态。
7. 进程、端口、profile、config、lease、RPC 清理证明；未关闭风险不得隐瞒。

### 8.3 完成定义

- [ ] CD1–CD17 的测试与完成判据全部满足。
- [ ] 30 条确定性场景连续三轮通过，真实 30 条有可审计证据。
- [ ] 子代理 feature 默认关闭、显式测试开关开启；事件和审批按 owner 端到端贯通。
- [ ] 深浅主题、三组断点、键盘/焦点/reduced-motion 无阻断缺陷。
- [ ] 未上报 token 未被记为 0，所有临时资源均清理。
- [ ] 仅本计划通过 `git add -f` 纳入被忽略 docs/plans；最终报告、代码、测试均已提交到本地 master。

### 8.4 自动恢复专项完成定义

- [ ] READ 瞬态错误、工具参数错误、替代工具、Reflection retry/replan、永久错误和 WRITE 未知结果均有独立回归证据。
- [ ] GUI/CLI 对中间失败、恢复中、恢复成功、恢复耗尽和 Final Answer 使用同一状态语义。
- [ ] 任何恢复事件都具备 `event_id/seq/timestamp`，重连后可去重、重放并报告 gap。
- [ ] 报告按 transport retry、model recovery、graph replan 分项统计次数、耗时、token 和最终结果。
