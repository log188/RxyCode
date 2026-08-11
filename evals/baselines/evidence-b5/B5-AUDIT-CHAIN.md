# B5 独立模型审计证据链（2026-08-09）

B5 卡（会话复用与 prewarm）审计产物。审查角色：zen/gpt-5.6-luna（`https://opencode.ai/zen/v1`）。

## 审计轮次（9 轮）

| 轮次 | 文件 | 结论 | 核心阻断项 |
|---|---|---|---|
| R1 | `b5-luna-audit-R1.txt` | FAIL | 恢复测试不真实 / prompt_cache_key 无真实链路 / 预热仅签名 / 保活仅开关 |
| R2 | `b5-luna-audit-R2.txt` | FAIL | append 已有前缀不清空 / 预热未接入 / 保活未调度 / 命中率链路 |
| R3 | `b5-luna-audit-R3.txt` | FAIL | append 重复追加 / prewarm 未接入 run / keep-alive 仅布尔 |
| R4 | `b5-luna-audit-R4.txt` | FAIL | 重叠检测不通用 / keep-alive 未发送 / prewarm 未真实重建 / MCP 签名不全 |
| R5 | `b5-luna-audit-R5.txt` | FAIL | append 丢 system/tool / keep-alive 未传 max_tokens / prewarm 未真实 |
| R6 | `b5-luna-audit-R6.txt` | FAIL | 重叠仍重复 / prewarm 提前提交 warmed |
| R7 | `b5-luna-audit-R7.txt` | FAIL | prewarm 未确认不可重试 / keep-alive 参数未入请求 |
| R8 | `b5-luna-audit-R8.txt` | FAIL | tool_calls 元数据丢失 / prewarm 首 chunk 确认 / 预热未用真实前缀 |
| R9 | `b5-luna-audit-R9-PASS.txt` | **PASS** | 无阻断项，判据 1-6 + CB1-CB8 全过 |

## 实现收敛（9 轮修复）

- `memory/short_term.py`：append_from_dicts（不清空逐条追加 + system/tool/assistant tool_calls 全类型保留）
- `memory/manager.py`：load_session(append_only=True) 通用最长重叠去重（前缀不匹配不追加）
- `core/cache_policy.py`：build_prewarm_signature（model/cwd/MCP 完整 JSON）、PrewarmState（warm/validate/rebuild）、keep_alive_enabled/budget/should_fire/build_keep_alive_request（max_tokens=1）
- `core/agent_v2.py`：_ensure_session_loaded append-only 恢复、_maybe_rebuild_prewarm（未确认持续重试）、_confirm_prewarm（成功后提交）、_session_prewarm_messages（真实 system 前缀）、_maybe_keep_alive（预算 + 真实发送）、run 入口集成（prewarm 重建 + keep-alive 发送，完整消费流）

## 验收证据

- `b5-pytest-v.txt`: 36 passed
- `b5-ruff.txt`: All checks passed
- `b5-evals-gate.txt`: GATE PASS 94.7% ≥ 89.5%（18/19，零回归）
- 跨 turn 命中实测: prompt 89281 / hit 74880 / 83.87%（同 session 两轮）
- 恢复验证: append-only + 重叠去重 + tool_calls 保留

## 最终结论

zen/gpt-5.6-luna 第 9 轮审计 **PASS**：B5 完成判据 1-6 全过，八条硬约束 CB1-CB8 无违反。
B5 卡可在开发文档验收处打钩。
