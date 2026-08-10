# Phase 4 D8 交付记录：Desktop 进 CI（typecheck + 单测 + 三平台构建产物）

> 仓库：`D:\agent-demo\RxyCode-Desktop`（RxyCode-master 未改动，schema.json / protocol-client 零改动）
> 执行日期：2026-08-09 · 执行人：Composer 2.5
> 依赖：D6 commit `90d2775`（三平台构建配置）、D7 commit `9ec0848`
> 平台状态：**Windows 本地实测通过（本机）**；ubuntu / macOS / Linux 构建的 **CI 实跑待推到远程后验证**（本机为 Windows，不谎报）

## 完成判据（验收 SOP）

- [x] 新增 `.github/workflows/ci.yml`（GitHub Actions）：`push / pull_request / workflow_dispatch` 触发
- [x] `test` job（ubuntu-latest）：`npm run typecheck` + `npm test`（136/136），Node 24、Python 3.14（setup-python）
- [x] `build` job（matrix：windows-latest / macos-latest / ubuntu-latest）：沿用 D6 的 `build:win / build:mac / build:linux`，产物 `upload-artifact`
- [x] 无 `continue-on-error`（R8）
- [x] RxyCode-master 只读引用：checkout 到与本地一致的 `../RxyCode-master` 平级目录；test 用 `PYTHONPATH` 解析 appserver、build 用 `RXYCODE_REPO_DIR`，**任何 job 不修改 master checkout**
- [x] Node 版本与本地一致（本地 `v24.14.0`，CI `NODE_VERSION: "24"`）
- [x] CI 解释器来源 = setup-python；prepare-runtime 适配点：build job 先 `pip install -r requirements.txt` + `setuptools wheel`（本地 D6 的 `D:\python` 自带这些包并随 site-packages 复制进运行时；CI 全新解释器需补装，否则离线 `pip install --no-deps --no-build-isolation` 会缺构建后端）。若首次 CI 实跑仍失败，如实标注「待适配」，不谎报
- [x] Windows 本地实测全部真实跑通并贴输出：`typecheck` / `lint`（sanity）/ `test`（136/136，非沙箱）/ workflow YAML 解析 / `build:win`（NSIS + win-unpacked + 内嵌运行时）
- [x] CI 实跑（ubuntu/macos/linux 构建 + snap/AppImage/dmg）**待推到远程后验证**；workflow 里 `RXYCODE_MASTER_REPO: <org>/RxyCode-master` 为占位符，**推到远程前必须填**
- [x] 边界：只新增 `.github/workflows/ci.yml` + `docs/phase4-d8-delivery.md` + README 说明；`electron-builder.yml` / `src/` / `scripts/` / `protocol-client` 零改动
- [x] 一张卡一个 commit，可单独 revert

## 改动文件清单

| 文件                                   | 改动                                                                            |
| -------------------------------------- | ------------------------------------------------------------------------------- |
| `.github/workflows/ci.yml`（新增）     | Desktop CI：`test` job（typecheck + 单测）+ `build` job（三平台矩阵，产物上传） |
| `docs/phase4-d8-delivery.md`（本文件） | 交付记录                                                                        |
| `README.md`                            | 新增 CI 说明段                                                                  |

## CI 工作流设计说明

- **只读 backend 引用**：workflow 用 `actions/checkout` 把 `RXYCODE_MASTER_REPO` checkout 为 `../RxyCode-master`（与本地布局一致，`appserver.integration` 测试与 `prepare-runtime` 的默认解析路径均命中）。test job 用 `PYTHONPATH` + `requirements.txt` 让 `python -m appserver`（stub 模式）可导入，**不安装、不写回 master**；build job 用 `RXYCODE_REPO_DIR` 让 `prepare-runtime` 只读 vendor 源码。
- **prepare-runtime 在 CI 的输入**：setup-python 提供全新解释器；build job 先把 RxyCode 的 `requirements.txt`（覆盖 staged 运行时 verify 的全部 import：pydantic/fastapi/uvicorn/langchain/langgraph/…）与 `setuptools wheel`（`--no-build-isolation` 的构建后端，pyproject 声明 `setuptools>=69` + `wheel`）装进该解释器，`prepare-runtime` 复制 site-packages 后即可离线完成 vendored 安装。此路径 Windows 本机已用等价输入验证；CI 上属首次实跑，失败则标注「待适配」。
- **三平台构建**：完全复用 D6 的 `build:win / build:mac / build:linux` 脚本与 `electron-builder.yml`，D8 不改打包配置。matrix job 各自在本平台 runner 上构建对应产物并上传。
- **已知 CI 实跑风险（如实标注，本地无法验证）**：
  - ubuntu job 的 `snap` 目标需要 snapcraft，workflow 里用 `sudo snap install snapcraft --classic` 预装；若 runner 行为变化导致失败，属 CI 实跑待适配项。
  - macos job 未签名，已设 `CSC_IDENTITY_AUTO_DISCOVERY: "false"`。
  - `RXYCODE_MASTER_REPO` 占位符未填时，checkout 步骤会如实失败（不会静默跳过）。

## 命令与真实输出

### typecheck（沙箱内，退出码 0）

```
> npm run typecheck
> npm run typecheck:node
> tsc --noEmit -p tsconfig.node.json --composite false
> npm run typecheck:web
> tsc --noEmit -p tsconfig.web.json --composite false
（无错误输出，退出码 0）
```

### lint（沙箱内 sanity，退出码 0）

```
> npm run lint
> eslint --cache .
（无问题输出，退出码 0）
```

### test（非沙箱，136/136）

```
> npm test
ℹ tests 136
ℹ suites 0
ℹ pass 136
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 5609.3059
（退出码 0）
```

> 说明：kill-tree 测试在**沙箱内**会失败（`taskkill` 报 `ERROR: Access denied`，沙箱禁止跨进程终止，手工复现确认；非代码回归）；按「进程类命令非沙箱」规则在非沙箱复跑后 136/136 全绿。

### workflow YAML 解析校验（沙箱内，退出码 0）

```
> python -c "import yaml,pathlib; d=yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text(encoding='utf-8')); print('yaml ok, jobs =', list(d['jobs'].keys()))"
yaml ok, jobs = ['test', 'build']
```

### build:win（非沙箱，退出码 0；354s）

```
> npm run build:win
> npm run build && npm run runtime:prepare && electron-builder --win
> npm run build
> npm run typecheck && electron-vite build
（tsc 无错误；vite 产出 out/main 604.04 kB / out/preload 4.88 kB / out/renderer assets 614.93 kB）

> npm run runtime:prepare
> node scripts/prepare-runtime.mts
RUNTIME_PREPARE_START platform=win32 arch=x64 out=D:\agent-demo\RxyCode-Desktop\build\runtime\win32-x64
RUNTIME_PREPARE_OK out=D:\agent-demo\RxyCode-Desktop\build\runtime\win32-x64 pythonVersion=3.14.2 rxycodeVersion=1.2.6 protocolVersion=1.0.0 totalBytes=278926893

> electron-builder --win
• electron-builder  version=26.15.3 os=10.0.26100
• packaging       platform=win32 arch=x64 electron=39.8.10 appOutDir=dist\win-unpacked
• building        target=nsis file=dist\rxycode-desktop-0.1.0-setup.exe archs=x64 oneClick=true perMachine=false
• building block map  blockMapFile=dist\rxycode-desktop-0.1.0-setup.exe.blockmap
（退出码 0）
```

产物核对：

```
dist\rxycode-desktop-0.1.0-setup.exe         168702611 bytes
dist\rxycode-desktop-0.1.0-setup.exe.blockmap
dist\win-unpacked\rxycode-desktop.exe        210983936 bytes
build\runtime\win32-x64\manifest.json        （pythonVersion 3.14.2 / rxycodeVersion 1.2.6）
```

## 推到远程前必填 / 必查

1. 把 `.github/workflows/ci.yml` 顶部 `RXYCODE_MASTER_REPO: <org>/RxyCode-master` 换成真实 backend 仓库位置（例如 `xin-yi33/RxyCode`，分支已固定 `ref: main`）。
2. 推送到 GitHub 后观察：`test` job 绿；`build` job 三个平台绿（首次实跑，风险见上）。
3. 若 ubuntu/macos 构建失败：按「待适配」如实记录到本卡，不谎报。

## 禁改边界检查

```
git -C RxyCode-master status --porcelain        # 无输出（工作区干净）
git -C RxyCode-master rev-parse HEAD            # 3b8807470ddc09fbebe0e9e2cf7bdc3204cacf83（前后一致）
git -C RxyCode-master hash-object protocol/schema.json  # 222c18a81e87e2a73c96d689f41631dfa1a21a59（前后一致）
git diff --stat                                 # 仅 D8 三个文件
```

## Commit

```
ci(desktop): run typecheck, unit tests and three-platform builds in CI

The desktop app had no CI at all: typecheck, the 136 unit tests and the
D6 packaging scripts were only ever verified on the Windows dev machine.
The workflow checks out the backend repo read-only as ../RxyCode-master
(matching the local layout) and runs tests on ubuntu plus one build job
per platform; Windows is verified locally, macOS/Linux need a real CI run
after the RXYCODE_MASTER_REPO placeholder is filled in.
```
