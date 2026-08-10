# Phase 4 D7 交付记录：自动更新 + 崩溃上报

> 仓库：`D:\agent-demo\RxyCode-Desktop`（RxyCode-master 未改动，schema.json 零改动，protocol-client 零改动）
> 执行日期：2026-08-08 · 执行人：Composer 2.5
> 依赖：D6 commit `90d2775`；RxyCode 保持 v1.2.6（`D:\agent-demo\RxyCode-master` 仅只读引用）
> 平台状态：**Windows 实测通过（本机）**；macOS/Linux 构建待 CI/对应平台验证（本机为 Windows，无法真实执行，不谎报）

## 完成判据（验收 SOP）

- [x] 自动更新：`electron-updater` 6.8.9（generic provider，`electron-builder.yml` 既有 `publish` 配置）；设置页「更新与诊断」tab **手动触发**检查/下载/安装，启动时不强制检查，失败不影响旧版本运行（单测覆盖）
- [x] 更新端到端实测：本地 HTTP generic feed + 打包产物真实 electron-updater 流程 `check → available(0.1.1) → download → downloaded`，**不安装不重启**，应用版本保持 0.1.0（update-feed-smoke 全绿）
- [x] 崩溃上报：自建脱敏诊断包（无 Sentry 等第三方）；同意开关默认**关**、切换即生效并持久化（`userData/crash-report-consent.json`）；未同意时仅本机记录、同意后可上传（`RXYCODE_CRASH_REPORT_URL`）
- [x] 诊断包脱敏：只含版本/平台/协议状态/日志摘要；API Key、Authorization/Bearer、长 token、完整 prompt/工具输入输出在落盘前 scrubbed（单测 + crash-smoke 断言）
- [x] DC5：crash 处理对 manager 的 kill 幂等（null 安全、正常退出/重复触发安全）；crash-smoke **真实制造 renderer 崩溃**（`forcefullyCrashRenderer`）并断言 appserver 子进程无孤儿（非沙箱跑）
- [x] dev-app-update.yml 只服务 dev 模式（`forceDevUpdateConfig`），`electron-builder.yml` files 保持排除；打包产物用 electron-builder 生成的 `app-update.yml`
- [x] 全量验收：typecheck / lint / test（118 基线 + 18 新增 = 136 通过）/ build / electron-builder --win / update-feed-smoke / crash-smoke / D6 packaged-smoke 回归，全部真实跑通，输出见下
- [x] DC1：Desktop 仍只走 `protocol-client`，不 import Python / 不调 HTTP（更新走 electron-updater 下载、崩溃上传仅当用户同意）
- [x] 协议零变化：`RxyCode-master/protocol/schema.json` 未改动（工作区干净，sha256 `d0921c6e…`），`protocol-client` 未改动
- [x] 一张卡一个 commit，可单独 revert

## 改动文件清单

| 文件                                           | 改动                                                                                                                                                                                                                                                                                           |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/main/auto-update.ts`（新增）              | electron-updater 的测试化状态机包装：状态 `disabled/idle/checking/available/not-available/downloading/downloaded/error`；`autoDownload=false`、`autoInstallOnAppQuit=false`（全部手动）；feed URL 覆盖（`RXYCODE_UPDATE_FEED_URL`）；失败只进 error 状态、旧版本不动                           |
| `src/main/auto-update.test.mts`（新增）        | 8 条测试：disabled 不碰 updater、not-available、available→download→downloaded→install 流程、check 失败可重试、download 失败旧版本保留、feed 覆盖、强制手动、非法状态 no-op                                                                                                                     |
| `src/main/crash-report.ts`（新增）             | 脱敏崩溃诊断：`redactSecrets`/`truncateLine`/`sanitizeDetail`；consent 持久化（默认关）；capture 写 `userData/crash-reports/crash-<ts>-<id>.json`（schema `rxycode.crash-diagnostic.v1`）；同意+配置端点才上传；`onCrash` 钩子接 DC5 kill                                                      |
| `src/main/crash-report.test.mts`（新增）       | 9 条测试：脱敏（api_key/sk-/Bearer/长 token）、截断、嵌套 detail、consent 默认关且持久化、capture 落盘脱敏、仅同意+URL 才上传、listReports 排序、重复 capture 安全                                                                                                                             |
| `src/main/index.ts`                            | 崩溃事件接线（`render-process-gone`/`child-process-gone`/`uncaughtException`/`unhandledRejection`）+ 幂等 `shutdownAppserver`（DC5）；update/crash IPC；`UPDATE_SMOKE`/`CRASH_SIM` smoke 模式；`RXYCODE_DESKTOP_USER_DATA` 覆盖 userData+cache（smoke 隔离）；broadcast 对已销毁 renderer 安全 |
| `src/platform/index.mts`                       | `DiagnosticsPlatform` + `createDiagnosticsPlatform` + `useDiagnostics`（DC3：Electron 细节全在适配层后）                                                                                                                                                                                       |
| `src/platform/index.test.mts`                  | 新增 createDiagnosticsPlatform 委托测试                                                                                                                                                                                                                                                        |
| `src/preload/index.ts` / `index.d.ts`          | update / crashReport 桥接（IPC invoke + 事件订阅）                                                                                                                                                                                                                                             |
| `src/renderer/src/components/SettingsPage.tsx` | 新增「更新与诊断」tab：当前版本、更新状态、检查/下载/重启安装按钮、下载进度、崩溃上报同意开关（默认关）、最近诊断列表                                                                                                                                                                          |
| `src/renderer/src/App.tsx`                     | SettingsPage 传入 `appVersion`                                                                                                                                                                                                                                                                 |
| `src/renderer/src/assets/main.css`             | settings-toggle / crash-report-list 样式                                                                                                                                                                                                                                                       |
| `dev-app-update.yml`（新增）                   | dev 模式 generic feed 占位（打包 files 保持排除）                                                                                                                                                                                                                                              |
| `scripts/update-feed-smoke.mts`（新增）        | 本地 HTTP feed（latest.yml + 安装包流）+ 打包产物真实 check/download 断言                                                                                                                                                                                                                      |
| `scripts/crash-smoke.mts`（新增）              | 真实 renderer 崩溃 → 诊断包脱敏/字段断言 + 无孤儿 appserver（DC5）                                                                                                                                                                                                                             |
| `package.json`                                 | 依赖 `electron-updater@^6.8.9`；test 列表 + `smoke:update` / `smoke:crash`                                                                                                                                                                                                                     |
| `package-lock.json`                            | npm install 产物                                                                                                                                                                                                                                                                               |
| `README.md`                                    | 新命令与 dev 更新说明                                                                                                                                                                                                                                                                          |

## 关键设计决策（已定，不自行发挥）

- 自动更新用 electron-updater（electron-builder 标配），generic provider；主进程 bundle 内联（`externalizeDeps:false`），打包态不依赖 node_modules。
- `disableDifferentialDownload=true`：全量下载，避免 generic feed 上的 blockmap/range 依赖（feed smoke 实测）。
- 崩溃上报不引第三方：Electron `crashReporter` 无 `stop()` 无法干净开关，改为 JS 层事件捕获 + 脱敏诊断包（本地始终落盘、上传才需要同意）。
- 手动触发：启动/退出均不自动检查或安装（`autoDownload=false`、`autoInstallOnAppQuit=false`）。

## 命令与真实输出

### typecheck

```
> npm run typecheck
> tsc --noEmit -p tsconfig.node.json --composite false
> tsc --noEmit -p tsconfig.web.json --composite false
（退出码 0，无错误）
```

### lint

```
> npm run lint
> eslint --cache .
（退出码 0，无问题）
```

### test（118 基线 + 18 新增 = 136）

```
ℹ tests 136
ℹ suites 0
ℹ pass 136
ℹ fail 0
ℹ cancelled 0
ℹ duration_ms 6355.7013
（退出码 0；含 kill-tree/进程类用例，非沙箱运行）
```

新增 17 条（auto-update 8 + crash-report 9）与 platform 委托 1 条，全部 ✔。

### build + electron-builder --win（Windows 实测，最终代码）

```
> npm run build
✓ built (main/preload/renderer)
> npx electron-builder --win
• building        target=nsis file=dist\rxycode-desktop-0.1.0-setup.exe archs=x64
• building block map  blockMapFile=dist\rxycode-desktop-0.1.0-setup.exe.blockmap
（退出码 0；产物：dist\rxycode-desktop-0.1.0-setup.exe、dist\win-unpacked\，含 app-update.yml）
```

### update-feed-smoke（打包产物真实 electron-updater 流程，非沙箱）

```
Checking for update
Generated new staging user ID: 223bb8a4-a345-5961-ab10-a2574e3fbf95
Found version 0.1.1 (url: rxycode-desktop-0.1.1-setup.exe)
UPDATE_STATUS {"status":"available","currentVersion":"0.1.0","availableVersion":"0.1.1",...}
Downloading update from rxycode-desktop-0.1.1-setup.exe
updater cache dir: C:\Users\zxy\AppData\Local\Temp\rxycode-update-smoke-MlGelh\@rxycodedesktop-app-updater
New version 0.1.1 has been downloaded to ...\pending\rxycode-desktop-0.1.1-setup.exe
UPDATE_STATUS {"status":"downloaded","currentVersion":"0.1.0","availableVersion":"0.1.1",...}
UPDATE_SMOKE_OK app version stays 0.1.0, feed 0.1.1 checked+downloaded (not installed)
（退出码 0；缓存经 LOCALAPPDATA 重定向到临时目录，未污染真实 profile）
```

### crash-smoke（真实 renderer 崩溃 + DC5 无孤儿，非沙箱）

```
SMOKE_CHILD_PID 50344
CRASH_SOURCE render-process-gone
CRASH_REASON crashed
CRASH_REPORT_FILE C:\Users\zxy\AppData\Local\Temp\rxycode-crash-smoke-HsQatU\crash-reports\crash-2026-08-08T14-46-05-409Z-84314c29-....json
CRASH_SMOKE_OK diagnostic ... sanitized, no orphan appserver
（退出码 0；脚本断言：schema 字段、source、app.version、protocolVersion=1.0.0、logs 数组、无 secret 形态内容、appserver pid 已退出）
```

### packaged-smoke（D6 回归，打包产物真实握手）

```
SMOKE_RUNTIME bundled
SMOKE_CHILD_PID 34864
SMOKE_RESULT {"protocol_version":"1.0.0","server_name":"rxycode-appserver","capabilities":{"sessions":true,"approval":true}}
SMOKE_VIOLATIONS 0
SMOKE_DONE
SMOKE_OK child pid 34864 exited, no orphan process left
（退出码 0）
```

## 协议是否变化

- 否。`RxyCode-master/protocol/schema.json` 零改动（工作区干净，sha256 `d0921c6e…`）；`protocol-client` 零改动；Desktop 仍只通过 `protocol-client` 消费协议（DC1）。

## 已知限制

- 无真实更新/崩溃收集服务器：feed 与上传端点为占位（`https://example.com/auto-updates` / `RXYCODE_CRASH_REPORT_URL`），配置真实地址前检查会干净失败（error 状态）、上传不会发生。
- 原生 minidump（Electron crashReporter）未启用：Electron 39 无 `crashReporter.stop()`，无法干净随同意开关启停；本卡用 JS 层事件捕获 + 脱敏诊断包，覆盖 renderer/main JS 崩溃。
- macOS/Linux：配置沿用 D6，构建与 smoke 待 CI/对应平台验证（本机 Windows）。
- `npm run format`（prettier --write .）会重排 D3/D5 交付文档，不在本卡白名单内，已还原；新文件均已按 prettier 格式化。

## 回滚方式

- `git revert <本 commit>` 即可单独回滚；回滚后删除 `dev-app-update.yml` 引用（文件本身保留无副作用）。
- 自动更新未启用 `autoInstallOnAppQuit`，无后台安装副作用；更新下载缓存位于系统临时/用户缓存目录，可安全删除。
- 崩溃诊断与 consent 文件在 `userData/crash-reports/` 与 `userData/crash-report-consent.json`，回滚后不再产生新文件，旧文件可手动删除。
