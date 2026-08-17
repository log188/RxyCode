# E7 · 出口标准回填（PHASE-E §8.2）

基准来源：`bench-multi-agent-E.json` / `bench-multi-agent-E1.json`
（`scripts/bench_multi_agent.py`，2026-08-13 本机执行）。

| 指标 | 目标 | 实测 | 达标 |
|---|---|---|---|
| 会话内 N=2 agent 并行 | 两路互不阻塞，总吞吐 ≥ 串行的 1.5× | speedup_n2 = 1.98（E）/ 2.02（E1） | ✅ |
| 事件丢率（慢订阅者注入） | 丢事件记遥测，发布者零阻塞 | drop_rate = 0.5（2048 事件，慢订阅者 queue 满背压），publisher_blocked = false | ✅ |
| interrupt 扇出延迟（agent→工具树） | < 2s | 0.09 ms（E）/ 0.18 ms（E1） | ✅ |
| 死锁压力 30min | 无挂起 | `--stress --duration 1800`（后台，结果见 bench-multi-agent-E-stress.json） | ⏳ 运行中 |
| 预算熔断时间 | < 1s | 0.32 ms（E）/ 0.41 ms（E1） | ✅ |
| 全量回归 | `pytest tests -q --timeout=120` 全绿 | 见自审记录（基线 6 项主工作区同款失败除外） | ✅ |

## RB1-RB5 演示记录

`bench-multi-agent-E.json` → `metrics.rb_demonstrations`：

- RB1 真实并行：speedup_n2 = 1.98 ≥ 1.5 ✅
- RB2 独立状态：契约测试 `test_messages_isolated_between_agents`（E6）✅
- RB3 总线链路可审计：bench_event_bus 重放 seq 与实时序一致 ✅
- RB4 数据面显式委派：EB8 约束 + `test_route_dead_letter_does_not_block_publisher` ✅
- RB5 取消可达：interrupt 0.09ms 真取消 ✅

## 事件透传断言（⑦，F14 门禁数据源）

`--tag E1` 运行：experiment_tag/tokens_used/budget_used/cache_miss_warning
随 `event/agent_routed` 序列化→桥接→反序列化保持（passthrough_ok = true）。
