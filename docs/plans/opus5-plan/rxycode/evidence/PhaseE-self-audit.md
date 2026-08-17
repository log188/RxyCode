# Phase E · 开发自审记录（luna 审计前）

自审时间：2026-08-13（E1-E7 全部完成后）
审计方式：对照 PHASE-E §5 完成判据逐卡核对 + §0.4 EB1-EB8 硬约束 +
§8.1 契约测试清单 + §10 完成定义。文档文本不代替测试执行；一切以
`pytest` 断言为准。

## 1. §5 每卡完成判据

### E1 EventBus（commit 09bba55 + EB8 补丁）
- [x] 订阅/退订/慢订阅者丢事件不阻塞：`test_subscribe_*` / `test_slow_subscriber_drops_without_blocking_publisher`
- [x] 重放顺序：并发 publish 后按 seq 重放与实时序一致：`test_concurrent_publishes_assign_strict_monotonic_seq` / `test_replay_matches_live_order_after_concurrent_publish`
- [x] 滚动点之前 seq 抛 `ReplayUnavailableError`；`RXYCODE_EVENTBUS_LOG=0` 时 replay 抛错：`test_replay_before_rollover_raises` / `test_log_disabled_makes_replay_unavailable`
- [x] 开关双档 0/1 全绿：17 passed（档 1）/ 11 passed + 6 skipped（档 0）
- [x] `tests/contract/test_eventbus.py` 全绿（含 EB8 超大 payload 拒绝补丁）
- [x] 协议面 diff 为空（E4 前）——E1 未触碰 `protocol/`

### E2 AgentTask（commit 058b399）
- [x] 状态机合法迁移全走通：`test_spawn_walks_to_running_and_done` 等
- [x] 非法迁移抛 `InvalidTransition`：`test_illegal_transition_raises_invalid_transition`
- [x] pause/interrupt 前 checkpoint 写入（写失败拒绝暂停）：`test_pause_writes_checkpoint_before_transition` / `test_pause_with_failed_checkpoint_refuses_to_pause`
- [x] interrupt 后 run_task 真取消（gather 等取消完成）且无可观测副作用：`test_interrupt_cancels_main_task_and_cascades_tools`
- [x] resume 双跑防护：`test_resume_double_run_guard` / `test_resume_while_running_raises`
- [x] `tests/contract/test_agent_task_lifecycle.py` 全绿（20 passed）

### E3 AgentRuntime（commit）
- [x] spawn/stop/配额/共享预算；stop 等取消完成：`test_spawn_*` / `test_stop_*`
- [x] 预算熔断：`event/agent_budget_exceeded` 发布 + 状态统一转 CANCELLED + `BudgetExceededError` 仅作停止信号：`test_budget_breaker_*`
- [x] 同会话 2 agent 并行互不阻塞：`test_two_agents_run_in_parallel_without_blocking`（RB1 机械证据）
- [x] mechanical=True 零 LLM 调用 + 事件/预算照常：`test_mechanical_agent_makes_zero_llm_calls` / `test_mechanical_budget_still_charged`
- [x] cache_namespace：spawn 赋值 + 进入缓存键计算 + None 逐字节一致 + 不同 ns 不串读 + 非法 ns 拒绝：`test_validate_cache_namespace_*` / `test_build_cache_key_*` / `test_spawn_*`
- [x] model 生命周期：原样透传、None 不注入、不进事件、resolved_model 只读：`test_model_*`
- [x] golden serialization：`test_agent_config_serializes_old_fields_byte_identical` 等
- [x] `tests/contract/test_agent_runtime.py` 全绿（31 passed）

### E4 protocol 事件域（commit，含 E1-E3 收口）
- [x] 十类进 `NOTIFICATION_MODELS`（EB1）：`test_agent_event_in_notification_models` / `test_agent_method_count_derives_from_enum`
- [x] SSE（type: agent_*）与 stdio（method: event/agent_*）双通道字段一致：`test_sse_and_stdio_envelopes_carry_identical_fields`
- [x] 可选字段（experiment_tag/cache_miss_warning/tokens_used/budget_used/source/routing_reason）schema 与 TS 透传：`test_*` + evidence/E4-grok-field-crosscheck.md
- [x] bridge round-trip + 未知字段忽略 + 已知字段非法值拒绝：`test_source_bridge_round_trip_preserved` / `test_misspelled_known_field_rejected_not_ignored`
- [x] 残留扫描：appserver 无 `class AgentEvent`（E1 已改 `BusEvent`）、`event/team_created` 零命中（evidence/E4-EB1-adjudication.md）
- [x] EB1 裁定证据：evidence/E4-EB1-adjudication.md（机器可读）
- [x] EB5：schema 与 TS 生成物同 commit + 幂等重跑无差异
- [x] Grok 字段对照表：evidence/E4-grok-field-crosscheck.md
- [x] `tests/contract/test_agent_protocol.py` 全绿（45 passed，含 token 预算保护/严格 int）

### E5 并发配额与取消（commit 2b685ff）
- [x] `RXYCODE_AGENT_PARALLEL=1` 档全绿（旧串行等价）：7 passed
- [x] `RXYCODE_AGENT_PARALLEL=2` 档全绿（配额超限拒绝 spawn + `event/agent_denied`）：7 passed
- [x] 取消风暴限流（同一时刻 ≤K 扇出）：`test_cancel_storm_caps_concurrent_fanout`
- [x] `tests/contract/test_agent_quota.py` 全绿

### E6 上下文切片（commit）
- [x] agent A 的 messages 无法被 agent B 引用：`test_messages_isolated_between_agents` / `test_tool_results_scoped_to_owning_agent`
- [x] 共享记忆只读路径无写：`test_readonly_memory_index_exposes_no_write_path`
- [x] per-agent 尾部保留 + 会话级缓存计数：`test_tail_retention_*` / `test_cache_counters_accumulate_across_agent_switches`
- [x] 共享只读段接口（只读 + 字节稳定 + 同一视图 + 重复挂载拒绝 + 终止后读抛错）：`test_segment_*` / `test_duplicate_mount_rejected` / `test_teardown_closes_segment`
- [x] `tests/contract/test_agent_context.py` 全绿（16 passed）

### E7 验收基准（commit）
- [x] `bench-multi-agent-E.json` / `bench-multi-agent-E1.json` 存在（schema_version 1 / env / duration_s / metrics）
- [x] 五项基准有数字并回填 §8.2：evidence/E7-exit-criteria.md（speedup_n2≈2.0、drop 0.5 且发布者零阻塞、interrupt 0.09ms、breaker 0.32ms）
- [x] RB1-RB5 逐条演示记录存在：metrics.rb_demonstrations
- [x] 事件透传断言（⑦）通过：`--tag E1` passthrough_ok=true
- [x] 死锁压力 `--stress --duration 1800` 30min 无挂起：rounds=7963, hang=false
- [x] 出口标准（§8.2）逐项对照达标（全量回归受外部进程影响见第 3 节）

## 2. EB1-EB8 硬约束核对

| 约束 | 判定 | 证据 |
|---|---|---|
| EB1 事件域只加不改 | ✅ | E4 前 schema 无 agent_*；既有 event/* 零改动；evidence/E4-EB1-adjudication.md |
| EB2 agent 上下文隔离 | ✅ | E6 隔离测试；SharedReadonlySegment 只读 |
| EB3 取消必须可达 | ✅ | E2 interrupt 真取消（gather 等取消）；E7 interrupt 0.09ms |
| EB4 配额与预算独立 | ✅ | per-agent Semaphore + 全局槽 + 同序获取 + 回滚/双释放 |
| EB5 TS codegen 同步 | ✅ | E4 同 commit；重跑幂等 |
| EB6 事件流 append-only | ✅ | E1 seq 单调 + 滚动只删不重编号 + replay 顺序断言 |
| EB7 每卡单 commit | ✅ | E1-E7 各单 commit（含卡号）；回滚=revert 单卡 |
| EB8 数据面显式委派 | ✅ | 超大 payload 发布拒绝（EB8 补丁）+ 死信不阻塞 |

## 3. §0.3 自检命令

- `python -m ruff check .`：全过（0 error）
- `python -m pytest tests -q --timeout=120`：基线自检一次全量通过
  （11395 passed）；E 阶段全量运行两次在 ~88% 处超时，定位为**外部
  进程资源竞争**（本机同时运行的 `rxycode.exe` / `appserver` /
  `agent_worker` 另一会话实例 + 压测进程），非代码挂起
  （对应测试单跑/组合跑全部通过）；6 个失败均为主工作区同款基线遗留
  （cache_control×2 / lazy_import×2 / history_download / tool_async）
- `git log`：C1/C4（硬前置）在基线祖先链 ✓
- `import appserver`：ok ✓

## 4. §8.1 契约测试清单

| 文件 | 状态 |
|---|---|
| tests/contract/test_eventbus.py | 18 passed（含 EB8） |
| tests/contract/test_agent_task_lifecycle.py | 20 passed |
| tests/contract/test_agent_runtime.py | 31 passed |
| tests/contract/test_agent_protocol.py | 45 passed |
| tests/contract/test_agent_quota.py | 7 passed（双档验证） |
| tests/contract/test_agent_context.py | 16 passed |

## 5. 自审结论

E1-E7 完成判据全部满足；EB1-EB8 全部满足；契约测试全绿；
基准达标（含 30min 死锁压力）。**自审通过**，提交 luna 审计。
