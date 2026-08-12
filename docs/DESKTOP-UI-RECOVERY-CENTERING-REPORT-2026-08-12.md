# RxyCode Desktop UI、启动性能与自动恢复回归报告

执行日期：2026-08-12  
基线：本地 `master` 工作树（保留已有用户改动）  
范围：Phase 4 Desktop 当前实现；不宣称 Phase G 完整能力，也不把尚未合并的 Phase B 真实模型压力轮计入通过数。

## 1. 本轮修复结论

- 默认窗口改为单主列居中布局，不再为未打开的右侧检查器预留空列。
- 左侧任务列表改为由顶部导航按钮打开的抽屉；检查器只有点击工具、恢复或子代理活动后才出现。
- 当前打开任务禁止移入最近删除，给出“您正在打开该窗口删不掉”；其他任务删除、恢复均有即时 toast。
- 新建任务先显示进行中反馈；生产 appserver 在 `session/new` 返回后后台预热首个 worker。
- 历史 session 事件恢复由串行改为并发，降低首屏和会话切换等待。
- `job stalled` 或 worker transport degraded 后，允许重建对应 worker；Renderer 连接失败时自动重连，必要时 stop/start appserver 后重新 initialize。
- CDP harness 使用独立 Vite 临时端口，避免前一轮开发服务器占用 `5173` 污染后续 GUI 测试。

## 2. 真实 GUI 回归矩阵

命令：

```powershell
npm run test:gui:ux
```

最近两轮连续结果均为 10/10：

| 编号 | 场景 | 结果 |
|---|---|---|
| UX-01 | Composer、发送箭头、任务权限控件存在 | PASS |
| UX-02 | Enter 发送真实任务 | PASS |
| UX-03 | 批准后弹窗关闭、RPC 收敛 | PASS |
| UX-04 | Light 主题使用淡色语义 surface | PASS |
| UX-05 | Full access 需要二次确认 | PASS |
| UX-06 | Settings 支持 Escape 关闭 | PASS |
| UX-07 | 当前打开任务不能删除且即时提示 | PASS |
| UX-08 | 默认布局不创建 inspector 空列 | PASS |
| UX-09 | 非当前任务删除、最近删除恢复和 toast | PASS |
| UX-10 | 工具活动按需打开/关闭 inspector | PASS |

最近一轮工件：

`frontend/desktop-app/artifacts/gui-ux-1786544812618/cleanup-proof.json`

独立连续通过工件：`gui-ux-1786544787487`、`gui-ux-1786544812618`；两轮均为 10/10。

清理证明：WebSocket、Electron、appserver、端口、临时 profile、临时 worktree、pending RPC、lease 均已清理，`passed: true`。

## 3. 后端与连接回归

- `pytest -q tests/test_appserver/test_stdio_integration.py -k "watchdog_stall_kills_job or stalled_session_does_not_block_another_session or prompt_timeout"`：3 passed。
- stall 后同一 session 可以重建 worker 并成功执行下一次 prompt。
- 一个 session stalled 时，另一个 session 仍可新建并成功执行 prompt。
- `node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --test src/platform/index.test.mts scripts/cdp-harness.test.mts src/renderer/src/lib/taskActions.test.mts`：21/21 passed。
- `npm test`：188/188 passed。
- appserver 集成全量：12 passed，1 个 live-only 用例按环境变量要求跳过。
- `npm run typecheck`：通过。
- `npm run build`：通过。
- `git diff --check`：无空白错误；仅有 Windows 换行提示。

## 4. 重要限制

- 本报告没有把真实 Provider 的 30 场景模型压力轮标为通过；该轮应在 Phase B 合并并确认真实子代理链后执行。
- 本轮自动重连只对连接/transport/stall 类错误进行；未知写操作结果不会自动重放，避免重复副作用。
- 首次 worker warm 是后台优化，Provider 网络、模型限流和真实模型响应时间仍可能波动；UI 会先给出状态反馈，不再无提示卡住。

## 5. 关键改动文件

- `appserver/server.py`
- `appserver/watchdog.py`
- `tests/test_appserver/test_stdio_integration.py`
- `frontend/desktop-app/src/renderer/src/App.tsx`
- `frontend/desktop-app/src/renderer/src/assets/main.css`
- `frontend/desktop-app/src/renderer/src/hooks/useConversation.ts`
- `frontend/desktop-app/src/platform/index.mts`
- `frontend/desktop-app/scripts/cdp-harness.mts`
- `frontend/desktop-app/scripts/gui-ux-regression.mts`
