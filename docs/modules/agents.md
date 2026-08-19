# agents.md — 多 Agent 专家团

## 什么时候不该用多 Agent

**默认不要开。** F14 E0（`evals/baselines/f14-e0-matrix.md`）用 solo 基线加三段 SOP 成本模型得到：token ≈ 3.0x、墙钟 ≈ 2.5x、完成率不升。效能比灯全是 🔴。

不该用的时候：

- 单文件 bugfix / 小 refactor / 只读问答（当前评测集的主体）
- 强依赖串行、必须同一份上下文的任务
- 你还没有为这次运行单独准备 token 预算

该考虑打开的时候（E1/E2 再测）：

- 可拆的结构化分工（前后端、多模块、独立审计）
- 机械验证门能挡住假完成，且你接受至少 3x token

`settings.agents.enabled` 保持 **false**。F10 启发式 `min_files_for_team` 已回写为 4。

### 效能比门禁（红绿灯）

| 任务类型 | token倍数 | 时间倍数 | Δ完成率 | 灯 |
|---|---|---|---|---|
| bugfix | 3.0x | 2.5x | −2pp | 🔴 |
| feature | 3.0x | 2.5x | −2pp | 🔴 |
| readcode | 3.0x | 2.5x | −2pp | 🔴 |
| refactor | 3.0x | 2.5x | −2pp | 🔴 |

### 🔴 迭代记录

1. E0：成本模型，不烧团队 LLM。动作 = 默认关 + 阈值提高到 4。
2. E1：未开跑。等 F17 命中率门。
3. E2：未开跑。仅 E1 变黄再优化。

这不是失败，是省下的钱。
