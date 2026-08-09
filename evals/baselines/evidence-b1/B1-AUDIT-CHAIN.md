# B1 独立模型审计证据链（2026-08-09）

本目录文件为 B1 卡判据 6 的原始、可追溯审查产物。位于 `evals/baselines/evidence-b1/`
（docs/plans/ 自 2026-08-06 起不在版本控制内，故证据归档到可入库位置）。

文件 SHA-256（`Get-FileHash -Algorithm SHA256`）：

| 文件 | 内容 | SHA-256 前缀 |
|---|---|---|
| `b1-kimi-precheck-PASS.md` | zen/kimi-k2.7-code 独立预审复审全文（PASS，10/10 项） | A7A0DE9CCC595D67 |
| `b1-luna-audit-R2.txt` | zen/gpt-5.6-luna 第 2 轮审计（FAIL：判据 6 需真实预审） | A755C9BB209D68D0 |
| `b1-luna-audit-R3.txt` | zen/gpt-5.6-luna 第 3 轮审计（FAIL：需真实独立模型产出+机械证据） | 3A1546A3E149A039 |
| `b1-luna-audit-R4.txt` | zen/gpt-5.6-luna 第 4 轮审计（FAIL：需原始日志归档+diff 机械断言） | 2EA776B4912063F6 |
| `b1-audit-prompt4.txt` | 第 4 轮审计输入（diff+测试+基线+收口结论+预审输出） | B069DD0F439593B5 |
| `b1-pytest-v.txt` | `pytest -v` 原始输出（16 passed） | 9C5EA37B3837F041 |
| `b1-ruff.txt` | `ruff check core utils api_server.py tests/test_cache` 原始输出（All checks passed） | E0AF5E08A7EF46DA |
| `b1-evals-gate.txt` | evals GATE PASS 原始摘要（18/19=94.7% ≥ 89.5%） | FBE6FE48B4ADCC53 |

## 审查执行事实

- 独立预审角色：`zen/kimi-k2.7-code`（zen 模式，经 `~/.RxyCode/config.yaml` + credential store 鉴权，DPAPI）
- 主审计角色：`zen/gpt-5.6-luna`（zen 模式，`https://opencode.ai/zen/v1`，同一 key）
- 时间：2026-08-09；执行脚本位于 `C:\Windows\TEMP\opencode\`（临时，不入库）
- 输入材料：diff（`git diff utils/streaming.py`）、测试全文、基线全文、B1 卡收口结论段

## Composer 收口映射

| 审计意见（轮次） | Composer 处理 | 落地 |
|---|---|---|
| R2 判据 6 无真实预审 | 启用 zen/kimi-k2.7-code 独立预审 | `b1-kimi-precheck-PASS.md` |
| R3 判据 5 无机械证据 | `git ls-files` + 提交后 `git diff --name-only` 机械断言 | 见 B1 卡 + 本目录 |
| R3 fixture 命名不诚实 | 改为 "DeepSeek usage-shaped integration fixture" | `tests/test_cache/test_hit_rate_metrics.py` |
| R3 判据 6 无原始产出 | 归档全部原始审查输出 | 本目录 |
| R4 需原始日志 | 归档 pytest/ruff/evals 原始输出 | 本目录 |
| R4 需 diff 机械断言 | 提交后 `git diff --name-only` 验证白名单子集 | 见 B1 卡验收记录 |

## 最终结论

- zen/kimi-k2.7-code 预审：**PASS（可发布）**，10/10 审查点通过
- zen/gpt-5.6-luna 审计第 4 轮（R4）：FAIL，阻断项 = 本文件所补证据 + 机械 diff 断言
- 补齐后按流程最终复审（R5）
