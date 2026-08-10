# Phase 4 D3 交付记录：流式渲染 + 工具调用卡片 + 中断

> 仓库：`D:\agent-demo\RxyCode-Desktop`（RxyCode-master 未改动）
> 执行日期：2026-08-07 · 执行人：Composer 2.5
> 视觉验收说明：视觉验收因 Grok 不可用，经本地识图能力（阿里云 qwen3-vl-235b-a22b-thinking）完成，方案已获负责人/人工确认（人工确认痕迹：2026-08-07 用户消息批准「本对话现在具备识图能力，多模态环节由你完成，不再"等 Grok 停下报告"」，并指定识图命令 `node "C:\Users\zxy\.codex\skills\claude-vision-skill\vision.js" "<截图>" "<问题>"`）。该环节不默认满足 playbook 的 Grok 流程。
> 依赖：D1/D2 基线 commit `4879cd8`

## 完成判据（验收 SOP）

- [x] 流式渲染：`event/message_delta` 增量文本实时追加并自动滚动到底部
- [x] 工具调用卡片：`event/tool_begin` 创建 running 卡片，`event/tool_end` 更新为 ok/error + 摘要
- [x] 中断：运行中输入区按钮变为「停止」，点击发送 `session/interrupt`，`event/done` 正确收尾（取消保留部分文本；failed/timed_out 转错误态）
- [x] 错误幂等：`event/error` 与 RPC 错误响应不会重复追加错误消息
- [x] DC5 进程树强杀：`killProcessTree`（win32 `taskkill /T /F`，POSIX 进程组 SIGKILL）有回归测试
- [x] DC5 强杀回归：「强制杀 Electron（`taskkill /T /F`）后 appserver 退出、无孤儿进程」真实跑通
- [x] initialize 失败自动重试（默认 3 次退避）+ 连接错误状态暴露（UI 横幅）
- [x] `setWindowOpenHandler`：http/https 白名单 + `dialog` 确认（明确用户动作）；`will-navigate` 拦截
- [x] `will-navigate` 严格白名单：仅允许精确的生产 `index.html` file:// 路径与精确的 `ELECTRON_RENDERER_URL`（dev），拒绝其它 file:// 与任意 http(s)/javascript:/data: 导航
- [x] sandbox 收紧：`contextIsolation: true / nodeIntegration: false / sandbox: true`，preload 改为自包含 bundle
- [x] `stop()` 杀进程后等待加有限超时（不再无限挂起）
- [x] lockfile 根 name 对齐：回归校验测试（根与 protocol-client 两个 lockfile）
- [x] 多模态环节：dev server 起真实窗口，五态截图（空态/正常态/加载态/错误态/窄窗口）逐张识图核对通过

## 改动文件清单

| 文件 | 改动 |
|---|---|
| `src/renderer/src/lib/conversationStore.mts` | 工具卡模型/`applyToolBegin`/`applyToolEnd`/`applyRunComplete`/`applyProtocolNotification`；`applyError` 幂等 |
| `src/renderer/src/lib/conversationStore.test.mts` | 新增 13 个 reducer/路由测试 |
| `src/renderer/src/hooks/useConversation.ts` | 通知改走 store 路由；`connectionError` 状态；`interrupt()` 发送 `session/interrupt` |
| `src/renderer/src/components/ChatArea.tsx` | 工具卡渲染；滚动容器修正（`chat-area` 滚动到底） |
| `src/renderer/src/components/Composer.tsx` | 运行中「停止」按钮 + 占位提示 |
| `src/renderer/src/App.tsx` | 连接错误横幅；透传 tools/onStop |
| `src/renderer/src/assets/main.css` | 工具卡状态样式（running/ok/error 琥珀）；错误横幅间距；`main-layout` 行高约束；≤640px 隐藏会话面板 |
| `src/platform/index.mts` | initialize 有界重试（默认 3 次）+ `onConnectionError`；detach 中断重试 |
| `src/platform/index.test.mts` | 重试/错误上报/超时语义测试 |
| `protocol-client/src/index.ts` | 补导出 `InterruptRequest`/`RunComplete`/`ToolBegin`/`ToolEnd` 类型（schema 未动） |
| `src/main/appserver.ts` | `killProcessTree`；spawn 进程组；孤儿守卫（Job Object / POSIX guard）；`stop()` 有限超时；fake appserver 开关 |
| `src/main/index.ts` | sandbox 收紧；外链白名单+确认；`will-navigate`；窗口尺寸 env；keepalive smoke 模式 |
| `src/main/external-url.ts` + test | 外链白名单纯函数 |
| `src/main/navigation.ts` + test | `will-navigate` 严格白名单纯函数（精确 URL 相等） |
| `src/main/kill-tree.test.mts` | 进程树强杀回归（子进程+孙进程） |
| `src/main/lockfile.test.mts` | lockfile 根 name 对齐回归 |
| `scripts/fake-appserver.mjs` | 仓库内确定性协议假 appserver（tool/slow/fail 场景，测试设施） |
| `scripts/screenshot.mts` | CDP 截图驱动（dev server 五态） |
| `scripts/force-kill-smoke.mts` | DC5 强杀回归（真实 Electron）：第一阶段仅杀主进程断言守卫生效，第二阶段清理残余 Electron 子进程 |
| `scripts/win-job-guard.ps1` / `scripts/orphan-guard.mjs` | Windows Job Object（KILL_ON_JOB_CLOSE）/ POSIX 孤儿守卫 |
| `electron.vite.config.ts` | preload 只外部化 `electron`（sandbox 兼容） |
| `package.json` | test 脚本（禁 type-strip 警告）+ `smoke:force-kill` + `screenshot:d3` |
| `docs/d3-screenshots/*.png` | 五态视觉验收截图 |

## 命令与真实输出

以下均为本机最终运行结果（完整输出见会话记录，这里保留关键行）：

### typecheck
```
> tsc --noEmit -p tsconfig.node.json --composite false
> tsc --noEmit -p tsconfig.web.json --composite false
（退出码 0，无错误）
```

### lint
```
> eslint --cache .
（退出码 0，无警告）
```

### test（54/54，沙箱外，kill-tree 需要真实 taskkill 权限）
```
✔ killProcessTree terminates the direct child and its descendants
✔ attach retries initialize after a transient error and succeeds on the second attempt
✔ attach gives up after max attempts, cleans up, and reports the connection error
✔ applyToolBegin appends a running tool card to the session
✔ applyToolEnd marks the matching tool card ok with its summary
✔ applyRunComplete stops the session and keeps partial streaming text on cancel
✔ applyError does not append a duplicate message when the last one already errored
✔ isSafeExternalUrl rejects non-http(s) schemes
✔ root package-lock.json name matches package.json
✔ allows the exact production index.html URL
✔ rejects dev URLs that differ from the renderer URL and non-http schemes
ℹ tests 54 · pass 54 · fail 0
```

### build
```
out/main/index.js      14.34 kB
out/preload/index.js    3.69 kB
out/renderer/assets/index-DVk13d8o.css   5.90 kB
out/renderer/assets/index-BJAkxlKL.js  582.13 kB
✓ built（退出码 0）
```
> 尺寸说明：14.34 kB 为本次（含导航白名单改动后）生产构建实测输出；早期记录的 13.21 kB 与 dev 构建的 14.01 kB 是代码变更前/开发构建注入的产物，数值随源码变化，以 commit 后复跑 `npm run build` 为准。

### smoke（正常退出 DC5）
```
SMOKE_CHILD_PID 38488
SMOKE_RESULT {"protocol_version":"1.0.0","server_name":"rxycode-appserver","capabilities":{"sessions":true,"approval":true}}
SMOKE_VIOLATIONS 0
SMOKE_DONE
SMOKE_OK child pid 38488 exited, no orphan process left
SMOKE_EXIT=0
```

### smoke:force-kill（DC5 强杀回归：仅杀主进程 → 守卫断言 → 清理残余）
```
SMOKE_CHILD_PID 52048
SMOKE_RESULT {"protocol_version":"1.0.0","server_name":"rxycode-appserver","capabilities":{"sessions":true,"approval":true}}
SMOKE_VIOLATIONS 0
SMOKE_READY
SMOKE_FORCE_KILL_TARGET electron 20984 appserver 52048
SMOKE_GUARD_OK appserver 52048 exited after main-only Electron kill
SMOKE_FORCE_KILL_OK no orphan appserver, Electron children cleaned up
SMOKE_FORCE_KILL_EXIT=0
```
复跑（稳定性确认）：`electron 13972 / appserver 36828`，同样 `SMOKE_GUARD_OK` + `SMOKE_FORCE_KILL_OK`。

> 覆盖说明：第一阶段 `taskkill /PID <electron> /F`（不带 `/T`）后 Electron 主进程已死，appserver 仍被 Windows Job Object（KILL_ON_JOB_CLOSE）经守卫进程父进程检测路径终止，证明守卫真实生效而非仅靠树杀传播；第二阶段统一清理残余 Electron 子进程。

### screenshot:d3（视觉验收驱动）
```
SCREENSHOT_SAVED docs/d3-screenshots/01-empty.png
SCREENSHOT_SAVED docs/d3-screenshots/02-normal.png
SCREENSHOT_SAVED docs/d3-screenshots/03-loading.png
SCREENSHOT_SAVED docs/d3-screenshots/04-error.png
SCREENSHOT_SAVED docs/d3-screenshots/05-narrow.png
SCREENSHOT_OK
（错误态/窄窗口布局诊断：composer.bottom == innerHeight，chat-area scrollTop > 0，无横向溢出）
```

## 多模态环节（视觉验收，识图逐张核对）

识图：`node "C:\Users\zxy\.codex\skills\claude-vision-skill\vision.js" "<截图>" "<核对问题>"`（qwen3-vl-235b-a22b-thinking）

| 截图 | 核对结论 |
|---|---|
| [01-empty.png](d3-screenshots/01-empty.png) | ✅ 标题、RUNNING 徽章、会话空提示、对话区空态、输入区占位与禁用发送钮均正常，无乱码/错位 |
| [02-normal.png](d3-screenshots/02-normal.png) | ✅ 会话项、用户消息、助手消息、两张绿色完成工具卡（bash/read_file 含摘要）、发送钮、RUNNING 徽章均正常 |
| [03-loading.png](d3-screenshots/03-loading.png) | ✅ 流式文本、运行中指示、金色 running 工具卡、红色「停止」按钮、运行中占位提示均正常 |
| [04-error.png](d3-screenshots/04-error.png) | ✅ 仅一条红色错误消息、琥珀色工具失败卡、红色错误横幅与上方有间距、输入区可见、RUNNING 徽章正常 |
| [05-narrow.png](d3-screenshots/05-narrow.png) | ✅ 480px 下无横向滚动条、会话面板隐藏、内容独占宽度、摘要换行不截断、横幅不重叠、输入区完整 |

过程修复（识图发现 → 已修）：错误消息重复追加 → `applyError` 幂等；输入区被挤出视口 → `main-layout` 增加 `grid-template-rows: minmax(0,1fr)` + 滚动容器修正；工具失败卡与助手错误同色 → 琥珀色；窄窗口横向溢出 → ≤640px 隐藏会话面板 + 工具卡允许换行；错误横幅与工具卡重叠 → 增加间距。

## 协议是否变化

**否**。`RxyCode-master/protocol/schema.json` 未改动；JSON-RPC 方法/事件名未新增。`protocol-client/src/index.ts` 仅补导出 schema 中已存在的类型（`InterruptRequest`/`RunComplete`/`ToolBegin`/`ToolEnd`），属于客户端类型面补齐，不改变线上协议。

## 已知限制

1. 孤儿守卫的脚本路径在**打包（asar）环境**下会跳过（`app.asar` 检测），打包后的硬杀兜底需在 D6 打包卡中改为从 `resources/` 或解包目录加载——当前 dev/构建产物路径均可用。
2. `smoke`/`smoke:force-kill`/`screenshot:d3` 需要非沙箱权限（`taskkill` 与 Electron GUI）；`kill-tree` 单元测试同理，属环境限制而非代码问题。
3. 视觉验收截图由 CDP 抓取页面视口（不含系统窗口边框）。
4. 窄窗口（≤640px）下会话面板隐藏（保留数据，恢复宽度即回显），是 D3 阶段的响应式取舍，未做抽屉式导航。
5. `npm test` 通过 `--disable-warning=MODULE_TYPELESS_PACKAGE_JSON` 抑制 Node 对 `.ts` 类型剥离的启动告警（项目未开启 `"type": "module"`，属既有工程决策，不在本卡改动）。

## 回滚方式

单 commit 可直接回滚：
```powershell
git revert <D3 commit>
```
或
```powershell
git checkout 4879cd8 -- <受影响的文件>
```
回滚不影响 `RxyCode-master`（未触碰）；协议无变化，回滚后无需重新生成类型。
