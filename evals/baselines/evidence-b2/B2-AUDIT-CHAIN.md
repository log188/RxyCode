# B2 独立模型审计证据链（2026-08-09）

B2 卡（稳定前缀纪律）审计产物。审查角色：zen/gpt-5.6-luna（`https://opencode.ai/zen/v1`，同一 key）。

## 审计轮次

| 轮次 | 文件 | 结论 | 阻断项 |
|---|---|---|---|
| R1 | `b2-luna-audit-R1.txt` | FAIL | 真实请求测试/断点位置/prompt_cache_key 分派 |
| R2 | `b2-luna-audit-R2.txt` | FAIL | 字节序列化含 tools / subset 分支排序 |
| R3 | `b2-luna-audit-R3.txt` | FAIL | 完整 body 字节比较 / Anthropic payload / research 行为 |
| R4 | `b2-luna-audit-R4.txt` | FAIL | Anthropic 真实 payload / CB3 provider 隔离 / research 行为链 |
| R5 | `b2-luna-audit-R5.txt` | FAIL | DeepSeek/Anthropic 测试需显式 provider |
| R6 | `b2-luna-audit-R6-PASS.txt` | **PASS** | 无阻断项，判据 1-6 + CB1-CB8 全过 |

## 验收证据

- `b2-pytest-v.txt`: `pytest -v tests/test_cache/test_stable_prefix.py`（25 passed）
- `b2-ruff.txt`: `ruff check ...`（All checks passed）
- `b2-evals-gate.txt`: evals GATE PASS 94.7% ≥ 89.5%（18/19，零回归）
- 命中率实测: 91.44% ≥ B1 91.22%（两轮真实会话，go 模式 deepseek-v4-flash）
- 真实 payload 捕获: OpenAI 注入 prompt_cache_key；DeepSeek(provider=deepseek)/Anthropic(provider=anthropic)/非 openai override 均不注入

## 最终结论

zen/gpt-5.6-luna 第 6 轮审计 **PASS**：B2 完成判据 1-6 全过，八条硬约束 CB1-CB8 全满足。
B2 卡可在开发文档验收处打钩。
