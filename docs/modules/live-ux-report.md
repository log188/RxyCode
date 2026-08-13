# RxyCode 真人窗口实测与修复报告

日期：2026-08-13  
范围：`rxycode` OpenTUI + `rxycode gui` Desktop  
对照基线：确定性套件假协议命中率 41.37%（不能当真实缓存）

## 1. 结论（先看这个）

**首轮卡死已经按根因修掉。** 真实 `AgentV2.run`（「不要调用工具」的旅游规划）：

| 步骤 | 修复前 | 修复后（本机实测） |
|---|---:|---:|
| Agent 构造 | ~9s | **7.2s** |
| 成都/杭州规划首轮出完整答案 | **>120s 无终态**（GUI CDP timeout） | **7.6s / 10.5s** |
| 同 session 稍改措辞的第二轮 | 从未跑完 | **6–9s**（有会话记忆时语义缓存按设计不命中） |

**磁盘上的历史命中次数没有从 0 变成很高**：旧条目仍过期。但之前「永远 0 命中」有代码级根因，已经修掉：

- 工具快路径把 `cache_read_allowed` 整段旁路
- 中文语义实体按整句切片，近重复 overlap=0
- 答案里出现「无法复制」会被 `"无法"` 误杀，语义层根本不落盘

同 session 第二轮若记忆非空，语义层仍会 bypass（这是原设计，避免带上下文的答案串台）。**新 session、空记忆、近重复规划**现在可以语义命中（单元测试覆盖成都两句）。

上一份 CD 报告的 41.37% 仍是假协议，不能拿来对比。

## 2. 根因（不再猜）

GUI CDP `timeout waiting for completion`（125s）不是「worker 一定要 2 分钟」，而是首轮被几件事叠死：

1. **`run()` 在用户请求旁边后台预热**（全量 tools + `max_tokens=1`），和正式 LLM 抢同一条上游，历史上就是 90s 预热超时 + 正式请求 ≈ 117s
2. **「不要调用工具」仍走绑定 30+ 工具的快路径**，还把应用缓存 `bypass=True`
3. **做个小游戏**被打进完整 LangGraph，而不是带 write 的工具快路径
4. 语义缓存中文实体是整段汉字，近重复 overlap=0；`"无法"` 误伤正常中文答案

MCP 配置是 `{}`，**不是**这次 120s 的原因。

## 3. 本轮修复

| ID | 修复 |
|---|---|
| LAT-1 | `run()` 不再 `_schedule_prewarm`（用户请求自己写前缀） |
| LAT-2 | 进行中的 MCP 刷新不再 `await`（线程 `is_alive` 则跳过） |
| ROUTE-1 | `declines_tools`（不要调用工具 / no tools）→ `_fast_reply`，可缓存、不绑工具 |
| ROUTE-2 | `has_creation_product_intent`（做个小游戏）→ `_fast_reply_with_tools`，不再掉进 LangGraph |
| CACHE-1 | 工具快路径：`cache_read_allowed` 时读缓存；本轮**没调用工具**且 `cache_write_allowed` 时写入 |
| CACHE-2 | 中文 2-gram 实体 + 相似度阈值 0.90 |
| CACHE-3 | 语义 `put` 不再把单独的「无法」当失败答案 |

回归：`tests/test_core/test_first_turn_latency.py` 以及 cache / research_fast_path 相关用例。

## 4. 还没消灭的（说清楚）

- 每个 **新 GUI session 仍会 spawn 独立 worker**（约 7s 构造）。这是进程隔离，不是 120s 卡死。
- 同一会话里第二句近重复**不会**走语义缓存（有 memory 就 bypass）。
- Windows Terminal 多标签仍会抢走 TUI 焦点。
- 空 Electron profile 仍可能闪一下 `No configured models`。
