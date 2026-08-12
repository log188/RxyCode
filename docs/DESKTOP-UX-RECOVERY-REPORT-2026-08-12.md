# RxyCode Desktop UX / Recovery 回归报告（2026-08-12）

## 结论

本轮针对 Codex 风格 Composer、发送、审批、删除性能、浅色主题、设置键盘行为和三档安全模式完成实现并通过回归。真实 Electron/CDP UX suite 为 7/7 通过；Desktop Node suite 为 182/182 通过；TypeScript typecheck 和 Electron production build 通过。

## 修复范围

- Composer 改为圆角任务输入面板：附件入口、任务级审批模式、分组模型选择、麦克风占位、圆形发送/停止按钮。
- Enter 提交，Shift+Enter 保留换行；发送按钮和停止按钮有稳定 `data-testid`。
- 审批决定一经回复立即关闭模态框；任务仍在后台运行时由时间线和任务状态表达，不再把模态框卡在“正在提交”。拒绝现在正确产生 failed 终态。
- `session/trash` 前端乐观更新；appserver 先返回持久化软删除结果，再后台清理 worker。
- 设置页支持 General、三档安全模式、主题和语言偏好；ESC 和点击遮罩关闭；Full access 必须二次确认。
- Desktop prompt 把安全模式作为 request-local 参数传递到 worker，通过 async task-local context 覆盖，避免并发窗口互相污染。
- Light theme 使用语义 token，避免旧的深色硬编码面板覆盖浅色主题。

## 测试命令与结果

| 检查 | 命令 | 结果 |
|---|---|---|
| Desktop Node 全量 | `npm test` | 182 passed / 0 failed |
| Desktop 类型检查 | `npm run typecheck` | passed |
| Desktop 构建 | `npm run build` | passed |
| Electron UX | `npm run test:gui:ux` | UX-01～UX-07 全部 passed |
| Python 三档权限 | 当前 worktree 显式包命名空间启动 `pytest tests/test_core/test_permission_mode.py -q` | 4 passed |
| Python 语法 | `python -m compileall -q appserver core execution tests/test_core/test_permission_mode.py` | passed |
| 空白检查 | `git diff --check` | passed |

## Electron UX 场景

1. Composer 结构、发送箭头、任务审批模式存在。
2. Enter 真实发送任务并进入运行态。
3. 批准审批后模态框关闭，后台任务正常到达终态，RPC 对账完成。
4. Light theme 的 canvas/composer surface 不再泄漏深色背景。
5. Full access 选择触发确认弹窗，取消后不改变模式。
6. 打开 Settings 后按 ESC 关闭。
7. 删除任务立即出现在 Recently deleted，不等待 worker 清理。

工件目录：`frontend/desktop-app/artifacts/gui-ux-1786536207002/`（本地临时目录，不纳入提交）。多模态检查的最终浅色截图验证了浅灰画布、白色面板、圆角 Composer 和右下角模型/发送布局。

## 已知边界

- 语言选择已持久化并作为 Desktop 偏好暴露；现有历史组件中的旧字符串资源尚未在本轮全部翻译重写。
- 麦克风按钮按 Codex 布局预留，但当前没有语音输入后端 capability，因此保持 disabled。
- 本轮 GUI 使用 fake appserver 做确定性 Electron 验收；真实 Provider 测试仍应在 Phase B 合并后按现有 DTS suite 执行。
- 本机全局 editable Python 包仍指向另一个 worktree，因此 Python 定向测试使用当前 worktree 的显式包命名空间；未修改全局安装。

## 清理证明

UX suite 每轮使用独立 Electron profile、data directory、workspace worktree、动态 DevTools 端口，并在 `finally` 中终止自己启动的进程树。最终通过轮次确认 WebSocket、Electron、appserver、DevTools 端口、临时 worktree、临时目录和 lease 清理完成；源配置保持 byte-for-byte 不变。
