# RxyCode v1.2.10

RxyCode 是一个规划执行型的 AI 编程助手：把复杂任务自动拆解成子任务，通过安全工具编排器执行、验证结果后综合出最终答案，全程实时流式输出到终端或桌面界面。
> **推荐使用 v1.2.10。** 本版交付 Desktop GUI：`rxycode gui` 打开 Electron 应用，带 Codex 风格计划模式、常驻目标、计划卡片（实施 / 补充说明 / 跳过）和 Composer `+` 菜单。默认 CLI 不变：在 cmd（或任意终端）里输入 `rxycode` 就是 OpenTUI。

## 简要说明 / Summary

这一版是**桌面 GUI 版**：在保留 OpenTUI 的前提下，补齐真实可用的 Electron 应用。
- 新增：`rxycode gui` Desktop 应用（聊天、Composer、审批、设置）
- 新增：Plan 模式、Goal 对话框、计划卡片（实施 / 补充说明 / 跳过）
- 新增：Composer `+` 菜单（文件和文件夹、在项目中使用、目标、计划模式）
- 修复：Goal / 完全访问确认可用 Escape 关闭；附件路径写入 prompt
- 变更：产品版本 **1.2.10**；协议版本仍为 `1.1.0`

## 亮点 / Highlights

- **默认 CLI 仍是 OpenTUI** —— 在 cmd 里输入 `rxycode` 即可进入；不需要额外 launcher
- **桌面 GUI 可日常使用** —— `rxycode gui` 启动 Electron 应用，后端自动拉起 `python -m appserver`
- **先计划再动手** —— Plan 模式让 Agent 停在计划文档上；计划卡片提供实施、补充说明、跳过
- **常驻目标** —— Goal 对话框保存本会话目标；Escape 或点遮罩关闭
- **Composer `+` 菜单** —— 附加文件、选择工作区、设置目标、切换计划模式
- **危险操作会问你** —— 默认权限「更改前询问」；完全访问有二次确认

## 详细说明 / Details

### 新增功能

- **Desktop Plan / Goal / workspace** —— Plan 模式保持 Agent 在计划文档上；Goal 对话框保存常驻目标；计划卡片提供 `实施`、`补充说明`、`跳过`（`frontend/desktop-app/src/renderer/src/components/`）
- **Composer `+` 菜单** —— `文件和文件夹`、`在项目中使用`、`目标`、`计划模式`（`ComposerPlusMenu.tsx`）
- **三平台打包** —— Windows `setup.exe` + 便携 zip、macOS `.dmg`、Linux `.AppImage`；Windows 安装器默认目录 `%USERPROFILE%\.rxycode\desktop`，可浏览自定义路径

### 修复的 Bug

- **Goal 对话框关不掉** —— 现在 Escape 和点击遮罩都会关闭
- **完全访问确认关不掉** —— Escape 可取消
- **附件路径丢失** —— 选中的文件路径会写入 prompt（`promptWithAttachment`）
- **权限标签** —— Desktop UI 使用中文：更改前询问 / 自动编辑 / 完全访问
- **Windows 终端鼠标乱码** —— 关掉全量移动追踪（SGR 1003），保留点击、滚轮、框选和边界自动滚
- **首次打开很慢 / 首击无反馈** —— 进程启动即预热 Agent；首击立刻显示「收到，正在回复…」
- **工具后 FirstTokenTimeout** —— 用户正式请求会取消后台预热，避免和模型连接抢槽
- **回复被整段叠在第一块** —— 工具之后的正文新开一段，和工具调用穿插显示
- **便携 zip 找不到 exe** —— `rxycode gui` 能识别包装目录及其父目录
- **捆绑 rxycode 指向 CI 路径** —— 打包后改为可搬迁启动器（含相对路径 `rxycode.cmd`）
- **`rxycode --api` 写进安装包** —— 文件写入调用方工作区，不再 `chdir` 到 site-packages

### 变更

- 产品版本 **1.2.10**：`pyproject.toml`、安装脚本、OpenTUI/Ink 头部、MCP `clientInfo`、Desktop 设置页「当前版本」
- 协议版本保持 `1.1.0`（`protocol/version.py`）
- Windows 安装器为向导式：默认目录可改、桌面快捷方式默认可取消、界面语言跟随系统

## 安装 / Install

**CLI / OpenTUI（不含 Electron）：** 下面三步只装终端。装完输入 `rxycode`。**不要**指望这时 `rxycode gui` 能打开——CLI 包里没有桌面程序。

```powershell
# Windows
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/xin-yi33/RxyCode/v1.2.10/install.ps1 | iex"
rxycode
```

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/xin-yi33/RxyCode/v1.2.10/install.sh | sh
rxycode
```

```bash
uv tool install --force "git+https://github.com/xin-yi33/RxyCode.git@v1.2.10"
rxycode
```

**桌面 GUI（需另下本页 Desktop 资产）：**

| 系统 | 怎么开 |
|------|--------|
| Windows | 运行 `rxycode-desktop-1.2.10-setup.exe`，或解压 `RxyCode.Desktop-1.2.10-win.zip` 后运行 `rxycode-desktop.exe` |
| macOS | 打开 `.dmg`，把 **RxyCode Desktop** 拖进 Applications（未签名，首次请右键打开） |
| Linux | `chmod +x rxycode-desktop-1.2.10.AppImage && ./rxycode-desktop-1.2.10.AppImage`。没有 FUSE 时加 `APPIMAGE_EXTRACT_AND_RUN=1` |

装到 `~/.rxycode/desktop`（或设置 `RXYCODE_DESKTOP_DIR` / `--desktop-dir`）之后，**已经有 Desktop 的机器**才可以用 `rxycode gui` 当启动器。

**下载策略：** 仅本页（v1.2.10）提供 wheel / sdist 与桌面打包产物。更早版本的 GitHub Release **不开放**安装包下载（v1.2.9 及更早仅 wheel / sdist）。

## 资产 / Assets

- `rxycode-1.2.10-py3-none-any.whl`
- `rxycode-1.2.10.tar.gz`
- `rxycode-desktop-1.2.10-setup.exe`（Windows 安装版）
- `RxyCode.Desktop-1.2.10-win.zip`（Windows 便携版；解压后是 `RxyCode.Desktop-1.2.10-win/rxycode-desktop.exe`）
- `RxyCode.Desktop-1.2.10-arm64-mac.zip`（macOS Apple Silicon 便携包）
- `rxycode-desktop-1.2.10.dmg`（macOS，未签名）
- `rxycode-desktop-1.2.10.AppImage`（Linux）
