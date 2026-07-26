# 问题8：12 项工程能力运行时生效核验矩阵（2026-07-26）

> 核验对象：Harness Engineering 7 项 + Agent Reasoning Engineering 5 项。
> 核验层级：(a) 代码存在 → (b) AgentV2 初始化实例化 → (c) 真实 run/graph 路径调用 →
> (d) config 门控与默认态 → (e) 真实对话可观测触发（trajectory/tracing）。
> 入口核验：`main.py` 的 Ink 交互入口与 `--api` 服务入口均使用同一套
> `AgentV2` 后端能力接线，**没有任何路径跳过能力接线**。

## 总结论

**不是摆设。** 12 项能力全部真实接线（a/b/c 级全过，有 `tests/test_core/test_runtime_wiring.py` 守护）。
默认配置下 **11 项生效，1 项（RAG）默认关闭**——RAG 在你的清单中本就标注 "(Optional)"，
属预期的 opt-in 设计，已确认链路完整、开关即通（见下）。

## 生效矩阵（d 级重点）

| # | 能力 | 落地代码 | 门控配置 | 默认 | 默认下状态 |
|---|------|---------|---------|------|-----------|
| 1 | Governance | core/governance.py（限流 agent_v2:1048；路由 :552） | governance.rate_limit.enabled / model_routes | True / `{}` | ✅ 限流生效；路由接线但空表（配置 model_routes 才分流） |
| 2 | Tool Interface | execution/tool_orchestrator.py（agent_v2:660） | execution.tool_journal_enabled | True | ✅ 生效（契约+脱敏+截断） |
| 3 | Lifecycle & Orchestration | core/graph.py observed_node（:1257-1266）、checkpoints（agent_v2:605） | execution.checkpoint_enabled；lifecycle.hook_timeout_seconds | True / 5s | ✅ 生效 |
| 4 | Observability | core/tracing.py、trajectory.py、hooks.py（agent_v2:2738-2801 无条件） | 无开关（仅 retention） | — | ✅ 恒生效（且无法经 config 关闭） |
| 5 | Verification | validation/ + graph validator_node（graph:1260,663-743） | 无开关 | — | ✅ 恒生效 |
| 6 | Execution Environment | core/session_runtime.py（bind_session agent_v2:2740） | execution.sandbox_mode | "workspace" | ✅ 生效 |
| 7 | Context Management | tool_orchestrator:234-251 硬截断；memory/ | context.max_tool_output_chars=30000；summarize_tool_output=False | — | ✅ 截断恒生效；LLM 摘要默认关（仅优化项） |
| 8 | Prompt | core/prompts/templates.py（agent_v2:1884,2423） | 无开关 | — | ✅ 恒生效 |
| 9 | Planner | planning/ + goal_planner/decomposer 节点（graph:1257-1258） | 无开关 | — | ✅ 恒生效（入口即 goal_plan） |
| 10 | Memory | memory/manager.py（agent_v2:583,761,832） | memory.*（窗口参数） | — | ✅ 恒生效 |
| 11 | Reflection | validation/reflection.py + re_planner.py + graph reflection 节点（graph:776-844） | 无开关 | — | ✅ 条件生效（有 FAILED 任务即触发） |
| 12 | RAG (Optional) | rag/index.py + memory/manager.py 注入 | **rag.enabled** | **False** | ⚠️ 默认关（见下） |

## 三条关联链

- **reflection → re_planner 重规划**：✅ 默认完整可触发。validator FAILED → route "reflect"
  （graph:1204-1206）→ Reflector action=replan → route "re_plan"（graph:1211-1215）→ re_planner_node。
- **verification 失败 → recovery**：✅ 可触发，但设计为"先反思再恢复"——失败先经 reflection 中转，
  仅 stuck/超上下文/reflection-retry 三种情况直达 error_recovery（graph:1182-1186, 1141-1146, 1216-1219）。
  非断点，属路由设计。
- **RAG 索引 → 检索注入 prompt**：❌ 默认断链（rag.enabled=False）。断点三处：
  agent_v2:588 索引器不启动、memory/manager.py:259 检索短路返回空、manager.py:223/499 注入点空转。
  **链路本身完整**——将 `config.yaml` 中 `rag.enabled` 设为 `true`（并确保 embedding 可用）即全通，无需改代码。
  处置：保持默认关（你的清单标注 Optional；索引/嵌入有成本，gemini-cli 等同类也不默认开）。

## 遗留风险（低优先级，未改码）

1. Observability 无法经 config 关闭（恒开；如需可后续加 observability.enabled）。
2. ModelRouter 默认空路由：governance 分流需用户配置 `governance.model_routes` 才有实际差异。
3. parallel_enabled 默认 False：并行执行为渐进发布设计，默认串行。

## e 级（真实对话可观测触发）

结合问题7 终端实测执行：跑一次真实任务后核对 trajectory/tracing 中
run.started / graph.node.* / validator / reflection（若失败）/ hook 事件是否落盘。
