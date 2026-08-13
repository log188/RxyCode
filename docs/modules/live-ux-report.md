# RxyCode 真人窗口实测与修复报告

日期：2026-08-13  
范围：`rxycode` OpenTUI + `rxycode gui` Desktop  
对照基线：`docs/DESKTOP-CD-INTEGRATION-STRESS-REPORT-2026-08-13.md`（确定性套件缓存命中率 41.37%，真实 provider 未上报）

## 1. 结论（先看这个）

**缓存命中率没有显著提升。** 本机真实缓存当前为：

| 层 | 条目 | 命中次数 | 有效条目 |
|---|---:|---:|---:|
| precise | 2 | **0** | 0（均已过期） |
| semantic | 1 | **0** | 0（已过期） |

TUI 空闲状态栏当时是 `缓存: 0B / 0.0%`。上一份 CD 报告里的 41.37% 来自**确定性假协议回放**，不是真实模型缓存，不能拿来宣称本次变快。

本次真正变快、且截图已验证的是：

- TUI 顶栏记住模型（`Build · deepseek-v4-flash`），不再 `unknown`
- OpenTUI 从启动到 `Agent initialized` 约 **9 秒**（`rxycode.log` 17:07:29 → 17:07:38）
- GUI 冷启动不再被 57 个历史任务的 `child_sessions/events` 10s 超时锁死；Composer 可输入，状态为 `Queued`，没有红条

仍未清掉的问题：

- **每个新 session 仍会冷启动独立 worker**。CDP 实测发「成都两日游」后停在 `Starting Agent worker…` 超过 120s，没有等到终态回答
- Windows Terminal 多标签会抢走 TUI 焦点，自动化很难拍到完整回复帧
- 空 Electron profile 首屏会短暂显示 `Model not connected` / `No configured models`（用户真实配置下的 `rxycode gui` 已显示 deepseek）

## 2. 怎么测的

1. `cmd` / Windows Terminal 执行 `rxycode`，PrintWindow 截图空闲态
2. 向 OpenTUI 的 bun 控制台写入「成都两日美食游」类提示
3. `rxycode gui` 真实用户配置启动，截图空闲态与压力点击
4. 另用临时 profile + CDP 发同样的旅游规划提示，截运行中画面
5. 读取 `~/.rxycode` 的 precise/semantic 缓存统计和 `rxycode.log`

截图目录：`artifacts/live-round2/`（不入库）

## 3. 已修复并回归的 bug

| ID | 现象 | 根因 | 修复 |
|---|---|---|---|
| GUI-P0 | 红条 `child session recovery failed: RPC timeout: child_sessions/events`，Stop 锁死 | 启动时对全部历史任务 `Promise.all` 打 `child_sessions/events`，appserver 为此 **bootstrap AgentV2（30s）**，前端 10s 超时还当成断连 | 未就绪 worker **立刻返回空 child events**；超时视为非致命 |
| GUI-P0 | `Running` + `Preparing Agent worker…` 但时间线是空的 | `tasks.json` 里 8 个任务仍是 `running`，回放 progress 当成活任务 | 冷启动把 `running` 降成 `queued`；`releaseStaleRun` 清 progress |
| TUI | Header `unknown`、切模型杀 worker | 已在前一次提交 `1430d0e` | 本次复测空闲态已显示 `deepseek-v4-flash` |

测试：

- `pytest tests/test_appserver/test_server_subagents.py` 等：**16 passed**
- desktop `conversationStore` / `sessionRecovery` / `taskPresentation`：**78 passed**

## 4. 缓存为什么没升

真实两级缓存（`cache/precise_cache.py`、`cache/semantic_cache.py`）只在 **完全相同或极近的请求** 且条目未过期时命中。本次：

- 条目全部过期，命中次数为 0
- 旅游规划两次措辞不同，不会走 precise hit
- 首轮还在 `Starting Agent worker`，没有完整 `event/token_usage` 可汇总

因此：**不能报告缓存命中率显著提升。** 体感变快主要来自少做无用 RPC、不锁 Composer、MCP 后台化，而不是 cache hit。

## 5. 建议下一步（未做）

1. 新任务尽量复用已预热的 worker，而不是每个 session 再构造一遍 AgentV2
2. 延长/刷新 cache TTL，或对纯问候/短规划做稳定 cache key
3. GUI 在 appserver `models/list` 就绪前不要画成「No configured models」
