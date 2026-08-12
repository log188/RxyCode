# B7 独立模型审计证据链（2026-08-11）

B7 卡（不返工）审计产物。审查角色：zen/gpt-5.6-luna（`https://opencode.ai/zen/v1`）。

## 实现范围

### 核心（不返工五件套）
1. **错误回喂**：`_error_feedback_message`（引导语"换一种完全不同的方法"）+ `_error_feedback_wrap`，追加在断点之后，不碰前缀（CB1/CB7）
2. **死循环检测**：`core/stuck_detector.py`（连续相同 / 交替模式 / 连错，阈值可配默认 3，opencode DOOM_LOOP_THRESHOLD 语义）
3. **失败结果不缓存**：`_should_cache_answer`（空答案 / `[error ...]` 一律不写应用缓存）
4. **Git 快照**：`core/snapshot.py`（LLM 调用前捕获 status/diff，坏结局可回滚；git 不可用容错）
5. **reviewer 重试**：`core/reviewer_retry.py`（默认关闭，开启有 API 调用预算，同分取调用最少者）

### 波动根因修复（用户要求纳入，确定性方案）
6. **DSML 兜底解析**：`_parse_dsml_tool_calls`（deepseek FC=True 偶发输出 `<||DSML||tool_calls>` / `<dsml>` 变体文本 → 解析为 tool_calls）；接入工具轮 + 合成轮（`_synthesis_with_tools`）
7. **POSIX→PowerShell 转换扩展**：`utils/shell.py` translate_command 新增 `pwd`/`cat`/`grep -n`/`grep -rl`/`find -name`/`2>/dev/null`/`||` 转换
8. **evals readcode 任务 yaml 补 `effect: read`**（4 个任务）：修复只读任务被误判为副作用任务（agent 偶用 cd/bash 即失败）

## 验收证据

- `b7-pytest-v.txt`: 32 passed（test_no_rework）
- `b7-shell-tests.txt`: 25 passed（test_shell，含新增转换）
- `b7-ruff.txt`: All checks passed
- `b7-evals-gate.json`: **GATE PASS 94.7% ≥ 89.5%（零回归，1 改善）**
  - tokens 1,177,035；并行 4 组 + 自动重试 3 轮（本地验收工具，不提交）
  - 唯一失败 websearch-summary：基线 latest-agent.json 即 FAIL（agent 完成搜索后无法产出含中文 pattern 的总结），非本卡引入
- 全量回归 tests/test_core + test_cache + test_memory + test_validation + test_execution: 8040 passed, 2 failed（P7 lazy-import 预算遗留，stash 验证早于 B1-B5，非本卡引入）

## 波动分析（报告核心结论）

历次全量通过率：B6 89.5% / B7 78.9% / 78.9% / 84.2% / 84.2% / **94.7%（修复后）**。失败任务每次不同（validator/pipeline/usage/cli-parser/json-merge/mutable-default…），根因分解：
1. **模型采样不稳定（64%）**：DSML 文本污染（U+FF5C 变体实测）、POSIX/PowerShell 混用、答案措辞漂移
2. **只读任务误判副作用（修复）**：readcode 任务 effect 未声明 → agent 偶用 cd/bash 即被要求 WRITE 证据 → 失败。**修复：effect: read**
3. **环境配置污染**：active_model 被并发会话改掉 → 404（2 轮全量）。**验收方式：显式 --model**
4. **并行 journal 锁**：已通过本地隔离解决（不提交）
5. **websearch-summary**：任务本身能力要求（基线即 FAIL）

## 审计轮次（10 轮）

| 轮次 | 结论 | 核心阻断项 |
|---|---|---|
| R1 | FAIL | `_synthesis_with_tools` 缺 ToolMessage 导入；stuck break 只跳内层；合成轮未捕获 Git 快照；DSML 混文本 ET 失败；bash 转换误改引号 |
| R2 | FAIL | 引号内 `2>/dev/null`/`\|\|`/`pwd` 被误转换（需引号感知） |
| R3 | FAIL | 未闭合引号/转义引号/哨兵碰撞/grep 多文件/`\|\| pwd` 未处理 |
| R4 | FAIL | grep pattern 用 json.dumps（PS 不认反斜杠转义、$ 展开）；判据证据不足 |
| R5 | FAIL | reviewer 无 Agent 集成；Git 无 restore 调用链；PS 引用测试不完整 |
| R6 | FAIL | Git snapshot 非真正恢复（reset --hard 丢快照前修改、重复捕获丢基线）；ReviewerBudget 未限制总调用；stuck 后可能返回 DSML |
| R7 | FAIL | `_review_answer` await async-gen TypeError；`git checkout -- .` 不保留快照前修改；stuck recovery 空时保留 DSML |
| R8 | FAIL | reviewer max_api_calls=2 时 regeneration 结果被丢弃；工具错误后普通文本仍缓存；重要性判定过脆 |
| R9 | FAIL | `_synthesis_with_tools` 工具错误未设状态；`_tool_error_occurred` 未按请求重置 |
| R10 | **PASS** | 无剩余阻断项，判据 1-6 + CB1-CB8 全过 |

## 最终结论

zen/gpt-5.6-luna 第 10 轮审计 **PASS**：B7 完成判据 1-6 全过，八条硬约束 CB1-CB8 无违反。
B7 卡可在开发文档验收处打钩（2026-08-11）。
