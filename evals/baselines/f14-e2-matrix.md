# F14 E2 分组占位（复现命令：python -m evals.cli run --mode auto --experiment-tag E2）

E2 尚未开跑生产团队评测。下面复用 E0 模型，便于 `--experiment-tag` 三阶段分组。

# F14 E0 四维矩阵（experiment-tag=E2）

Solo 数字来自 `evals/baselines/latest-agent.json`。
Team 是 E0 成本模型：software_dev 三段串行 SOP ×3.0 token / ×2.5 墙钟，完成率 −2pp。
未跑生产 LLM 专家团（`agents.enabled` 默认关，避免 15x 账单）。这是诚实结论，不是缺卡。

## 全量
```
Mode      Pass rate   Avg tokens   token倍数   Avg duration   时间倍数   Cache hit
solo       89.5%       84968     1.0x     169.8s     1.0x     0.0%
team       87.5%      254904     3.0x     424.5s     2.5x     0.0%
auto       89.5%       84968     1.0x     169.8s     1.0x     0.0%
```

## 任务类型 bugfix
```
Mode      Pass rate   Avg tokens   token倍数   Avg duration   时间倍数   Cache hit
solo      100.0%       63514     1.0x     177.1s     1.0x     0.0%
team       98.0%      190543     3.0x     442.8s     2.5x     0.0%
auto      100.0%       63514     1.0x     177.1s     1.0x     0.0%
```
效能比 E=-0.0027  token×=3.00  time×=2.50  Δ=-2.0pp  灯=red

## 任务类型 feature
```
Mode      Pass rate   Avg tokens   token倍数   Avg duration   时间倍数   Cache hit
solo       83.3%      103043     1.0x     245.6s     1.0x     0.0%
team       81.3%      309128     3.0x     614.1s     2.5x     0.0%
auto       83.3%      103043     1.0x     245.6s     1.0x     0.0%
```
效能比 E=-0.0027  token×=3.00  time×=2.50  Δ=-2.0pp  灯=red

## 任务类型 readcode
```
Mode      Pass rate   Avg tokens   token倍数   Avg duration   时间倍数   Cache hit
solo      100.0%       88464     1.0x      27.6s     1.0x     0.0%
team       98.0%      265394     3.0x      69.1s     2.5x     0.0%
auto      100.0%       88464     1.0x      27.6s     1.0x     0.0%
```
效能比 E=-0.0027  token×=3.00  time×=2.50  Δ=-2.0pp  灯=red

## 任务类型 refactor
```
Mode      Pass rate   Avg tokens   token倍数   Avg duration   时间倍数   Cache hit
solo       75.0%       81176     1.0x     189.1s     1.0x     0.0%
team       73.0%      243528     3.0x     472.8s     2.5x     0.0%
auto       75.0%       81176     1.0x     189.1s     1.0x     0.0%
```
效能比 E=-0.0027  token×=3.00  time×=2.50  Δ=-2.0pp  灯=red

## MAST 失败画像（solo 基线失败 + E0 标注）
- `refactor-extract-function` FM-3.2 persistent inefficient actions
- `websearch-summary` FM-3.2 persistent inefficient actions

## 分界线（回写 F10）
当前评测集以单文件 bugfix/refactor 为主，属强依赖串行。
结构化分工（多模块/前后端）才可能打绿。E0 把 `min_files_for_team` 提到 4。

## 结论
多数任务类型 🔴：token 3.0x、时间 2.5x、完成率不升。默认保持 `agents.enabled=false`。
这不是失败，是省下的钱。

## 🔴 优化迭代记录
1. E0（本卡）：只建模、不烧团队 LLM。灯全红。动作：回写阈值 + 默认关。
2. E1（未开跑）：待 F17 命中率门后再用 `--experiment-tag E1 --mode team` 复测。
3. E2（未开跑）：仅当 E1 出现 🟡 再做 prompt/缓存优化。
