# B6 独立模型审计证据链（2026-08-10）

B6 卡（token 治理）审计产物。审查角色：zen/gpt-5.6-luna（`https://opencode.ai/zen/v1`）。

## 审计轮次（6 轮）

| 轮次 | 文件 | 结论 | 核心阻断项 |
|---|---|---|---|
| R1 | `b6-luna-audit-R1.txt` | FAIL | JSON 截断不保证 ≤limit（顶层长字符串/数字/key/容器）；极小 limit 普通文本超限；去重用截断后内容算指纹；CB8 默认值质疑 |
| R2 | `b6-luna-audit-R2.txt` | FAIL | 顶层 JSON 字符串在 limit=1/2 下超限（引号开销未兜底）；CB8 已裁定 PASS（默认 2000 为文档设计要求） |
| R3 | `b6-luna-audit-R3.txt` | FAIL | 顶层空字符串 limit=1 下 `""` 长 2 超限 |
| R4 | `b6-luna-audit-R4.txt` | FAIL | `_minimize_values` 无进展循环（全 null 仍 True → 500 次空转）；超长 key 未删除过早退化标量；bool 被当 int 配置 |
| R5 | `b6-luna-audit-R5.txt` | FAIL | 长 key 阈值 >32 应为 >=32 且需递归；去重只存最后一个指纹（A→B→A 会重复） |
| R6 | `b6-luna-audit-R6.txt` | **PASS** | 无新增阻断项，判据 1-6 + CB1-CB8 全过 |

## 实现收敛（6 轮修复）

- `config/settings.py`：`cache.tool_output_max_chars` 默认 2000（文档指定，CB8 PASS 依据）
- `core/agent_v2.py`：
  - `_tool_output_max_chars()`：读配置，bool/非 int → None（不截断）；≤0 → None
  - `_truncate_tool_text()`：B6 字符维度（默认 2000）+ A20 token 维度叠加，各维度可独立关闭
  - `_truncate_tool_text_chars()` / `_truncate_plain_chars()`：字符截断，极小 limit 纯头部兜底（硬上限）
  - `_truncate_json_chars()`：JSON 结构保持截断，保证 json.loads 合法且 ≤limit；策略链 = 最长字符串值截半 → 删超长 key（≥32，递归）→ 容器尾部裁剪 → 值置 null（无进展即退）→ 最小合法字面量
  - `_tool_output_fingerprint()`：JSON sort_keys 规范化指纹（key 顺序无关）；非 JSON 原文
  - `_dedupe_tool_output()`：**原始输出**（截断前）指纹；指纹集合按工具累计（A→B→A 判重）；重复 → 占位符
  - 落地接入：`_fast_reply_with_tools` 工具循环 + research webfetch 分支（先 dedupe 后 truncate）
- `tests/test_cache/test_token_governance.py`：37 个测试（B6 验收命令指定文件）
- `tests/test_providers/test_token_governance.py`：A20 既有测试适配（`test_truncate_tool_text_none_no_change` 显式关闭 B6 字符维度以保持 token 维度语义）

## 验收证据

- `b6-pytest-v.txt`: 37 passed
- `b6-related-tests.txt`: 298 passed, 3 skipped（test_providers + test_cache）
- `b6-ruff.txt`: All checks passed
- `b6-evals-run.log`: GATE PASS 89.5% ≥ 89.5%（持平，无净回归）
- token 对比（完成判据 6）：1,614,391 → 1,293,031（-321,360 / -19.9%）
- 全量回归 tests/test_core + test_cache + test_memory: 7693 passed, 2 failed（P7 lazy-import 预算遗留，stash B6 改动后同样失败，早于 B1-B5，非本卡引入）
- 波动说明：readcode-validator-threshold 全量一次 FAIL 但单任务重跑 PASS（LLM 偶发波动，失败时 agent 仍读到 0.7 阈值原文，非截断导致）；websearch-summary 基线即 FAIL

## 最终结论

zen/gpt-5.6-luna 第 6 轮审计 **PASS**：B6 完成判据 1-6 全过，八条硬约束 CB1-CB8 无违反。
B6 卡可在开发文档验收处打钩。
