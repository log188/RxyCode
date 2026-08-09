# B3 独立模型审计证据链（2026-08-09）

B3 卡（断点预算缓存策略）审计产物。审查角色：zen/gpt-5.6-luna（`https://opencode.ai/zen/v1`）。

## 审计轮次

| 轮次 | 文件 | 结论 | 阻断项 |
|---|---|---|---|
| R1 | `b3-luna-audit-R1.txt` | FAIL | 统一分配器未调用 / TTL 未注入 / DeepSeek 未接入 / 末条 user 块级 / tool_result 合并 |
| R2 | `b3-luna-audit-R2.txt` | FAIL | tools 未参与分配 / 未按 caps 限制断点类型 / DeepSeek 非代码强制 / tool_pair 未接入 |
| R3 | `b3-luna-audit-R3.txt` | FAIL | TTL 未生效 / tools 断点未实际注入 / ainvoke 未传 tools |
| R4 | `b3-luna-audit-R4.txt` | FAIL | CB3 未强制（OpenAI 误配仍注入）/ tool_pair 不严格 |
| R5 | `b3-luna-audit-R5.txt` | FAIL | _raw_stream tools 绕过 CB3 / 未消费 tool_call 未检查 |
| R6 | `b3-luna-audit-R6-PASS.txt` | **PASS** | 无阻断项，判据 1-6 + CB1-CB8 全过 |

## 验收证据

- `b3-pytest-v.txt`: `pytest -v tests/test_cache/test_breakpoint_budget.py`（33 passed）
- `b3-ruff.txt`: `ruff check core/cache_policy.py core/agent_v2.py core/providers config tests/test_cache`（All checks passed）
- `b3-evals-gate.txt`: evals GATE PASS 94.7% ≥ 89.5%（18/19，零回归）
- 命中率实测: 91.51%（prompt 28953/hit 26496）> B1 基线 91.22%

## 实现要点（6 轮修复收敛）

- `core/cache_policy.py`：allocate_breakpoints（tools→system→messages，≤4 强制预算）、resolve_ttl_seconds（5m/1h/数字秒）、apply_breakpoint_budget（统一入口 + caps 类型限制 + tool_pair_integrity 校验）、mark_last_user_breakpoint（不改原对象）、tool_pair_integrity（紧跟 assistant/连续 result/缺 id 拒绝/未消费拒绝）、verify_deepseek_prefix
- `core/agent_v2.py`：_apply_cache_control 统一入口 + Anthropic 白名单（CB3）；_raw_stream tools 断点注入与 _apply_cache_control 判定一致；_record_usage DeepSeek 命中验证；ainvoke/astream 传 tools
- `core/providers/anthropic.py`：llm_kwargs 注入 extra_body.cache_ttl
- 测试 33 个（分配序/TTL/provider 分派/末条 user/tool pair/DeepSeek 验证/负向误配）

## 最终结论

zen/gpt-5.6-luna 第 6 轮审计 **PASS**：B3 完成判据 1-6 全过，八条硬约束 CB1-CB8 全满足。
B3 卡可在开发文档验收处打钩。
