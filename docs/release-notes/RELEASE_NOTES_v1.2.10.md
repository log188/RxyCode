# RxyCode v1.2.10

RxyCode 是一个规划-执行型的 AI 编码代理，把复杂任务拆解为子任务，通过安全工具编排执行、验证并综合出最终答案，全部实时流式渲染。**v1.2.10 是桌面 GUI 版本**：`rxycode gui` 进入 Electron 桌面应用，同时保留 OpenTUI 终端界面与 CLI。

> **推荐使用 v1.2.10：** 本版交付桌面端 GUI（Plan 模式、Goal 对话框、Composer `+` 菜单、审批弹窗、设置页），`rxycode gui` 命令，以及 Windows / macOS / Linux 三平台打包产物——Windows 提供自定义路径安装版（默认 `~/.rxycode/desktop`，可浏览选择目录、桌面快捷方式默认开启可取消）与便携 zip。

## 主要说明 / Summary

- **桌面 GUI**：`rxycode gui` 启动 Electron 应用，Chat 会话列表 + 消息流 + Composer。
- **Plan / Goal / workspace 流程**：Plan 模式让 agent 停留在计划文档上；Goal 对话框保存常驻目标；计划卡片提供 Build / Revise / Skip。
- **Composer `+` 菜单**：附加文件、选择工作区、设置目标、切换计划模式。
- **审批与设置**：写操作触发审批弹窗，权限标签（每次询问 / 自动编辑 / 完全信任），设置页含更新与诊断、关于。
- **CLI real-business harness**：`frontend/desktop-app/scripts/real-business-cli-harness.mts` 通过 stdio JSON-RPC 直连 `python -m appserver`。
- 本地 GUI/CLI real-business 套件 **T01–T08** 通过，**T09 skipped**。协议版本保持 `1.1.0`。

## 亮点 / Highlights

- **桌面 GUI（Electron + React）**：`rxycode gui` 一键启动，后端 `python -m appserver` 作为子进程自动启动，双击桌面快捷方式即可进入。
- **Windows 安装器**：自定义 NSIS 安装向导——默认安装到 `%USERPROFILE%\.rxycode\desktop`，支持**浏览**自定义目录，桌面快捷方式默认勾选可取消；安装界面语言跟随系统（中文系统显示中文，其他语言显示英文）。
- **三平台交付**：Windows `setup.exe` + 便携 zip、macOS `.dmg`、Linux `.AppImage`。
- **Plan / Goal**：Codex 风格计划与目标流程，agent 在动手前先产出计划文档。
- **CLI 与 GUI 双界面**：README 展示 CLI 与 GUI 演示（`docs/images/cli-demo-cover.png` 与多张 `gui-*.png`）。

## 详细说明 / Details

### 新增功能

- **Desktop Plan / Goal / workspace flows**：Plan 模式保持 agent 在计划文档上；Goal 对话框保存常驻目标；计划卡片提供 `实施`、`补充说明`、`跳过`（`frontend/desktop-app/src/renderer/src/components/`）。
- **Composer `+` 菜单**：`附加文件` / `切换工作区` / `目标` / `计划模式`（`ComposerPlusMenu.tsx`）。
- **CLI real-business harness**：stdio JSON-RPC 客户端，启动 `python -m appserver` 创建工作区会话并通过 ProtocolClient 提问（`real-business-cli-harness.mts`）。
- **三平台打包**：`electron-builder.yml` 配置 win（nsis + zip）、mac（dmg）、linux（AppImage）；`prepare-runtime.mts` 支持 win32 / darwin / linux 运行时就绪布局。

### 修复

- Goal 对话框 Escape / 点击遮罩关闭。
- 完全信任确认 Escape 关闭。
- 附件文件路径写入 prompt（`promptWithAttachment`）。
- Desktop UI 权限标签为中文：每次询问 / 自动编辑 / 完全信任。

### 变更

- 产品版本 **1.2.10**：`pyproject.toml`、安装脚本、OpenTUI/Ink 头部、MCP `clientInfo`、Desktop 设置页。协议版本保持 `1.1.0`。
- Windows 安装器升级为向导式（`oneClick: false`）：默认目录 `~/.rxycode/desktop`、可浏览自定义、快捷方式勾选、中英文自适应。

### 验证

- Desktop `npm run typecheck` 通过，`npm test` 通过（新增 `prepare-runtime.test.mts` 三平台运行时就绪 4/4）。
- 已知基线：`real-business-suite.test.mts` 的 CSS 几何契约用例（`.composer` flex 规则）在 v1.2.10 仍为失败——与本次发布改动无关，后续 GUI 收尾时更新。

## 安装 / Install

**推荐（v1.2.10）：**

```powershell
# Windows
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/xin-yi33/RxyCode/v1.2.10/install.ps1 | iex"
```

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/xin-yi33/RxyCode/v1.2.10/install.sh | sh
```

```bash
uv tool install --force "git+https://github.com/xin-yi33/RxyCode.git@v1.2.10"
```

**启动桌面 GUI：**

```bash
rxycode gui
```

**下载策略：** 仅本页（v1.2.10）提供 wheel / sdist 与桌面打包产物。更早版本的 GitHub Release 保持原下载通道不变（v1.2.9 及更早仅 wheel / sdist）。

## 资产 / Assets

- `rxycode-1.2.10-py3-none-any.whl`
- `rxycode-1.2.10.tar.gz`
- `rxycode-desktop-1.2.10-setup.exe`（Windows 安装版）
- `rxycode-desktop-1.2.10-win.zip`（Windows 便携版）
- `rxycode-desktop-1.2.10.dmg`（macOS，未签名）
- `rxycode-desktop-1.2.10.AppImage`（Linux）