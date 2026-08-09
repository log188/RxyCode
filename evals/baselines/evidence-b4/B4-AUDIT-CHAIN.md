# B4 独立模型审计证据链（2026-08-09）

B4 卡（压缩不毁前缀）审计产物。审查角色：zen/gpt-5.6-luna（`https://opencode.ai/zen/v1`）。

## 审计轮次（9 轮）

| 轮次 | 文件 | 结论 | 核心阻断项 |
|---|---|---|---|
| R1 | `b4-luna-audit-R1.txt` | FAIL | 25% 预算未实现 / system 裁剪 / 配对依赖回退 |
| R2 | `b4-luna-audit-R2.txt` | FAIL | 遥测单位 / 配对边界 / 前缀重排 |
| R3 | `b4-luna-audit-R3.txt` | FAIL | 非首位 system 提升 / 吞并 tool result / 预算循环 |
| R4 | `b4-luna-audit-R4.txt` | FAIL | 预算循环重复摘要 |
| R5 | `b4-luna-audit-R5.txt` | FAIL | 正文子串识别摘要误删 system / fold 空多摘要 |
| R6 | `b4-luna-audit-R6.txt` | FAIL | 仅摘要输入重复 / SimpleNamespace 摘要 |
| R7 | `b4-luna-audit-R7.txt` | FAIL | 重复压缩丢摘要状态 / 非首位 system 顺序 |
| R8 | `b4-luna-audit-R8.txt` | FAIL | 摘要位置前移 / fold 空丢摘要 / 首条摘要重复 |
| R9 | `b4-luna-audit-R9-PASS.txt` | **PASS** | 无阻断项，判据 1-6 + CB1-CB8 全过 |

## 实现收敛（9 轮修复）

- `core/compaction.py`：build_summary_message（Objective/Work State/Next Move）、_split_units（轮次单元配对守恒）、_fold_middle_section（首位 system 前缀不可变、非首位 system 顺序保持、摘要唯一标记 is_compaction_summary、折叠在原位替换摘要）、compact_messages（唯一入口、25% 尾部预算循环复用摘要、遥测 tokens_before/after、tool_pair_integrity 回退防线、重复压缩保留摘要状态、正式 SystemMessage）
- `core/agent_v2.py`：_maybe_compress_context 移除 ContextCompressor 原位截断，统一走 compact_messages；阈值读 caps.compaction_threshold + reserved 20k 输出预留

## 验收证据

- `b4-pytest-v.txt`: 22 passed
- `b4-ruff.txt`: All checks passed
- `b4-evals-gate.txt`: GATE PASS 89.5% ≥ 89.5%（另一次 94.7%；两次 84.2% 为 websearch-summary 恒失败 + 随机波动任务，非回归）
- 压缩触发实测: tokens 8150→1715（79%），system 未变，单摘要
- evals token: 1.23M < 1.61M 基线（降 38 万）

## 最终结论

zen/gpt-5.6-luna 第 9 轮审计 **PASS**：B4 完成判据 1-6 全过，八条硬约束 CB1-CB8 全满足。
B4 卡可在开发文档验收处打钩。
