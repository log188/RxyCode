# Phase 4 D6 交付记录：打包（Windows / macOS / Linux，含内嵌 Python 运行时）

> 仓库：`D:\agent-demo\RxyCode-Desktop`（RxyCode-master 未改动，schema.json 零改动）
> 执行日期：2026-08-08 · 执行人：Composer 2.5
> 依赖：D5 commit `34863e4`；RxyCode 保持 v1.2.6（`D:\agent-demo\RxyCode-master` 仅只读引用）
> 平台状态：**Windows 实测通过（本机）**；macOS/Linux 配置已备、构建待 CI/对应平台验证（本机为 Windows，无法真实执行，不谎报）

## 完成判据（验收 SOP）

- [x] 内嵌 Python 运行时自包含：打包产物内含 Python 解释器 + site-packages + vendored RxyCode 1.2.6（离线 `pip install --no-deps --no-build-isolation` 安装到运行时），**不依赖开发机 `../RxyCode-master`**（packaged-smoke 以 `RXYCODE_REPO_DIR=<不存在的路径>` 实测通过）
- [x] appserver 定位优先级：**包内运行时优先 > 开发模式 fallback**（`../RxyCode-master` / `RXYCODE_REPO_DIR`），由 `findBundledRuntime` + `buildSpawnSpec` 实现并有单测覆盖
- [x] 打包产物真实握手：`dist\win-unpacked\rxycode-desktop.exe`（SMOKE 模式）实际启动内嵌运行时 `python -m appserver`（stub）并完成 initialize 握手，`SMOKE_RESULT` 返回 `protocol_version=1.0.0`、`server_name=rxycode-appserver`，0 协议违规，无孤儿进程
- [x] Windows 实测硬验收：typecheck / lint / test（118 通过）/ `runtime:prepare` / `runtime:verify` / `electron-builder --win`（NSIS 安装器 + win-unpacked）/ 产物检查 / packaged-smoke 全部真实跑通，输出见下
- [x] macOS/Linux：electron-builder 三平台目标（mac: dmg、linux: AppImage/snap/deb）+ `prepare-runtime` 跨平台脚本（`bin/python3` 布局）已配置；**构建待 CI/对应平台验证**
- [x] DC1：Desktop 仍只走 `protocol-client`（现已打包进主进程 bundle），不 import Python / 不调 HTTP
- [x] DC5：打包版孤儿守护可用（`scripts/**` 加入 asarUnpack，guard 路径映射 `app.asar.unpacked`），打包 smoke 验证无孤儿进程
- [x] 协议零变化：`RxyCode-master/protocol/schema.json` 未改动（哈希 `222c18a…` 前后一致），RxyCode-master 工作区干净；`protocol-client` 未改动
- [x] 一张卡一个 commit，可单独 revert

## 改动文件清单

| 文件                                          | 改动                                                                                                                                                                                                                                                                                        |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/main/runtime.ts`（新增）                 | 内嵌运行时解析：manifest 读取/校验、`findBundledRuntime`（`resources/runtime/<platform>-<arch>/`）、`pythonExeName`                                                                                                                                                                         |
| `src/main/runtime.test.mts`（新增）           | 12 条测试：manifest 解析/缺失/损坏、平台与 arch 不匹配、python/appserver 缺失、完整运行时的路径解析、默认平台                                                                                                                                                                               |
| `src/main/appserver-runtime.test.mts`（新增） | 13 条测试：`buildSpawnSpec`（bundled 优先/dev fallback/fake/stub env/缺 repo 报错）、manager 懒解析、`runtimeLabel`、`repoRootDir`                                                                                                                                                          |
| `src/main/appserver.ts`                       | 导出 `buildSpawnSpec`（启动决策纯函数）；constructor 懒解析 dev repo（打包模式不抛错）；`bundledRuntime()` 优先；`runtimeLabel`；孤儿守护支持 `app.asar.unpacked` 路径                                                                                                                      |
| `src/main/index.ts`                           | `getManager` 不再急切 `findRepoRoot()`；smoke 从 `manager.repoRootDir` 读 schema；输出 `SMOKE_RUNTIME <bundled                                                                                                                                                                              | dev>` 标记 |
| `scripts/prepare-runtime.mts`（新增）         | 运行时制备：复制本地完整 Python（剪裁 debug/文档/无关依赖）+ vendored RxyCode 源码 + 离线 pip 安装 rxycode 1.2.6 + 自检（imports + stub 启动）+ manifest                                                                                                                                    |
| `scripts/verify-runtime.mts`（新增）          | 运行时校验：manifest/布局/python 版本/imports/协议版本                                                                                                                                                                                                                                      |
| `scripts/smoke-lib.mts`（新增）               | 共享 smoke 断言（从 smoke.mts 抽出，参数化 exe/cwd/env/expectedRuntime/schemaDir）                                                                                                                                                                                                          |
| `scripts/smoke.mts`                           | 改用 smoke-lib（开发态，`SMOKE_RUNTIME dev`）                                                                                                                                                                                                                                               |
| `scripts/packaged-smoke.mts`（新增）          | 打包产物 smoke：spawn win-unpacked exe，`RXYCODE_REPO_DIR` 指向不存在路径，断言 `SMOKE_RUNTIME bundled` + 握手 + 无孤儿                                                                                                                                                                     |
| `electron.vite.config.ts`                     | main 构建 `externalizeDeps: false`（把 TS 版 `protocol-client` 打进主进程 bundle——打包版无法在 asar 的 node_modules 下做类型剥离，实测发现并修复）                                                                                                                                          |
| `electron-builder.yml`                        | `extraResources` 打入 `build/runtime` → `resources/runtime`；`asarUnpack` 增加 `scripts/**`；`files` 排除 `node_modules`（全部已 bundle）；`electronDist` 指向本地 electron（离线可重复构建）；nsis/dmg/appImage artifactName 改为平铺文件名（`${name}` 含 `/` 会令 makensis 输出路径失败） |
| `package.json`                                | test 列表加入 2 个新测试文件；新增 `runtime:prepare` / `runtime:verify` / `packaged-smoke`；`build:win/mac/linux/unpack` 先制备运行时                                                                                                                                                       |
| `eslint.config.mjs`                           | ignores 增加 `**/build/runtime`（vendored 前端 TS 不进 lint）                                                                                                                                                                                                                               |
| `.gitignore`                                  | 增加 `build/runtime/`（运行时产物不入库）                                                                                                                                                                                                                                                   |
| `README.md`                                   | 命令说明：运行时制备/校验、三平台构建、packaged-smoke；平台状态标注                                                                                                                                                                                                                         |
| `docs/phase4-d6-delivery.md`（本文件）        | 交付记录                                                                                                                                                                                                                                                                                    |

## 命令与真实输出

### typecheck

```
> tsc --noEmit -p tsconfig.node.json --composite false
> tsc --noEmit -p tsconfig.web.json --composite false
（退出码 0，无错误）
```

### lint

```
> eslint --cache .
（退出码 0，无问题）
```

### test

```
ℹ tests 118
ℹ suites 0
ℹ pass 118
ℹ fail 0
（退出码 0）
```

### runtime:prepare（Windows 实测）

```
RUNTIME_PREPARE_START platform=win32 arch=x64 out=D:\agent-demo\RxyCode-Desktop\build\runtime\win32-x64
RUNTIME_PREPARE_OK out=D:\agent-demo\RxyCode-Desktop\build\runtime\win32-x64 pythonVersion=3.14.2 rxycodeVersion=1.2.6 protocolVersion=1.0.0 totalBytes=274541237
（退出码 0）
```

制备过程含：复制本地 Python（`D:\python`，完整安装，剪裁 debug/`Doc`/`libs`/`include`/`share`/`Lib\test`/`idlelib`/`turtledemo`/`venv`/`scipy`/`pandas`/`matplotlib`/`coverage`/`pytest`/`ruff`/editable 痕迹/PDB）、复制 vendored RxyCode 源码（排除 `.git`/`docs`/`tests`/`__pycache__`/egg-info/log 数据文件）、离线 `python -m pip install --no-deps --no-build-isolation <repo>`（`PIP_NO_INDEX=1`）、自检 `import appserver` + 全部 requirements imports + `RXYCODE_APPSERVER_STUB=1 python -m appserver`（stdin EOF 正常退出）。

### runtime:verify

```
RUNTIME_VERIFY_OK dir=D:\agent-demo\RxyCode-Desktop\build\runtime\win32-x64 Python 3.14.2 rxycodeVersion=1.2.6 protocolVersion=1.0.0 createdAt=2026-08-08T11:18:50.185Z
（退出码 0）
```

### build（Windows 实测：electron-builder --win）

```
• electron-builder  version=26.15.3 os=10.0.26100
• packaging       platform=win32 arch=x64 electron=39.8.10 appOutDir=dist\win-unpacked
• using custom unpacked Electron distribution  electronDist=node_modules\electron\dist
• building        target=nsis file=dist\rxycode-desktop-0.1.0-setup.exe archs=x64 oneClick=true perMachine=false
• building block map  blockMapFile=dist\rxycode-desktop-0.1.0-setup.exe.blockmap
（退出码 0）
```

产物：`dist\rxycode-desktop-0.1.0-setup.exe`（159.6 MB）、`dist\win-unpacked\`（app.asar 1.7 MB，内嵌运行时 `resources\runtime\win32-x64\` 261.8 MB，guard 脚本 `app.asar.unpacked\scripts\`）。

### packaged-smoke（打包产物真实握手，Windows 实测）

```
SMOKE_RUNTIME bundled
SMOKE_CHILD_PID 35700
SMOKE_RESULT {"protocol_version":"1.0.0","server_name":"rxycode-appserver","capabilities":{"sessions":true,"approval":true}}
SMOKE_VIOLATIONS 0
SMOKE_DONE
SMOKE_OK child pid 35700 exited, no orphan process left
（退出码 0）
```

说明：spawn 的是打包后的 `dist\win-unpacked\rxycode-desktop.exe`，环境带 `RXYCODE_DESKTOP_SMOKE=1` 与 `RXYCODE_REPO_DIR=<不存在的路径>`，cwd 为系统临时目录——`SMOKE_RUNTIME bundled` 证明 appserver 来自包内运行时（优先于开发 fallback），握手成功且零协议违规、无孤儿进程。

### 开发态 smoke（回归，重构后）

```
SMOKE_RUNTIME dev
SMOKE_CHILD_PID 44748
SMOKE_RESULT {"protocol_version":"1.0.0","server_name":"rxycode-appserver","capabilities":{"sessions":true,"approval":true}}
SMOKE_VIOLATIONS 0
SMOKE_DONE
SMOKE_OK child pid 44748 exited, no orphan process left
（退出码 0）
```

### 禁改边界检查

```
git -C RxyCode-master status --porcelain        # 无输出（工作区干净）
git -C RxyCode-master rev-parse HEAD            # 3b8807470ddc09fbebe0e9e2cf7bdc3204cacf83（前后一致）
git -C RxyCode-master hash-object protocol/schema.json  # 222c18a81e87e2a73c96d689f41631dfa1a21a59（前后一致）
```

### 提交前最终复验（2026-08-08，重建后全链重跑）

```
> npm run build        # typecheck + electron-vite build
vite v7.3.6 building ssr environment for production...
out/main/index.js  24.26 kB
out/preload/index.js  3.80 kB
out/renderer/index.html + assets/index-D7oDsng8.js 607.00 kB
（退出码 0）

> npm test             # 118/118 通过
ℹ tests 118
ℹ pass 118
ℹ fail 0
ℹ duration_ms 6429.2758
（退出码 0）

> npm run lint         # eslint --cache .
（退出码 0，无问题）

> npx prettier --check <本次改动的 16 个文件>   # All matched files use Prettier code style!
（退出码 0）

> npm run runtime:verify
RUNTIME_VERIFY_OK dir=D:\agent-demo\RxyCode-Desktop\build\runtime\win32-x64 Python 3.14.2 rxycodeVersion=1.2.6 protocolVersion=1.0.0 createdAt=2026-08-08T11:18:50.185Z
（退出码 0）

> npm run packaged-smoke   # 最终打包产物（重建后 electron-builder --win 重打包）
SMOKE_RUNTIME bundled
SMOKE_CHILD_PID 35700
SMOKE_RESULT {"protocol_version":"1.0.0","server_name":"rxycode-appserver","capabilities":{"sessions":true,"approval":true}}
SMOKE_VIOLATIONS 0
SMOKE_DONE
SMOKE_OK child pid 35700 exited, no orphan process left
（退出码 0）

> dist\rxycode-desktop-0.1.0-setup.exe = 167,392,883 bytes（159.6 MB）
> bundle 编码检查：out/main/index.js 中文文案完整（打开/取消/打开外部链接/是否在浏览器中打开此链接），无 BOM、无 U+FFFD
> 全部改动文件扫描：17 个文件无 BOM、无 replacement char
```

## 协议是否变化

**否**。`RxyCode-master/protocol/schema.json` 未改动（哈希不变），JSON-RPC 方法/事件未新增；`protocol-client` 源码未改动（构建方式从外部 require 改为打进主进程 bundle，属桌面端构建配置，非协议变化）。

## 已知限制

1. **macOS/Linux 构建未在本机执行**：本机为 Windows，`prepare-runtime` 已按 `bin/python3` 布局与三平台 electron-builder 目标写好，但构建与握手验证需在 CI / 对应平台执行（D8 接入）。交付不谎报已实测。
2. **NSIS 首次构建需要网络**（electron-builder 下载 NSIS/winCodeSign 工具链）；electron 本体已配置 `electronDist` 指向本地，离线可重复。本机首次构建曾因 GitHub 网络抖动失败，重试通过。
3. **代码签名未配置证书**：electron-builder 以 signtool 处理资源但未签名（无证书）；签名/公证入口属 D7/D8。
4. 运行时体积约 262 MB（完整 Python 3.14.2 + 全部 requirements 依赖 + vendored RxyCode），安装包 159.6 MB；后续可裁剪（如按需依赖、排除 `pip`/`setuptools`）。
5. 会话/工作区持久化数据仍由 appserver 在 vendored `app/` 目录（安装目录）内写入的路径待 D7+ 收口（本次握手路径不落盘）；安装目录可能不可写，属后续卡范围。
6. 打包版 smoke 依赖 `--disable-gpu`（D3 已验证等效）；真实 GUI 交互（安装/启动/升级）验证待 D7/D8。

## 回滚方式

单 commit 可直接回滚：

```powershell
git revert <D6 commit>
```

或

```powershell
git checkout <D6 commit>~1 -- <受影响的文件>
```

回滚不影响 `RxyCode-master`（未触碰）；协议无变化，回滚后无需重新生成类型；`build/runtime` 与 `dist` 均为 gitignore 产物，可删除后重建。
