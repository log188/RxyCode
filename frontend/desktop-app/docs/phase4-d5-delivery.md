# Phase 4 D5 交付记录：设置页（模型 / API Key / 工作区）+ 工作区目录选择与持久化

> 仓库：`D:\agent-demo\RxyCode-Desktop`（RxyCode-master 未改动）
> 执行日期：2026-08-08 · 执行人：Composer 2.5
> 视觉验收说明：**Grok 不可用、经阿里云 qwen3-vl-235b 本地识图、已获人工确认**。识图命令为 `node "C:\Users\zxy\.codex\skills\claude-vision-skill\vision.js" "<截图>" "<核对问题>"`；五张截图逐张识图核对通过（结论见下文表格）。
> 依赖：D2 commit `4879cd8`、D3 commit `297c68e`、D4 commit `7e12340`
> 前置状态：Phase 3（M1–M8）未落地（RxyCode-master 源码无 `resolve_output_limit` / `OutputLimitResolution` / `limit_source`，M1–M8 完成判据 0/48）；协议 schema 无 model / 凭据管理方法。按负责人确认的方案 A 执行：只做可独立完成部分，其余以 BLOCKED_PREREQUISITE 状态如实呈现，不造假数据。

## 完成判据（验收 SOP）

- [x] 设置页骨架 + 三 tab 导航（模型 / API Key / 工作区）— **已完成**
- [x] 工作区目录选择（Electron 原生目录对话框，主进程 `workspace:pick-directory` IPC）— **已完成**
- [x] 工作区选择持久化（版本化 localStorage key `rxycode.desktop.workspaceSettings.v1`，跨重启可加载）— **已完成**
- [x] 新会话使用所选工作区：通过既有协议字段 `session/new.workspace_root` 生效（未设置时回退后端仓库根目录）— **已完成**
- [x] 恢复默认：清除已保存工作区，回到后端仓库根目录 — **已完成**
- [x] 模型管理（复用后端 `config/model_manager.py`）— **前置缺失（blocked）**：protocol/schema.json 无 model 管理方法，Desktop 只能走 protocol-client（DC1）；RxyCode-master 冻结、schema.json 零改动，本卡不新增协议、不读取后端配置文件、不伪造数据
- [x] API Key 管理（DC4：系统密钥链）— **前置缺失（blocked）**：协议无凭据写入方法，密钥无消费方；不绕过协议自行落盘
- [x] Phase 3 上限来源摘要展示 — **前置缺失（blocked）**：M1–M8 未落地，协议无 `model_max_output_tokens` / `resolved_max_tokens` / `limit_source`；按验收要求不展示伪造上限数据
- [x] 不造假数据：三块阻塞区只显示 BLOCKED_PREREQUISITE 说明，无任何本地假数据顶替 — **已完成**
- [x] DC1：Desktop 仍只走 `protocol-client`，不 import Python / 不调 HTTP — **已完成**
- [x] DC3：Electron 特有能力集中在 `src/platform/` 与主进程（目录对话框经 IPC + preload + platform 适配器）— **已完成**
- [x] 协议零变化：`RxyCode-master/protocol/schema.json` 未改动，RxyCode-master 工作区干净；protocol-client 未改动 — **已完成**
- [x] 视觉验收：dev server（`RXYCODE_DESKTOP_FAKE_APPSERVER=1`）五态截屏 + 断言，逐张识图核对通过 — **已完成**
- [x] 一张卡一个 commit，可单独 revert — **已完成**

## 改动文件清单

| 文件 | 改动 |
| --- | --- |
| `src/renderer/src/lib/workspaceSettings.mts`（新增） | 纯函数：工作区设置加载/保存/规范化/生效值计算（版本化 localStorage） |
| `src/renderer/src/lib/workspaceSettings.test.mts`（新增） | 9 条测试：缺失/损坏/形状错误存储、往返、trim、兜底 |
| `src/main/workspace-dialog.ts`（新增） | 主进程目录选择 helper（可注入 dialog，可单测） |
| `src/main/workspace-dialog.test.mts`（新增） | 4 条测试：选中/取消/空列表/openDirectory 属性 |
| `src/main/index.ts` | 注册 `workspace:pick-directory` IPC handler |
| `src/preload/index.ts` | 暴露 `workspace.pickDirectory` |
| `src/preload/index.d.ts` | 补充 `workspace.pickDirectory` 类型 |
| `src/platform/index.mts` | `AppserverPlatform` 增加 `pickWorkspaceDirectory()`（Electron 能力集中于此，DC3） |
| `src/platform/index.test.mts` | 新增平台适配器委托测试；fake platform 补方法 |
| `src/renderer/src/components/SettingsPage.tsx`（新增） | 设置页：三 tab 导航、模型/API Key/上限摘要 blocked 面板、工作区面板 |
| `src/renderer/src/App.tsx` | 顶栏「设置」入口、工作区设置状态与持久化、接线 `useConversation` |
| `src/renderer/src/hooks/useConversation.ts` | `createSession` 使用工作区覆盖值（`workspaceRootOverride ?? info.repoRoot`） |
| `src/renderer/src/assets/main.css` | 设置页/blocked 面板/工作区卡片样式 |
| `scripts/settings-screenshot.mts`（新增） | D5 五态截图 + 断言驱动（CDP + 临时 profile） |
| `package.json` | test 列表加入 2 个新测试文件；`screenshot:d5` 脚本 |
| `docs/d5-screenshots/*.png` | 五张视觉验收截图 |
| `docs/phase4-d5-delivery.md`（本文件） | 交付记录 |

## 命令与真实输出

### typecheck

```
> @rxycode/desktop-app@0.1.0 typecheck
> npm run typecheck:node && npm run typecheck:web
> tsc --noEmit -p tsconfig.node.json --composite false
> tsc --noEmit -p tsconfig.web.json --composite false
（退出码 0，无错误）
```

### lint

```
> @rxycode/desktop-app@0.1.0 lint
> eslint --cache .
（退出码 0，零输出，无警告）
```

### test（93/93，沙箱外，kill-tree 需要真实 taskkill 权限）

```
✔ killProcessTree terminates the direct child and its descendants (398.77ms)
✔ pickWorkspaceDirectory returns the selected directory path
✔ pickWorkspaceDirectory returns null when the dialog is canceled
✔ pickWorkspaceDirectory returns null when no path was selected
✔ pickWorkspaceDirectory requests an open-directory dialog
✔ createAppserverPlatform pickWorkspaceDirectory delegates to the preload bridge
✔ stub appserver supports initialize, session/new and session/prompt over protocol-client
✔ EOF shutdown while a prompt is pending never resolves the pending prompt
✔ fake appserver approval round trip resolves an approved decision
✔ loadWorkspaceSettings returns the default when no value is stored
✔ loadWorkspaceSettings ignores malformed JSON and falls back to the default
✔ loadWorkspaceSettings rejects stored values with a non-string workspaceRoot
✔ loadWorkspaceSettings reads back a saved workspace root
✔ saveWorkspaceSettings round-trips through loadWorkspaceSettings
✔ normalizeWorkspaceRoot trims surrounding whitespace
✔ normalizeWorkspaceRoot turns blank values into null
✔ effectiveWorkspaceRoot uses the saved workspace when set
✔ effectiveWorkspaceRoot falls back to the repo root when nothing is saved
ℹ tests 93 · pass 93 · fail 0
```

（其余既有测试逐条通过，未在本文档重复粘贴；完整输出见上方 test 命令实际运行记录。）

### build

```
out/main/index.js      14.80 kB
out/preload/index.js    3.80 kB
out/renderer/assets/index-DmdRGEVB.css   12.01 kB
out/renderer/assets/index-D7oDsng8.js  607.00 kB
✓ built（退出码 0）
```

### screenshot:d5（视觉验收驱动，全新临时 profile 保证确定性）

```
SCREENSHOT_STEP 01-main-settings-button  SCREENSHOT_SAVED ...\01-main-settings-button.png
SCREENSHOT_STEP 02-model-blocked         SCREENSHOT_SAVED ...\02-model-blocked.png
SCREENSHOT_STEP 03-apikey-blocked        SCREENSHOT_SAVED ...\03-apikey-blocked.png
SCREENSHOT_STEP 04-workspace-default     SCREENSHOT_SAVED ...\04-workspace-default.png
SCREENSHOT_STEP 05-workspace-saved       SCREENSHOT_SAVED ...\05-workspace-saved.png
SCREENSHOT_D5_OK settings states captured and asserted
SCREENSHOT_OK D:\agent-demo\RxyCode-Desktop\docs\d5-screenshots
（退出码 0）
```

驱动内置断言：模型 tab 2 个 blocked 面板、API Key tab 1 个 blocked 面板、工作区默认态显示 `info.repoRoot`、预置持久化后 reload 仍显示 `D:\demo-workspace`（与 D4 的持久化规则截图同法，原生目录对话框无法无头驱动，故通过同一版本化 localStorage key 预置后全量 reload 验证）。

## 多模态环节（视觉验收，识图逐张核对）

识图：`node "C:\Users\zxy\.codex\skills\claude-vision-skill\vision.js" "<截图>" "<核对问题>"`（qwen3-vl-235b-a22b-thinking）

| 截图 | 核对结论 |
| --- | --- |
| [01-main-settings-button.png](d5-screenshots/01-main-settings-button.png) | ✅ 顶栏含「设置」按钮；品牌名、RUNNING 徽章、设置/权限/Start/Stop 布局正常，无乱码/错位 |
| [02-model-blocked.png](d5-screenshots/02-model-blocked.png) | ✅ 模型 tab：标题、三 tab 导航、两个 BLOCKED_PREREQUISITE 红色面板（模型管理不可用 / Phase 3 上限来源摘要不可用）均正常，中英文无乱码 |
| [03-apikey-blocked.png](d5-screenshots/03-apikey-blocked.png) | ✅ API Key tab：标题、一个 BLOCKED_PREREQUISITE 面板（API Key 管理不可用）正常，无乱码/溢出（首次识图遇 API 429 限流，重试通过） |
| [04-workspace-default.png](d5-screenshots/04-workspace-default.png) | ✅ 工作区默认态：当前生效为 `D:\agent-demo\RxyCode-master`、已保存设置为未设置、选择目录/恢复默认按钮与说明正常 |
| [05-workspace-saved.png](d5-screenshots/05-workspace-saved.png) | ✅ 工作区已保存态：当前生效与已保存设置均为 `D:\demo-workspace`，恢复默认可用，说明文字正常 |

## 协议是否变化

**否**。`RxyCode-master/protocol/schema.json` 未改动，JSON-RPC 方法/事件未新增；`protocol-client` 未改动。工作区功能仅消费既有 `session/new.workspace_root` 字段。

## 已知限制

1. **模型 / API Key / Phase 3 上限摘要三块被 Phase 3 与协议方法阻塞**（供向负责人汇报）：
   - Phase 3（M1–M8）未落地：RxyCode-master 无按真实 model_id 解析输出上限的模块，无 `limit_source` 摘要协议字段，计划文档 M1–M8 完成判据 0/48；
   - protocol/schema.json 无 model 管理 / 凭据写入方法，Desktop 在「只走 protocol-client（DC1）+ schema 零改动 + RxyCode-master 冻结」约束下无法复用后端 `config/model_manager.py`；
   - 三块均以 BLOCKED_PREREQUISITE 状态如实呈现，未用本地假数据顶替。
2. 工作区「选择目录」为原生对话框，截图驱动无法无头点击，持久化状态通过同一版本化 localStorage key 预置 + 全量 reload 验证（与 D4 持久化规则截图同法）；真实点击路径由主进程单测 + IPC 接线覆盖。
3. 工作区设置存 renderer localStorage（明文、随 Electron profile 保存），与 D4 的 always-allow 规则同属本阶段桌面端方案；Phase D 后端 session store 落地后可迁移。
4. `screenshot:d5` 需要沙箱外权限（Electron GUI + taskkill 清理），与 D3/D4 一致；截图使用临时 profile，不污染默认用户数据。
5. 视觉验收经阿里云 qwen3-vl-235b 本地识图完成（Grok 不可用），一次识图触发 API 429 限流后重试通过；结论已写入本记录并按流程获人工确认。

## 回滚方式

单 commit 可直接回滚：

```powershell
git revert <D5 commit>
```

或

```powershell
git checkout <D5 commit>~1 -- <受影响的文件>
```

回滚不影响 `RxyCode-master`（未触碰）；协议无变化，回滚后无需重新生成类型。
