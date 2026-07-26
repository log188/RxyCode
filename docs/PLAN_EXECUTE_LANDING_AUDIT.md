# Plan-and-Execute 工程落地审计

审计日期：2026-07-25

## 结论

用户要求的 Harness 7 层和 Reasoning 5 项都已进入生产调用链，不再是仅有类、函数或配置但无人调用的孤立实现。这里的“已落地”同时满足四个条件：存在生产入口、能沿真实调用链到达、运行状态或持久化产物可观察、具有不绕过该入口的行为回归。

## 落地矩阵

| 层 | 状态 | 生产调用链与证据 | 真实边界 |
|---|---|---|---|
| Execution Environment | 已落地 | `AgentV2.run -> bind_session -> LangGraph` 使用会话级 CWD；`CheckpointStore` 保存图快照；`ToolExecutionJournal` 保存副作用尝试；图看门狗执行轮次、并行度、工具时限、任务总时限。测试覆盖会话并发隔离、恢复、重置、取消和虚拟时钟下超过 600 秒仍继续的受控任务。 | `workspace` 是 CWD/写路径边界，不是 OS 文件系统沙箱；`docker` 才提供容器边界。当前机器无 Docker，镜像未实机构建。CPU 只在 Docker 模式强制。 |
| Tool Interface | 已落地 | 内置工具与动态 MCP 工具都注册到 `ToolOrchestrator`，统一经过 Schema、风险、Plan 只读、路径门禁、dry-run、审批、超时、只读重试、清洗、审计、evidence 与取消。MCP 使用真实 stdio JSON-RPC 进程。 | MCP 命令是明确标注的 `host_process`；远端 `readOnlyHint` 不能降低本地 WRITE 风险。 |
| Context Management | 已落地 | `MemoryManager` 动态组装用户、会话、项目、任务与 RAG 上下文；快速工具循环和图路由均触发压缩；过大任务结果先归档原文再向图注入有界副本；规划状态和执行结果按需进入 prompt。 | 压缩优先保证结构与工具关联，不承诺无损保留任意超长原文；原文通过 artifact 保留。 |
| Lifecycle & Orchestration | 已落地 | `build_graph()` 连接规划、分解、串/并行执行、校验、反思、重规划、压缩、错误恢复、综合与终止；`route_next()` 是唯一状态路由；run/graph/task/tool hooks 在生产节点发射并记录结果。 | 并行只调度依赖满足的叶任务；默认关闭并行以便渐进启用。 |
| Observability | 已落地 | `NodeSpan`、`TrajectoryLogger`、hook audit、tool evidence、append-only safety audit 和 `RunMonitor` 关联同一 run；记录 plan、步骤、replan、token、耗时和失败归因；`runtime_status()` 暴露限额、沙箱、checkpoint、journal、MCP 退避及最近失败。 | 日志和轨迹有大小/条数保留上限；敏感参数和内嵌凭据先脱敏。 |
| Verification | 已落地 | 结构化输出有提取、Schema 校验和一次 repair；`TaskTree.assert_valid_plan()` 拒绝未知依赖、不可达节点及层级/DAG 环；Validator 先做确定性 evidence 校验，再做结构化语义评分；最终输出重新核对 artifact 大小和 SHA-256。 | 写入任务没有成功 WRITE/DANGER evidence 时必定失败，模型文本不能自行宣告完成。 |
| Governance | 已落地 | `SensitiveActionPolicy` 是 ToolOrchestrator 的首个决策；`AsyncTokenBucketRateLimiter` 与 `ModelRouter` 接入所有模型角色和三条模型调用入口；异常、流中断、取消、breaker-open 都 exactly-once 结算已获 grant；审计为脱敏 JSONL。 | 限流、checkpoint 锁和 journal 协调是单进程边界，不是分布式 exactly-once。checkpoint 写失败会告警但不阻断当前回答。 |
| Prompt Engineering | 已落地 | 版本化 Planner、Executor、Validator、Reflection、Re-planner 模板由对应生产组件实际读取；包含工具纪律、Plan 只读、失败自修正、结构化格式和 `effect` 字段。 | Prompt 是策略输入，不替代确定性安全门和验证器。 |
| Planner Engineering | 已落地 | `GoalPlanner` 与 `HierarchicalDecomposer` 通过统一 structured-output 入口生成 `TaskEffect`、任务层级与依赖；计划先校验再进入 `TaskScheduler`；Re-planner 受深度、节点与重试预算约束。 | `TaskEffect.AUTO` 仅用于旧 checkpoint 兼容；新计划显式输出 effect，运行时仍会根据意图和工具风险兜底。 |
| Memory Engineering | 已落地 | 短期窗口、用户记忆、会话长期记忆、项目全局记忆、向量记忆和 graph checkpoint 均接入 Agent；会话进度可恢复。memory/history 搜索限制在许可 scope 和当前 session，路径解析后再次做根目录及符号链接边界检查。 | 长期记忆是本地持久化；没有跨主机一致性。 |
| Reflection Engineering | 已落地 | 每个任务校验后进入 `ReflectionEngine`，区分 planning、reasoning、tool、verification 错误并产出 retry/replan/terminate；失败归因进入状态、monitor 和 trajectory。 | 反思模型不能覆盖确定性失败、重试预算或终止上限。 |
| RAG（可选） | 已落地 | 启用时注册只读 `code_search`，后台索引代码库；缓存具备 TTL/LRU、generation freshness、变更后失效和 worker 状态；Planner/Executor 通过 MemoryManager 获取检索上下文。 | 当前是代码库 RAG，不是任意外部文档知识库；关闭时工具不会暴露给模型。 |

## 开源实现取样

本次参考的是可核验的官方仓库和规范样本，不声称存在一个客观、稳定的“GitHub 前 20 名”排名，也没有把不兼容实现整段 vendoring 进项目。

- [LangGraph](https://github.com/langchain-ai/langgraph) 的状态图、持久化和中断/恢复模式用于主状态机与 checkpoint 设计。
- [Gemini CLI 配置](https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/configuration.md)、[工具文档](https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/tools.md) 和 [遥测文档](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/telemetry.md) 用于轮次/沙箱/工具/可观测边界。
- [OpenAI Codex app-server](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md) 和 [Codex memory](https://github.com/openai/codex/blob/main/codex-rs/core/src/memories/README.md) 用于会话生命周期、恢复和记忆边界。
- [OpenCode compaction](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/compaction.ts)、[processor](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/processor.ts) 与 [session storage](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/session.sql.ts) 用于上下文压缩和持久状态分层。
- [OpenHands conversation state](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/state.py) 用于状态与安全审计模式。
- [MCP 2025-11-25 stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)、[lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle) 与 [tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) 用于真实 MCP 进程实现。

## 最终验收

- Python：`2320 collected`；`2311` 个可并行确定性测试和 `8` 个 serial 测试通过，共 `2319 passed`；`1` 个 opt-in live provider 测试未运行。
- 分发/安装/首启定向回归：`27 passed`；真实 wheel/sdist 构建和 `twine check` 通过，PowerShell、Git Bash、`uvx --from`、重复安装及无 uv bootstrap 均已在隔离目录实测。
- Coverage：新增分发测试前的已验证快照为核心包 `77.1%`（门槛 `67%`）、全项目 `71.7%`（门槛 `60%`）；JSON/XML/HTML 位于 `artifacts/final-coverage-20260725-r5/`，不冒充为新增测试后的重新采集结果。
- 前端：Vitest `28 files / 147 tests passed`；TypeScript build 通过。
- Windows ConPTY：交互 `15/15`，崩溃与终端恢复 `2/2`。
- Python 项目源码 compileall 通过；本次改动文件 Ruff 通过。
- Docker：当前机器没有 Docker 二进制，因此仅有静态契约和测试，不能声称镜像实机构建通过。
- GitHub 发布：本地目录没有 `.git`，公开仓库的 `v1.1.0/install.ps1` 与 `master/pyproject.toml` 当前均返回 HTTP 404；必须先把本目录作为仓库根推送并创建 `v1.1.0` tag，公网 Quick Start 才会生效。
