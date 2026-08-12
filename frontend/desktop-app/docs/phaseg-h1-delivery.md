# Phase G · H1 交付记录（Desktop 基线与前端包边界）

> 卡片：PhaseG-H1 · Desktop 基线与前端包边界（P0 / 1–2d / 无依赖 / owner: Composer 2.5 → 本记录由前端执行者完成）
> 基线：`xin-yi33/RxyCode` master `57d55d7`（2026-08-10，D5 已上线）
> 分支：`feat/phase-g-frontend`（总手册 §4.1）
> 日期：2026-08-12

## 完成判据

- [x] Desktop 入口、Renderer、Main、preload 和 protocol-client 目录边界已记录（见下）
- [x] 生成类型来源和 schema 版本已记录
- [x] 没有 renderer → Python/HTTP 直连（实测扫描）
- [x] 已提交可独立回滚 commit（本 commit 仅含本交付记录，`git revert` 即可回滚）

## 目录边界记录

| 路径 | 职责 | Owner |
|---|---|---|
| `frontend/desktop-app/` | Electron 桌面壳（electron-vite + electron-builder） | 前端 |
| `frontend/desktop-app/src/main/` | 主进程：appserver 监督、runtime 查找、auto-update、crash-report、navigation 白名单、workspace-dialog、kill-tree/孤儿守卫 | 前端 |
| `frontend/desktop-app/src/preload/` | contextBridge 桥（contextIsolation=true / nodeIntegration=false / sandbox=true，IPC allowlist） | 前端 |
| `frontend/desktop-app/src/platform/` | 平台能力适配层（DC3 隔离） | 前端 |
| `frontend/desktop-app/src/renderer/` | React UI：App、components、hooks、lib | 前端 |
| `frontend/desktop-app/scripts/` | smoke / 截图 / 打包脚本 | 前端 |
| `frontend/protocol-client/` | 协议客户端（client.ts、index.ts、src/generated/） | 前端（生成产物由后端生成提交） |
| `protocol/schema.json` | 协议 schema | 后端独占（前端只读） |
| `appserver/` | appserver 后端 | 后端独占 |

## 协议与生成类型

- schema：`protocol/schema.json`，`protocol_version = 1.0.0`
- 生成类型：`frontend/protocol-client/src/generated/types.ts`（17,289 B）+ `subagent-types.ts`（6,839 B）
- 生成方式：后端在协议变更时执行 `cd frontend/protocol-client && bun run generate`（json2ts），生成产物随协议 PR 提交；前端只读消费，禁止提交生成差异
- 本卡协议变化：none

## 验收命令与真实输出（2026-08-12 本机实测）

| 命令 | 结果 |
|---|---|
| `Test-Path frontend\desktop-app` | True |
| `Test-Path frontend\protocol-client` | True |
| `npm.cmd run typecheck` | 退出码 0，两段 tsc 均通过 |
| `npm.cmd test` | tests 136 / pass 136 / fail 0（14 个测试文件，含 kill-tree 真实 taskkill） |
| `python -m pytest tests/test_protocol_schema.py tests/test_question_protocol.py tests/contract -q` | **529 passed**（13.75s，1 warning 为 fastapi 弃用提示） |
| renderer 直连扫描（`fetch(` / `http(s)://`） | 无命中；`src/renderer/index.html` 仅有 CSP 注释里的示例 URL |

## 与文档不一致项（按总手册 §6 纪律如实报告）

1. **验收路径过时**：H1 卡验收命令写的 `python -m pytest tests/test_protocol -q` 中 `tests/test_protocol` 目录在仓库不存在。实际协议测试位于 `tests/test_protocol_schema.py`、`tests/test_question_protocol.py`、`tests/contract`，合计 529 通过。建议负责人更新 H1 卡的验收路径。
2. **工作目录路径差异**：前端文档 §0.3 示例为 `D:\agent-demo\RxyCode\RxyCode1_1_0`；本机实际使用 `D:\agent-demo\RxyCode-master`（已与 GitHub master `57d55d7` 对齐，工作区 clean）。不影响执行，仅记录。

## 已知限制

- `bun` 未安装：`frontend/protocol-client` 的 `test` / `generate` 脚本依赖 bun（H2 起需要；可安装 bun 或按等价方式验证）。
- 本卡为检查/记录卡，无功能代码改动；H1 的"壳不存在则 BLOCKED_PREREQUISITE"未触发（壳存在且验收全绿）。

## 回滚方式

`git revert <本 commit>`；因本 commit 仅新增 `docs/phaseg-h1-delivery.md`，回滚即删除该文件，无其他影响。

## 改动文件

- `frontend/desktop-app/docs/phaseg-h1-delivery.md`（新增）
