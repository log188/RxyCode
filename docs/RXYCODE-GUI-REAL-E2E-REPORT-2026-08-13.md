# RxyCode GUI 真实业务 e2e 验收报告

- 计划文件名日期：2026-08-13
- 执行完成：2026-08-16
- 分支：`codex/rxycode-gui-real-e2e`（隔离 worktree）
- 基线：本地 `master@709e0dd`；合入时本地 `master` 另有 `41b8649`（stream thinking）
- 模型：`opencode-go/deepseek-v4-flash`
- 网关：`https://opencode.ai/zen/go/v1`
- 未使用官网 DeepSeek（`api.deepseek.com`）
- 未 push、未创建 PR
- 未提交 `diag_*.py`、`.env.t09-mysql` 或任何数据库/演示口令
- 原始工件在 `D:\agent-demo\RxyCode\RxyCode1_1_0\artifacts\`，不入库

## 1. 结论

真实 Electron + CDP 业务套件 **T01–T09 两批共 18 个任务全部验收通过**。确定性 Desktop CD 套件 **30 场景 × 3 轮共 90 条全部匹配期望终态**（`DESKTOP_CD_SUITE_OK`，exit 0，`error` 全空）。

Batch B 不是一次长会话跑完 9 项，而是同一会话策略下按失败项补跑：已通过项未重跑。套件门禁测试 `node --test scripts/real-business-suite.test.mts scripts/cdp-harness.test.mts` 为 **42 passed**。

## 2. 模型与隔离

| 项 | 值 |
|---|---|
| `REAL_BUSINESS_MODEL_ID` | `opencode-go/deepseek-v4-flash` |
| Provider | `opencode-go` |
| Gateway | `https://opencode.ai/zen/go/v1` |
| GUI | 真实 Electron + CDP，独立 debug 端口 / profile / data dir / workspace |
| T09 数据库 | 本机 MySQL 低权限用户，凭据只经 env 注入（`desktopSuiteEnv()` / `mysqlTestEnv()`） |
| T09 演示登录 | 独立演示口令 env，**不得**把 `MYSQL_ADMIN_PASSWORD` 当登录口令 |

## 3. 全量 18：分段真绿证据

### 3.1 Batch A（9 独立会话）

- 工件：`D:\agent-demo\RxyCode\RxyCode1_1_0\artifacts\rxycode-gui-real-e2e-full-18-A`
- `generated_at`：2026-08-15T23:19:24.031Z
- T01–T09：`status=succeeded`，`error=null`

### 3.2 Batch B（同一长会话策略，分段补跑）

| 任务 | 真绿工件 | 关键探针 / 产物 |
|---|---|---|
| T01, T02, T04, T05, T07 | `artifacts\rxycode-gui-real-e2e-full-18-B2` | `error=null` |
| T08, T09 | `artifacts\rxycode-gui-real-e2e-full-18-B2-retry3` | 见下 |
| T03, T06 | `artifacts\rxycode-gui-real-e2e-full-18-B2-retry4` | 见下 |

**不以 B2 的 T03/T06 计通过。** 该次 JSON 出现 `status=succeeded` 但 `error` 非空（T03 后台模块 1/5；T06 缺 CSV）。验收以 `error=null` 的补跑工件为准。

### 3.3 T03（retry4）

探针 `batch-B\probes\T03.rxy-play-probe.json`：

- `ok: true`
- `demoClicked: true`
- `navigated: true`
- `adminModules: 5`
- 后台文案含用户 / 订单 / 内容 / 设置 / 分析

产物含 `index.html`（`#btn-demo-login` 与 `#btn-demo-login-alt`）、`admin.html`、`PLAN.md`、`README.md`、`TEST-REPORT.md`。模型 Final Answer 曾误称 `#btn-demo-login` 未修；**以探针为准，不因此重跑。**

### 3.4 T06（retry4）

探针 `batch-B\probes\T06.rxy-play-probe.json`：

- `ok: true`
- 标题含黄金 / 白银 / 科创50 / 美股代理

磁盘上有 CSV（`assets_daily.csv` / `data.csv` 等）+ 交互 BI + `sources.md` / `README.md` / `TEST-REPORT.md`。

### 3.5 T08（retry3）

探针 `batch-B\probes\T08.rxy-play-probe.json`：

- `ok: true`
- 标题「珠江新城通勤租房决策」

产物含真实 `areas.csv`、`index.html` 示意地图 SVG、以及「合同与风险」条款（合同 / 解约 / 噪音 / 维修）。`error=null`。

### 3.6 T09（retry3）

- 5 个 Controller：Auth / Product / Inventory / Order / Revenue
- Flyway `V1__init.sql`：`users` / `products` / `inventory` / `orders` / `order_items`（另有 `user_roles`）
- `CoffeeShopApplicationTests.java` 使用 `mockMvc.perform`
- `TEST-REPORT.md` 引用：`Tests run: 3, Failures: 0, Errors: 0`
- 7 份文档：README / DEVELOPMENT / API / ARCHITECTURE / SECURITY / MIGRATION-ROLLBACK / TEST-REPORT
- 无 H2；解压了 `.tools/apache-maven-3.9.16`
- 缺 TEST-REPORT 时 harness 已观察到 `mvn test` 绿，补写文档后 `error=null`

## 4. 补跑中修过的套件行为（worktree）

1. `pendingToolPrep` 只匹配 `preparing write tool call`，避免 datetime/webfetch 吃掉 180s 预算。
2. 静默 30s 硬失败仅在 `first_event_ms` 为空或大于 30s 时触发。
3. 缺 CSV 触发补写：T06→`data.csv`，T08→`areas.csv`，T04→`budget.csv`，T07→`tco.csv`。
4. 看门狗停掉后仍 `copyTree`，并允许 1 次补文件（`runAbortedByWatchdog && attempt > 1` 才停）。
5. T03 空目录时强制补写站点与文档；已有站点不改写。
6. T03 prompt：skill 返回后下一工具必须 `write T03-company/PLAN.md`，禁止 ls/glob Electron Cache。
7. T06 prompt：webfetch 403 立刻写 CSV+index。
8. T08 prompt：磁盘上必须有真实 `.csv`。
9. T09 prompt：禁止 websearch/webfetch；第一工具必须 write `pom.xml`。
10. `terminalOutcomeIssue(status, finalAnswer, artifactOk)`：smoke/探针已过时，忽略 leftover Failed 徽章上的 `Tool write/edit did not complete`。

未放宽 15 分钟任务墙钟，未把 H2/SQLite/Python 当成 T09 替代，未藏元素刷绿。

## 5. 确定性 GUI 三轮

- 命令：`node scripts/desktop-cd-suite.mts --mode=deterministic --rounds=3`
- 工件：`D:\agent-demo\RxyCode\RxyCode1_1_0\artifacts\rxycode-gui-deterministic-3-2026-08-16`
- 耗时：约 130s；exit 0；`DESKTOP_CD_SUITE_OK`
- 90 条：`succeeded=81`，`cancelled=6`，`failed=3`，`error` 全空

`cancelled` / `failed` 是场景期望终态，不是套件失败：

| ID | kind | 期望终态 |
|---|---|---|
| DTS-12 | cancel | cancelled（三轮） |
| DTS-13 | failure | failed（三轮） |
| DTS-25 | child-cancel | cancelled（三轮） |

其余 DTS-01–11、14–24、26–30 三轮均为 `succeeded`。

## 6. 性能与诚实记录

下列为 **defect 记录，不是 `error` 硬失败**（工具活动可见时，first-token 超时不否掉研究任务）：

- Batch A：T04 / T06 / T07 的 `first_token` 超过 30s hard-fail 观察阈值（例如 T04 ≈205s，T06 ≈153s，T07 ≈127s）。
- Batch B 真绿项同样留下 8s/15s first-token 与部分静默间隔 defect。
- 验收标准仍是：产物可运行、探针 `ok`、`error=null`、墙钟硬失败未吞掉。

未宣称 first-token 全部进入 8s 目标。

## 7. 合入范围

合入本地 `master` 的是本分支上的 Desktop CDP harness / 真实业务 suite / 本报告，以及分支已有的 GUI e2e 修复。当前 Cursor 主工作区 `fix` 上的 `tools/websearch.py`、相关测试和 `diag_*.py` **不在本合入内**。
