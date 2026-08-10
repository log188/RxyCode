# RxyCode v1.2.9

RxyCode 是一个规划执行型的 AI 编程助手：把复杂任务自动拆解成子任务，通过安全工具编排器执行、验证结果后综合出最终答案，全程实时流式输出到终端界面。
> **推荐使用 v1.2.9。** 本版完成 Phase C isolated subagent runtime 的真实执行桥接：子代理不再把“收到任务”伪装成完成，而是创建独立 AgentV2/session，经过子代理权限与 workspace 边界执行真实模型和工具调用，并将 token、证据、产物、取消和结构化错误回传给 Primary。

## 简要说明 / Summary

这一版是**子代理真实执行版**：补齐 Phase C 从生命周期骨架到真实 AgentV2/provider/tool loop 的桥接，并用高难并发压力测试验证失败边界。
- 新增：ChildRuntime → 独立 AgentV2/provider/tool 执行桥接
- 新增：子代理 session、权限、workspace、audit、usage 和 telemetry 关联
- 修复：placeholder `Task received` 不再被标记为 `completed`
- 修复：parent cancel 可穿透到 active child AgentV2
- 新增：子代理 execution bridge 契约测试和 Phase 4 高难压力测试
- 验证：530 passed / 1 skipped；真实 16-case 并发压力测试完成

## 亮点 / Highlights

- **子代理真正开始执行任务** —— 每个 Child 创建独立 AgentV2 并绑定独立 session，不持有 Primary history 或 Primary 可变运行状态
- **统一权限和工具边界** —— read/edit/bash 等调用在进入 AgentV2 的 ToolOrchestrator 前经过 Child permission/workspace guard；MCP/Skill 继续作为受控 capability，不允许旁路执行
- **拒绝假成功** —— 没有真实 provider/tool 执行能力时返回结构化 `runtime_not_implemented`/`failed`，不再返回固定文本却标成 `completed`
- **取消真正可达** —— parent cancel 同时取消 Child CancellationToken 和 active AgentV2；取消专项 S2/S3 约 52 秒内进入 `cancelled`
- **证据和 token 可追踪** —— TaskResult 增加向后兼容 telemetry，回传 tool calls、evidence、artifacts、MCP/Skill 调用和 Child-local token/wall time
- **压力测试先发现再修复** —— 16 个高难 product/arch case，最高 6 个 child 并发，真实模型消耗 1,581,135 tokens

## 详细说明 / Details

### 新增功能

- **ChildRuntime 真实执行桥接** —— `ChildRuntime` 为每个 Child 创建独立 `AgentV2`，调用 `set_session(child_session_id)` 后进入既有 `AgentV2.run()` 主循环；Primary 不把 AgentV2、history、ToolOrchestrator 或 mutable memory/cache 引用传给 Child
- **Child permission guard** —— 工具调用在到达 AgentV2 safety gate 前先经过 Child `PermissionPolicy`；拒绝结果保留在 Child audit，不执行工具
- **TaskResult telemetry** —— 新增向后兼容 telemetry mapping，记录 `tool_calls`、`evidence`、`artifacts`、`mcp_calls`、`skill_calls` 和 cache 归因状态
- **真实取消链路** —— `ChildRuntime.cancel()` 调用 CancellationToken 与 active AgentV2.cancel；SessionTree 的 parent cancellation 通过 callback 传播到执行实例
- **Phase 4 压力测试套件** —— 双轨 T1–T8/S1–S8 高难 prompt、并发 runner、token/工具/事件记录、Windows CMD PNG capture 和详细 REPORT

### 修复的 Bug

- **placeholder 假成功** —— 旧 `ChildRuntime.execute()` 只消耗一步预算并返回固定 acknowledgement，却将状态标成 `COMPLETED`；现在真实执行前不会报告完成
- **parent cancel 不穿透** —— SessionTree 原先只标记 session/token，active AgentV2 仍可能继续等待；现在 facade callback 会触发 AgentV2.cancel
- **TaskResult 丢失执行证据** —— Child 实际调用模型后，manager 只回传 summary/usage，工具调用无法进入压力测试报告；现在通过 telemetry 回传
- **并发取消配置未生效** —— S2/S3 的 `cancel_after_sec` 已接入 harness，取消结果记录 `cancel_ok` 和终态事件

### 验证与回归

- Phase C / appserver / safety / bridge 回归：**530 passed / 1 skipped**
- 跳过项：`tests/test_appserver/test_stdio_integration.py` 的 live AgentV2 bootstrap，需要显式设置 `RXYCODE_APPSERVER_LIVE=1`
- 真实 Phase 4 压力测试：16 个高难任务，`max_parallel=6`
- 压力测试结果：**10 PASS / 6 FAIL_RUNTIME / 0 FAIL_PRODUCT**
- 真实 token 消耗：input **1,417,829**，output **163,306**，total **1,581,135**
- 取消专项：S2/S3 `cancel_ok=True`，约 52 秒进入 `child_session/cancelled`
- cache 命中率：并发 child 使用进程级 TokenStats 无法安全拆分，报告标记 `not_reported`，不生成虚假 ratio
- MCP/Skill：当前配置没有 MCP server，报告记录为 0 次真实调用，未把模型自述当成功证据

## 安装 / Install

**推荐（v1.2.9）：**

```powershell
# Windows
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/xin-yi33/RxyCode/v1.2.9/install.ps1 | iex"
```

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/xin-yi33/RxyCode/v1.2.9/install.sh | sh
```

```bash
uv tool install --force "git+https://github.com/xin-yi33/RxyCode.git@v1.2.9"
```

**下载策略：** 仅本页（v1.2.9）提供 wheel / sdist。更早版本的 GitHub Release **不开放**安装包下载。

## 资产 / Assets

- `rxycode-1.2.9-py3-none-any.whl`
- `rxycode-1.2.9.tar.gz`
