# B10 独立模型审计证据链（2026-08-11）

B10 卡（单 agent 桥接层）审计产物。审查角色：zen/gpt-5.6-luna（`https://opencode.ai/zen/v1`）。

## 实现范围

1. **core/bridge/base.py**：AgentBridge 抽象基类（spawn → invoke 流式 → stop kill → usage）+ BridgeConfig（token 预算 5 万 / 时间预算 300s / 结果截断 2000 字符，全可配）
2. **core/bridge/acp.py**：ACP 适配器（JSON-RPC over stdio，NDJSON 逐行，session/new_prompt + agent_message_chunk/agent_thought_chunk/tool_call/session/result）
3. **core/bridge/cli.py**：CLI 兜底适配器（grok agent stdio，task_delegate lineage-only）
4. **core/bridge/lifecycle.py**：run_official_agent 编排——asyncio.timeout 时间预算 + token 预算累计 + 超限 kill + 结果截断回流
5. **tools/run_official_agent.py**：StructuredTool（agent/task/time_budget_s/max_result_chars），DANGER 风险
6. **core/builtin_tool_registration.py**：run_official_agent_enabled 条件注册（默认 False，CB8）
7. **api_server.py /bridge 命令**：默认禁用提示 / 用法提示 / claude+grok 分派 / 结果回流
8. **config/settings.py**：execution.run_official_agent_enabled 默认 False

## 验收证据

- `b10-pytest-v.txt`: 14 passed（test_agent_bridge：委托/流式/回收/超时 kill/token 预算 kill/工具注册门控/前缀零污染）
- `b10-api-tests.txt`: 2 passed（/bridge 默认禁用 + 用法）
- `b10-ruff.txt`: All checks passed
- 全量回归 test_core+test_cache+test_memory+test_validation+test_execution+test_tools+test_bridge+test_api: 9105 passed, 2 failed（P7 lazy-import 遗留）
- evals GATE PASS 94.7% ≥ 89.5%（零回归，1 改善）；唯一失败 websearch-summary 基线即 FAIL
- 验收方式：并行 4 组 + 失败重试 3 轮（本地工具，不提交）

## 缓存纪律（桥接不破坏主链路）

- 独立子进程/独立 session/独立前缀（ACPBridge/CLIBridge 各 spawn 独立进程）
- lineage-only 不复制主历史（task_delegate 只带任务描述+引用）
- 结果摘要 ≤ max_result_chars（默认 2000 字符）回流主 harness
- 主链路前缀零污染：test_bridge_does_not_touch_main_token_stats（桥接不写主 token_stats）

## 审计轮次（2 轮）

| 轮次 | 结论 | 核心阻断项 |
|---|---|---|
| R1 | FAIL | usage 多字段重复计数；未读 B9 契约；无进程树 kill；结果摘要无硬上限；/status cache_rate 无真实数字；thinking/reasoning/窗口/cache 规范未覆盖（旁路 CLI 自行管理，已澄清范围） |
| R2 | **PASS** | 无阻断项，判据 1-5 + 限制性规范 7 条 + CB1-CB8 全过 |

## 最终结论

zen/gpt-5.6-luna 第 2 轮审计 **PASS**：B10 完成判据 1-5 全过，模型限制性规范 7 条 + 八条硬约束 CB1-CB8 无违反。
B10 卡可在开发文档验收处打钩（2026-08-11）。

