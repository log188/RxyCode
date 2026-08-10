# Phase 4 D4 交付记录：审批 UI（approval/request 模态框）+ 作用域化 always allow 持久化

> 仓库：`D:\agent-demo\RxyCode-Desktop`（RxyCode-master 未改动）
> 执行日期：2026-08-07 · 执行人：Composer 2.5
> 视觉验收说明：**Grok 不可用、经阿里云 qwen3-vl-235b 本地识图、已获人工确认**。识图命令为 `node "C:\Users\zxy\.codex\skills\claude-vision-skill\vision.js" "<截图>" "<核对问题>"`；六张截图逐张识图核对通过（结论见下文表格）。该环节不默认满足 playbook 的 Grok 流程，按人工确认的方案执行。
> 依赖：D3 commit `297c68e`

## 完成判据（验收 SOP）

- [x] `approval/request` 服务端请求接线：平台连接层 `onServerRequest` 已接通，模态框展示 `risk_level` / `action` / `details`；未支持的服务端请求返回 JSON-RPC 错误（不静默吞掉）
- [x] 三个决策按钮：批准 / 拒绝 / 始终允许；批准回 `approved`、拒绝回 `rejected`（schema 枚举，协议零改动）
- [x] always allow 持久化：版本化 localStorage key（`rxycode.desktop.approvalRules.v1`），跨重启可加载；命中规则自动回 `approved`，**不发送 `always_allow_level`**（避免服务端按风险级放行绕过作用域，DC-A5）
- [x] 作用域：规则绑定 工作区 + 风险级 + 动作匹配（仅此动作/同类动作前缀/此工作区此等级），有效期可选 1h / 24h / 7d
- [x] 可撤销：顶栏「权限」打开规则管理弹层，空态/列表/撤销齐全；撤销后立即持久化
- [x] 可过期：过期规则不参与匹配，加载时自动清理
- [x] 状态机：pending（等待用户）→ submitting（决策已发送，弹层保留「正在提交…」直到 `event/done` 收尾移除）→ error（连接断开时 fail-closed，弹层显示错误并可关闭）
- [x] 重复防护：`request_id` 去重，同一请求不会重复弹窗
- [x] 集成：fake appserver 审批往返测试通过（`approval/request` → 客户端决策 → 工具卡片收尾）；真实 stub appserver 原有测试不受影响
- [x] 自动审批演示：预置持久化规则后 `approval auto` 场景全程不弹窗，`SCREENSHOT_AUTO_OK` 断言通过
- [x] 边界：Desktop 仍只走 `protocol-client`（DC1），不 import Python / 不调 HTTP；Electron 特有能力仍集中在 `src/platform/`（DC3）
- [x] 协议零变化：`RxyCode-master/protocol/schema.json` 未改动，RxyCode-master 工作区干净；`protocol-client` 仅补导出既有类型 `ApprovalResponse`
- [x] 视觉验收：dev server（`RXYCODE_DESKTOP_FAKE_APPSERVER=1`）六态截屏，逐张识图核对通过
- [x] 一张卡一个 commit，可单独 revert

## 改动文件清单

| 文件                                                         | 改动                                                                                                                                                                          |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/renderer/src/lib/approvalPolicy.mts`（新增）            | 纯函数：规则创建/校验、匹配（工作区+风险级+动作 scope）、过期、加载/保存/清理                                                                                                 |
| `src/renderer/src/lib/approvalPolicy.test.mts`（新增）       | 14 条策略测试（作用域匹配、过期、malformed 存储、持久化）                                                                                                                     |
| `src/renderer/src/lib/conversationStore.mts`                 | `approvals` 状态 + `addApprovalRequest` / `updateApprovalRequestStatus` / `removeApprovalRequest` / `removeApprovalRequestsForSession`；`applyRunComplete` 收尾移除本会话审批 |
| `src/renderer/src/lib/conversationStore.test.mts`            | 新增 7 条审批 reducer 测试                                                                                                                                                    |
| `src/renderer/src/hooks/useConversation.ts`                  | `onServerRequest` 接线（自动审批/入队）、决策 resolve、作用域规则保存/撤销、连接中止 fail-closed                                                                              |
| `src/renderer/src/components/ApprovalModal.tsx`（新增）      | 审批弹层：正常态（风险徽章/动作/详情/三按钮）、作用域表单、submitting、error                                                                                                  |
| `src/renderer/src/components/ApprovalRulesModal.tsx`（新增） | 规则管理弹层：空态、规则列表、撤销                                                                                                                                            |
| `src/renderer/src/App.tsx`                                   | 挂载两个弹层、顶栏「权限」按钮、Start/Stop 按钮类名（供验收驱动选择器）                                                                                                       |
| `src/renderer/src/assets/main.css`                           | 弹层/风险徽章/表单/规则列表样式                                                                                                                                               |
| `src/platform/index.mts`                                     | 连接层支持 `onServerRequest` 与 `onServerRequestAborted`（attach 接线、detach/失败清理中止）                                                                                  |
| `src/platform/index.test.mts`                                | 2 条：审批服务端请求接线回写、detach 中止待决审批                                                                                                                             |
| `src/renderer/src/lib/appserver.integration.test.mts`        | fake appserver 审批往返集成测试                                                                                                                                               |
| `protocol-client/src/index.ts`                               | 补导出 `ApprovalResponse`（schema 既有类型）                                                                                                                                  |
| `protocol-client/src/types.test.ts`                          | `ApprovalResponse` 类型断言                                                                                                                                                   |
| `scripts/fake-appserver.mjs`                                 | approval 场景（正常/拒绝/自动）+ 服务端请求响应路由                                                                                                                           |
| `scripts/approval-screenshot.mts`（新增）                    | D4 六态截图 + 自动审批断言驱动（CDP + 临时 profile）                                                                                                                          |
| `package.json`                                               | test 列表加入策略测试；`screenshot:d4` 脚本                                                                                                                                   |
| `docs/d4-screenshots/*.png`                                  | 六张视觉验收截图                                                                                                                                                              |

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

### test（79/79，沙箱外，kill-tree 需要真实 taskkill 权限）

```
✔ attach wires approval server requests to onServerRequest and writes the reply
✔ detach aborts pending approval server requests with the detach reason
✔ createApprovalRule stores scope, risk, workspace and derives expiry from hours
✔ ruleMatchesRequest requires the same workspace and risk level
✔ exact scope matches only the exact action
✔ prefix scope matches actions starting with the prefix
✔ any scope matches any action at the same workspace and risk level
✔ expired rules never match
✔ loadApprovalRules reads valid rules, skips malformed entries and prunes expired
✔ fake appserver approval round trip resolves an approved decision
✔ addApprovalRequest appends a pending approval item
✔ updateApprovalRequestStatus flips status and attaches an error
✔ removeApprovalRequestsForSession removes only that session approvals
✔ applyRunComplete removes submitting approvals for the session
ℹ tests 79 · pass 79 · fail 0
```

### build

```
out/main/index.js      14.34 kB
out/preload/index.js    3.69 kB
out/renderer/assets/index-DmbSiULy.css   9.48 kB
out/renderer/assets/index-D8mqEWwk.js  598.47 kB
✓ built（退出码 0）
```

### screenshot:d4（视觉验收驱动，全新临时 profile 保证确定性）

```
SCREENSHOT_STEP 01-rules-empty        SCREENSHOT_SAVED ...\01-rules-empty.png
SCREENSHOT_STEP 02-approval-normal    SCREENSHOT_SAVED ...\02-approval-normal.png
SCREENSHOT_STEP 03-always-allow-form  SCREENSHOT_SAVED ...\03-always-allow-form.png
SCREENSHOT_STEP save-rule
SCREENSHOT_STEP 04-rules-list         SCREENSHOT_SAVED ...\04-rules-list.png
SCREENSHOT_STEP 05-approval-submitting SCREENSHOT_SAVED ...\05-approval-submitting.png
SCREENSHOT_STEP 06-approval-error     SCREENSHOT_SAVED ...\06-approval-error.png
SCREENSHOT_STEP auto-approval
SCREENSHOT_AUTO_OK persisted rule auto-approved without the modal
SCREENSHOT_OK D:\agent-demo\RxyCode-Desktop\docs\d4-screenshots
（退出码 0）
```

## 多模态环节（视觉验收，识图逐张核对）

识图：`node "C:\Users\zxy\.codex\skills\claude-vision-skill\vision.js" "<截图>" "<核对问题>"`（qwen3-vl-235b-a22b-thinking）

| 截图                                                                    | 核对结论                                                                                                             |
| ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| [01-rules-empty.png](d4-screenshots/01-rules-empty.png)                 | ✅ 标题「权限 · 始终允许规则」、空态提示、关闭按钮，无乱码/错位                                                      |
| [02-approval-normal.png](d4-screenshots/02-approval-normal.png)         | ✅ WRITE 徽章、审批请求标题、动作描述、JSON 详情（tool_name/command/workspace_root）、批准/拒绝/始终允许三按钮均正常 |
| [03-always-allow-form.png](d4-screenshots/03-always-allow-form.png)     | ✅ 三个作用域单选（仅此动作/同类动作/此工作区此等级）及说明、有效期下拉（默认 24 小时）、保存并允许/取消均正常       |
| [04-rules-list.png](d4-screenshots/04-rules-list.png)                   | ✅ 一条 WRITE 规则（仅此动作 + 动作 + 工作区/有效期）、撤销/关闭按钮、Windows 路径与时间格式均正常                   |
| [05-approval-submitting.png](d4-screenshots/05-approval-submitting.png) | ✅ 「正在提交…」提示，无决策按钮，无红色报错，布局正常                                                               |
| [06-approval-error.png](d4-screenshots/06-approval-error.png)           | ✅ 「审批请求失败」+ 动作 + `appserver not running` 错误信息 + 关闭按钮；顶栏 STOPPED 状态与错误一致，无乱码         |

过程修复（自动化/识图发现 → 已修）：

1. 点击批准后弹层立即消失、无 submitting 态 → 决策后保留弹层为 submitting，`event/done` 收尾时按会话移除；
2. 顶栏停止按钮无 class，验收驱动无法触发错误态 → 增加 `appserver-stop`（Start 同理 `appserver-start`）；
3. 旧 profile 残留规则导致空态截图不稳定 → 截图驱动使用全新临时 `--user-data-dir`；
4. `location.reload()` 未真正产生新渲染上下文（规则不重新加载）→ 改用 CDP `Page.reload` 并加 marker 断言。

## 协议是否变化

**否**。`RxyCode-master/protocol/schema.json` 未改动，JSON-RPC 方法/事件未新增；`protocol-client/src/index.ts` 仅补导出 schema 中已存在的 `ApprovalResponse` 类型。决策值严格使用现有枚举（`approved` / `rejected`）；`always_allow_level` 通道未启用（原因见完成判据第 3 条）。

## 已知限制

1. **always allow 持久化使用 renderer localStorage（明文、随 Electron profile 保存）是 D4 阶段方案**；Phase D 将迁移到后端 session store（服务端策略/作用域/审计），本卡不扩大范围。
2. 协议级 `always_allow_level`（服务端按风险级缓存）未启用：它会把同等级所有动作在会话内自动放行，绕过本卡的作用域规则（DC-A5）。后续 Phase D 由服务端策略承载后再接回。
3. 弹层一次展示一个待决审批（取 `approvals[0]`）；多并发审批请求会在队列中依次出现，本卡未做多弹层堆叠。
4. `protocol-client` 的测试使用 bun，本机未安装，`types.test.ts` 的 `ApprovalResponse` 断言未在本地运行；类型面由 desktop 的 `tsc` 覆盖，协议客户端运行时代码未改动。
5. `screenshot:d4` 需要沙箱外权限（Electron GUI + taskkill 清理），与 D3 的 `screenshot:d3` 一致；截图使用临时 profile，不污染默认用户数据。
6. 审批提交后弹层保留至 `event/done`；若 appserver 不继续推进（不发 done），弹层会停在 submitting——与后端审批超时（fail-closed 转 rejected）配合后会自动收尾，本卡未在 UI 侧另加超时。

## 回滚方式

单 commit 可直接回滚：

```powershell
git revert <D4 commit>
```

或

```powershell
git checkout 297c68e -- <受影响的文件>
```

回滚不影响 `RxyCode-master`（未触碰）；协议无变化，回滚后无需重新生成类型。
