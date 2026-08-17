# Phase E · 执行过程记录（契约测试先行 + 边界说明）

本文件记录 §0.2 七步循环的执行过程与 E 层边界事项，供审计核对。

## 契约测试先行（§0.2 步骤 3）

每张卡的实际执行顺序均为：**先写 `tests/contract/test_<卡>.py`
（契约测试）→ 运行（红）→ 实现白名单文件（绿）→ ruff → 验收命令 →
单 commit**。git 历史每卡一个 commit（测试与实现同 commit）无法单独
分离"测试先行"，但执行过程为：契约测试先落盘、实现随后。证据：

- E1：`test_eventbus.py` 先写（18 用例覆盖 §5 E1 判据），再实现
  `appserver/eventbus.py`；
- E2：`test_agent_task_lifecycle.py` 先写（20 用例），再实现
  `appserver/agent_task.py`；
- E3：`test_agent_runtime.py` 先写（41 用例），再实现
  `appserver/agent_runtime.py`；
- E4：`test_agent_protocol.py` 先写（52 用例），再实现
  `protocol/notifications.py` 的 AgentEvent + schema/TS 生成；
- E5：`test_agent_quota.py` 先写（7 用例），再实现开关与限流；
- E6：`test_agent_context.py` 先写（18 用例），再实现
  `appserver/agent_context.py`；
- E7：`bench_multi_agent.py` 与基准 JSON 同卡提交。

## E 层边界说明（超出白名单/依赖外部参与者的项）

以下各项在当前执行环境中无法在 E 卡白名单内完成，已按文档边界处理：

| 项 | 文档归属 | E 层现状 | 说明 |
|---|---|---|---|
| 真实 SSE/stdio agent 事件接线 | E4 判据（SSE=api_server StreamTUI，stdio=appserver JSON-RPC） | stdio：真实 `write_message_sync`/`parse_line` 编解码往返测试；SSE：线格式（`data: <json>` + `type: agent_*`）往返测试 | `api_server.py` 的 StreamTUI 无 `agent_*` 输出类型且不在 E4 白名单；完整通道接线属 F 层消费方（F13） |
| TeamEvent 分派 | F3 定义 | E4 判据（AgentEvent 拒绝 `event/team_*`）已满足并有测试 | TeamEvent 本身 F3 实现 |
| namespace role/model 注入与碰撞 | F17（"唯一性范围 = role/model 组合级…F17 负责生成"） | E3 只读接收 + 构造期 fail-closed 校验 + 键构建 | 多模型策略属 F 层 |
| Grok 4.5 强制参与 | §0.1/E4 | 执行环境无 Grok 实例；以 E4-grok-field-crosscheck.md 逐字段对照生成物替代 | 参与者不可用为环境约束 |
| 全量回归 6 失败 | §8.2 | 已正式登记为验收基线失败（acceptance-baseline-failures.md，主工作区逐一复现） | 属 B/P7/C8/master 责任阶段 |

## 白名单越界（依赖驱动的必要改动）

| 卡 | 越界文件 | 原因 | 契约测试锁定 |
|---|---|---|---|
| E3 | `appserver/agent_task.py` | E3 熔断契约需要 E2 的 `_last_error` 暴露（BudgetExceededError 链） | test_budget_breaker_* |
| E4 | `appserver/agent_task.py` / `appserver/eventbus.py` + E1/E2 测试 | E4 残留扫描判据强制：appserver 不得有 `class AgentEvent`，E1 运行时事件改名 `BusEvent` 收口 | 全契约套件 |
| E6 | `tests/contract/test_agent_runtime.py` | E5 默认串行后 E3 并行测试需显式 parallel_limit | test_two_agents_run_in_parallel_without_blocking |

## 事件快照记账（§4.1 E3 运行时层）

- spawn 起 `tokens_used/budget_used` = 0（started 事件携带，契约测试
  `test_lifecycle_events_carry_token_snapshot_from_spawn` 锁定）；
- 单调不减（`token_snapshot` 累计口径）；
- (run_id, task_id, attempt) 去重（`test_usage_dedup_by_run_task_attempt`）；
- 熔断事件携带最终快照（`check_budget` 发布 payload 含 tokens_used/budget_used）。
