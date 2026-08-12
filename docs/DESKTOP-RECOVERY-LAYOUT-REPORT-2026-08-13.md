# RxyCode Desktop Recovery and Layout Report

执行日期：2026-08-13
基线：本地 `master` 当前工作基线
范围：Phase 4 Desktop 当前实现；不宣称 Phase G 完整 Desktop 已完成。

## 1. 本轮结论

本轮修复了两个会直接影响真实使用的问题：

1. appserver watchdog 以前只根据“最后一次用户可见事件”判断 liveness。模型请求或本机工具静默超过 120 秒时，即使 worker 仍然工作，也可能收到 `job stalled >120.0s` 并被杀掉。
2. GUI 在 recoverable stall 后只重连了 transport，但重放历史状态可能把会话重新标记为 `running`，下一条 prompt 因此被前端 busy guard 丢弃。

本轮还把 Electron 回归覆盖到默认居中布局、按需 inspector、审批、Enter 发送、删除/恢复、浅色 dialog 和超时恢复链。

## 2. 实施内容

### 2.1 后端 liveness

- `appserver/agent_worker.py`
  - 增加 request-local worker heartbeat。
  - heartbeat 仅用于 appserver watchdog，不进入 renderer 时间线，不写 replay store。
  - 支持 `RXYCODE_APPSERVER_WORKER_HEARTBEAT_SECONDS`；默认 10 秒，非正值可在确定性测试中关闭。
- `appserver/server.py`
  - 识别 `event/heartbeat` 并 touch 当前 job 后丢弃，不持久化、不渲染。
  - bootstrap 阶段不提前注册 running watchdog job，避免冷启动阶段被错误归类为运行中卡死；外层 prompt timeout 仍然保留。
- `appserver/stub.py`
  - 增加 `silent:<seconds>` 确定性测试场景。

这保留了真正挂死 worker 的检测能力：测试关闭 worker heartbeat 后，`hang:forever` 仍会被 watchdog 终止。

### 2.2 Desktop reconnect

- `frontend/desktop-app/src/renderer/src/hooks/useConversation.ts`
  - reconnect 接受目标 session，避免用户切换任务时重放错误会话。
  - `sendMessage`、新建、重命名、删除、恢复、清理和设置模型在 client 缺失时共用 reconnect 入口。
  - recoverable stall 后将历史 `running` 状态降为可继续输入的 `queued`，不会把下一条 prompt 当作重复运行。
  - 保留正常运行中的 busy guard，防止用户重复提交真实正在执行的任务。

### 2.3 GUI 回归夹具

- `frontend/desktop-app/scripts/fake-appserver.mjs`
  - 增加 `timeout demo`：返回 production-like `appserver degraded: job stalled >120.0s`，不发送终态事件。
- `frontend/desktop-app/scripts/gui-ux-regression.mts`
  - 新增 recoverable stall → reconnect → 下一轮 Final Answer。
  - 增加删除后活动列表消失、恢复后重新出现。
  - 浅色主题检查 composer 与 settings dialog，避免黑色旧 surface 泄漏。

默认单栏居中、导航抽屉、按需 inspector 和语义化深色 token 已由此前 Desktop UI 改造保留，并在本轮 Electron 截图中复核。

## 3. 验收证据

| 检查 | 结果 |
|---|---|
| Desktop Node tests | 190 passed |
| appserver tests | 86 passed, 1 skipped |
| Desktop typecheck | passed |
| Desktop production build | passed |
| Electron GUI UX | 14/14 passed |
| `git diff --check` | passed |

跳过项是 `RXYCODE_APPSERVER_LIVE=1` 的真实 AgentV2 bootstrap 测试；本轮没有主动消耗真实 Provider token，因此不能把确定性 stub 结果冒充真实模型结果。

最终 Electron 工件：

`frontend/desktop-app/artifacts/gui-ux-1786555048353/`

其中包含 `ux-final.png`、`process-output.json` 和 `cleanup-proof.json`。最终 cleanup proof 确认 CDP websocket、Electron、appserver、临时 worktree、临时 profile、端口和 pending RPC 均已清理。

## 4. 关键场景

### 静默模型请求

配置 watchdog stall=2 秒、server heartbeat=1 秒，执行 `silent:3`。任务在 3 秒无用户可见输出期间保持成功，并返回 `stub:silent-complete`；这证明 watchdog 依赖 worker liveness，而不是依赖 token/tool 输出频率。

### 真正挂死

关闭 worker heartbeat 后执行 `hang:forever`。任务仍返回 `-32004`，状态进入 failed，server heartbeat 标记 degraded；后续 prompt 能重新创建 worker 并成功完成。

### GUI 恢复

`timeout demo` 的中间 RPC 错误只形成折叠的 recovery 行，没有形成最终 error；输入 `after timeout reconnect` 后产生新的 Final Answer。命令/结果/恢复/下一次命令/结果的顺序保持在同一时间线中。

## 5. 未覆盖与限制

- 本轮没有运行真实 Provider 场景，因此没有 input/output/cache-hit token 数值；确定性 fake appserver 的 `not_reported` 仍显示为未知，不转换成 0。
- 本轮未修改用户已有的 `Composer.tsx`、模型目录、Provider 文档和 Provider 测试改动。
- 本轮只处理当前 Phase 4 Desktop 的布局和恢复链，不引入 Phase G 的完整 diff/review 工作区。

## 6. 本轮增量复核（2026-08-13）

针对首轮启动慢、导航抽屉和任务操作反馈，本轮又完成了以下闭环：

- `ChatArea` 接收 `event/progress`，首轮没有可见模型输出时显示“正在启动 Agent”，并保留可验证的 `startup/working` 阶段标识；不会把冷启动误显示成无响应。
- 导航抽屉增加捕获阶段的 `Escape` 关闭；设置页原有的 `Escape` 关闭行为保持不变。
- GUI 回归新增真实 DOM 几何检查：默认时间线和 Composer 中线偏差不得超过 48px，默认不得存在 Inspector；同时保存 `layout-default.png` 与 `layout-inspector-open.png`。
- 删除/恢复改为先更新本地任务列表，再等待 appserver 持久化；连接恢复失败时才回滚。因此慢连接不再让用户误以为点击没有生效。
- fake appserver 增加首轮启动进度夹具，Electron 回归可以稳定验证冷启动提示而不消耗真实 Provider token。

本轮最终 Electron 工件：

`frontend/desktop-app/artifacts/gui-ux-1786556122019/`

其中 `cleanup-proof.json` 显示 websocket、Electron、appserver、临时 profile/worktree、调试端口、pending RPC 和 lease 均已清理。

本轮最终验收：

| 检查 | 结果 |
|---|---|
| Desktop Node tests | 190 passed |
| Desktop typecheck/build | passed |
| Electron GUI UX | 14/14 passed |
| 默认布局几何居中 | passed |
| 首轮启动提示 | passed |
| 导航抽屉 Escape | passed |
| 删除/恢复即时反馈 | passed |
| Inspector 默认隐藏、按需展开 | passed |
| `git diff --check` | passed |

appserver 的 86 passed、1 skipped 结论保持不变；跳过项仍是需要显式设置 `RXYCODE_APPSERVER_LIVE=1` 的真实 AgentV2 bootstrap，不在本轮 fake GUI 测试中冒充真实模型结果。
