# B8 独立模型审计证据链（2026-08-11）

B8 卡（并行与延迟）审计产物。审查角色：zen/gpt-5.6-luna（`https://opencode.ai/zen/v1`）。

## 实现范围

1. **只读工具并发**：`_execute_tools_parallel`（core/agent_v2.py）——只读组
   `asyncio.gather` + `Semaphore(max_parallel)` 并发；写组串行；结果按
   tool_calls 原序返回（tool_pair_integrity 安全，B2 排序纪律）。
   配置复用 `execution.parallel_enabled`（默认 False，CB8）/`max_parallel`（默认 3）。
   工具循环接入：`_fast_reply_with_tools` 先并行执行拿结果，再按原序处理
   B7 错误回喂/stuck 逻辑。
2. **后台 fork 摘要**：`_fork_background_summary`——`asyncio.create_task` +
   `copy.deepcopy` 快照（不原位改写已发送消息，G2 防线），调用方可不 await。
3. **流式与断点一致性**：`_raw_stream` 与 ainvoke/astream 共用
   `_apply_cache_control`（B3 策略唯一入口），测试锁定（含 P2 修复先例）。
4. **TTFT 记录**：TokenStats 新增 `ttft_ms`/`record_ttft`/`reset_ttft`；
   `_raw_stream` 首个内容 chunk 打点；conftest 隔离。
5. **B7 遗留修复**：grep/find 转换支持 `;` 链（`cd X ; grep ...`）——
   从 re.match 改 re.sub 任意位置匹配。

## 验收证据

- `b8-pytest-v.txt`: 16 passed（test_parallel_latency）
- `b8-shell-tests.txt`: 34 passed（含 grep 链新增）
- `b8-ruff.txt`: All checks passed
- `b8-ttft.json`: **TTFT 冷写 11844.9ms / 命中 5218.6ms / 加速 2.27x**
  （4 次交替采样：cold1 15627/hot1 6124/cold2 8063/hot2 4313；同前缀同模型同后端）
- evals: GATE PASS 94.7% ≥ 89.5%（零回归，1 改善 refactor-extract-function）
- 全量回归 test_core+test_cache+test_memory+test_execution+test_tools+test_validation:
  9020 passed, 2 failed（P7 lazy-import 遗留，stash 验证早于 B1-B5）
- 验收方式：并行 4 组 + 失败重试 3 轮（本地工具 C:\Windows\TEMP\opencode\b8_par.py，
  **不提交**主代码；Phase C 将做内核异步化）

## 审计轮次（待 luna 复审填充）

| 轮次 | 结论 | 阻断项 |
|---|---|---|
| R1 | ... | ... |

## 最终结论（待 luna PASS 后填写）

zen/gpt-5.6-luna 审计 **PASS** 后，B8 卡可在开发文档验收处打钩。
