# Phase 4 Desktop 压力测试报告

日期：2026-08-11

范围：当前 Phase 4 Desktop（非 Phase G 完整 Desktop）
执行方式：真实 Electron 窗口 + CDP 驱动 + 确定性 appserver 协议回放。每一轮由脚本关闭 Electron 子进程并删除临时 profile。

## 结论

- 15/15 个用户式场景均按预期结束：13 个成功、1 个用户取消、1 个外部 MCP 失败恢复。
- 压力运行总时长 17.479 秒，共渲染并校验 36 张工具卡。
- 每个成功会话严格为本会话的 3 张工具卡；首会话回切不会出现 DTS-15 的消息，证明会话消息和工具卡不串。
- 截图检查了工具卡、审批后的结果、长会话列表；固定顶栏和输入栏没有因会话增长而折叠，页面本身未发生滚动。
- 每轮结束后检查 Electron/Node 测试进程：无残留。

## 发现并修复的问题

1. 新建会话没有自动激活，后续提示词会继续发送到第一条会话，造成工具卡和消息看似串会话。
   - 修复：`addSession()` 始终把新建 session 设为活动 session。
   - 防回归：新增 reducer 单测和 15 场景的会话回切断言。

2. 测试 appserver 的取消登记晚于“运行中工具卡”的显示；用户立即点击停止时可能丢失取消请求。
   - 修复：在第一条流事件前登记可取消请求。
   - 防回归：DTS-12 必须呈现失败态工具卡和 `partial` 结果，不能呈现成功完成答案。

3. 审批页曾有两个 JSON-RPC 客户端竞争读取同一个 stdio 流，第二个客户端会对审批服务端请求回复 `Method not found`。
   - 修复：模型设置改为复用会话拥有的 `ProtocolClient`，不再建立第二条连接。
   - 防回归：集成测试覆盖异步审批决策；D4 截图回归覆盖同意、始终允许、提交中、错误与自动批准。

4. 相对写入路径可能被历史输出中同名文件劫持，而不是写入当前工作区。
   - 修复：非 `output/...` 的相对写路径优先解析到当前工作区；显式输出路径保持原有语义。
   - 防回归：新增同名历史输出测试和文件操作回归。

5. `rxycode GUI` 以前依赖 Click 默认大小写匹配。
   - 修复：命令组按 `casefold()` 解析子命令。
   - 防回归：`GUI`、`Gui`、`gUi` 均有单测。

## 15 个场景与结果

| ID | 用户提示词（摘要） | 结果 / 最终回答 | 工具路径 | 时长 |
| --- | --- | --- | --- | ---: |
| DTS-01 | 审计 Python 服务启动链路、列风险和验证命令 | 成功：已分析并验证 | grep → read → skill | 882 ms |
| DTS-02 | 为订单缓存实现 TTL，分析、修改、回归 | 成功：已分析并验证 | read → skill → workspace MCP | 1,021 ms |
| DTS-03 | 调查生产错误日志并给根因报告 | 成功：已分析并验证 | skill → workspace MCP → websearch | 1,019 ms |
| DTS-04 | 用 coding-workflow Skill 规划 API 迁移 | 成功：已分析并验证 | workspace MCP → websearch → bash | 1,017 ms |
| DTS-05 | 用 workspace MCP 交叉核对业务文档 | 成功：已分析并验证 | websearch → bash → write | 1,021 ms |
| DTS-06 | 竞品调研并写带来源的决策记录 | 成功：已分析并验证 | bash → write → git | 1,021 ms |
| DTS-07 | 检查 Git 工作区和 CI 失败测试 | 成功：已分析并验证 | write → git → glob | 873 ms |
| DTS-08 | 审计支付模块敏感变更 | 成功：已分析并验证 | git → glob → grep | 1,022 ms |
| DTS-09 | 需要写入审批的数据库迁移预检 | 成功：审批后“写入完成” | bash（审批） | 2,244 ms |
| DTS-10 | 需要写入审批的临时文件清理 | 成功：审批后“写入完成” | bash（审批） | 2,385 ms |
| DTS-11 | 长多工具分析并在会话间切换 | 成功：已分析并验证 | read → skill → workspace MCP | 876 ms |
| DTS-12 | 长耗时依赖诊断，工具出现后用户停止 | 预期取消：`partial` | bash（interrupted） | 881 ms |
| DTS-13 | 模拟外部 MCP 失败并继续新会话 | 预期失败：`demo failure` | 无（错误态） | 1,172 ms |
| DTS-14 | 多文件重构：Skill、MCP、读写、测试 | 成功：已分析并验证 | websearch → bash → write | 1,023 ms |
| DTS-15 | 发布前检查、验证命令、上线说明 | 成功：已分析并验证 | bash → write → git | 1,022 ms |

完整原始结果与三张 Electron 截图保留在本次测试工件目录：`artifacts/desktop-stress-20260811-final/`（不纳入 Git）。

## Token、缓存与模型说明

这 15 条用于前端/协议压力验证，使用确定性 appserver，而不是向模型供应商发送付费请求。因此它们的统计为：

| 指标 | 数值 |
| --- | --- |
| input token | N/A（无模型请求） |
| output token | N/A（无模型请求） |
| cache hit token | N/A（无模型请求） |
| cache hit rate | N/A（无模型请求） |
| 模型费用 | 0 |

这不是缺失数据：把模拟协议事件标为真实模型 token 会产生错误的成本报告。模型能力单独做了最小连接预检，结果如下（仅验证连接，不执行长任务，因此供应商未返回可汇总的 input/output/cache 使用量）：

| 模型 | 连接结果 | 耗时 |
| --- | --- | ---: |
| `opencode-go/deepseek-v4-flash` | 成功 | 2.36 s |
| `deepseek/deepseek-v4-flash` | 成功 | 1.55 s |
| `opencode-go/mimo-v2.5` | 成功 | 2.50 s |
| `zen/gpt-5.6-luna` | 成功 | 1.90 s |

`zen/gpt-5.6-luna` 初检发现它错误地只引用了未设置的 `OPENCODE_ZEN_API_KEY`。已按既有 OpenCode Go 凭据的受保护引用复用配置，仅调整凭据引用，未读取、输出或写入明文密钥；网关仍为 `https://opencode.ai/zen/v1`，因此 DTS-15 没有退回 Go 网关。

## 回归命令

```powershell
cd frontend/desktop-app
npm test                 # 138 passed
npm run typecheck        # passed
npm run screenshot:d3    # passed
npm run screenshot:d4    # passed
npm run screenshot:d5    # passed
npm run stress:desktop -- ..\..\artifacts\desktop-stress-20260811-final

# 仓库根目录，使用本次隔离 venv
python -m pytest tests/unit/test_gui_command.py tests/test_appserver/test_stdio_integration.py tests/test_appserver/test_approval.py tests/test_core/test_resolve_write_path_nesting.py tests/test_tools/test_write.py tests/test_core/test_session_runtime.py tests/test_fileops_e2e.py -q
# 73 passed, 1 skipped（RXYCODE_APPSERVER_LIVE 未设置）
```

## 限制与后续

- 当前机器没有已配置的真实 MCP server；DTS 中的 MCP 与 Skill 卡通过协议回放验证 Desktop 的渲染、会话隔离、失败与审批路径，不宣称调用了真实远程 MCP。
- 本报告的 15 条未跑长模型任务，目的是以零模型费用找出 Desktop 前端问题。真实模型的 token/caching 统计应由 appserver 在每次 provider 响应中标准化后上报 UI；这属于后续 Phase 的可观测性工作。

## 补充：真实模型与真实 Electron 复测（2026-08-11）

本节替代上文“15 条均为确定性 appserver 回放”的结论，记录随后完成的真实验收：每例均启动生产 `python -m appserver`、真实 Electron、真实模型，通过 CDP 输入提示词和截屏；没有使用 Computer Use。每个探针都在 `finally` 中 `taskkill /T /F` Electron 进程树并删除临时 profile。结束后复核：无残留 Electron 进程。

模型策略：DTS-01 至 DTS-14 使用低成本 `opencode-go/deepseek-v4-flash`；DTS-15 临时使用 `zen/gpt-5.6-luna`，完成后恢复 `active_model: opencode-go/deepseek-v4-flash`。DTS-07 临时注册本机 stdio MCP 回显服务并恢复完整 `config.yaml`；它没有网络能力，也没有读取密钥。

真实结果为 9 通过 / 6 预期失败。失败不是忽略：它们验证了失败 UI 已正确终态化（消息为错误态、全部已开始的工具卡为错误态、不会遗留“运行中”卡）。全部原始提示词、完整 final answer、截图和逐例 JSON 指标保存在未入库工件目录：

`D:\agent-demo\RxyCode\RxyCode1_1_0\.worktrees\phase4-desktop-stress-20260811\artifacts\desktop-real-suite-20260811\DTS-*/`

| ID | 用户式业务提示词（精确工具约束摘要） | 结果 / final answer 摘要 | 工具 | 耗时 | input / output / cache-hit / hit-rate |
| --- | --- | --- | --- | ---: | --- |
| DTS-01 | 审计 appserver 启动上下文：glob → grep → read；禁用写入与联网 | 失败：模型仍调用 websearch/webfetch，最终被副作用证据门禁拦截 | websearch, webfetch×3, glob, grep, read | 58.185s | 未上报终态用量 |
| DTS-02 | 审查协议通知契约：glob → grep `event/token_usage` → read | 通过：确认 TokenUsage/FinalAnswer 的 JSON-RPC 事件契约 | glob, grep, read | 23.704s | 未上报终态用量 |
| DTS-03 | 审查 conversation terminal state：glob → grep → read | 失败：只读工具完成后仍收到“无 WRITE/DANGER 证据” | glob, grep, read | 25.705s | 32,604 / 776 / 30,464 / 93.44% |
| DTS-04 | 审查模型输出限制目录：glob → grep → read | 失败：同一错误门禁路径 | glob, grep, read | 26.018s | 36,250 / 739 / 32,512 / 89.69% |
| DTS-05 | 审查 Desktop 审批规则：glob → grep → read | 失败：同一错误门禁路径 | glob, grep, read | 26.109s | 32,660 / 817 / 29,952 / 91.71% |
| DTS-06 | 审查 session 缓存遥测：glob → grep → read | 通过：确认 per-turn delta 与 TokenUsage/FinalAnswer 输出 | glob, grep, read | 25.595s | 未上报终态用量 |
| DTS-07 | 发票对账场景：调用真实本机 MCP echo，再核查 token 协议 | 通过：final answer 返回 `desktop-test-echo:invoice-reconciliation-2026` 并解释协议字段 | mcp_desktop_test_echo_echo, glob, read | 22.803s | 24,222 / 660 / 17,024 / 70.28% |
| DTS-08 | 要求加载已安装 `tdd` Skill，再审查只读测试 | 失败：路由错误调用 `download_skill`，且无审批 broker | download_skill | 11.362s | 未上报终态用量 |
| DTS-09 | 审查 protocol schema 缓存字段：glob → grep → read | 通过：确认 schema 表面与缓存字段定义 | glob, grep, read | 28.539s | 32,063 / 562 / 29,952 / 93.42% |
| DTS-10 | 审查 appserver worker 输出：glob → grep → read | 通过：确认 JSON-RPC result 带 cache-hit 字段 | glob, grep, read | 24.765s | 35,196 / 709 / 32,384 / 92.01% |
| DTS-11 | 审查 Desktop 启动运行时：glob → grep → read | 失败：目标文件不存在后模型做只读回退，最终仍误触发证据门禁 | glob×4, grep×3, read | 33.392s | 49,105 / 1,764 / 44,160 / 89.93% |
| DTS-12 | 审查审批渲染规则：glob → grep → read | 失败：同一错误门禁路径 | glob, grep, read | 22.582s | 未上报终态用量 |
| DTS-13 | 审查 session token 合同：glob → grep → read | 通过：确认 input delta 注入 TokenUsage、FinalAnswer 与 PromptResult | glob, grep, read | 22.197s | 26,874 / 616 / 23,680 / 88.11% |
| DTS-14 | 审查 worker cache-hit 输出：glob → grep → read | 通过：确认 worker 传递四项 token/缓存字段 | glob, grep, read | 22.959s | 34,639 / 371 / 31,872 / 92.01% |
| DTS-15 | Zen 模型审计 TUI 绑定：glob → grep → read | 通过：`zen/gpt-5.6-luna` 返回路径、绑定证据和并发风险 | glob, grep, read | 22.174s | 26,565 / 205 / 19,374 / 72.93% |

可汇总的 10 个终态用量事件合计：input 330,178、output 7,219、cache-hit 291,374、加权缓存命中率 88.25%。15 个场景总墙钟 396.089 秒。5 个失败/终态路径未发出 token usage 通知；报告把它标成“未上报”，不把未知数据记成 0。

本轮发现并已修复：

1. 真实 appserver 以顶层 `python -m appserver` 启动时，可能从同级 checkout 混入旧版绝对包导入；现已将 canonical 包名绑定到启动 checkout，并有子进程回归测试。
2. 真实任务只有 `tool_begin`、缺少 `tool_end` 时，Desktop 曾将完成后的工具卡保持为“运行中”；成功 final 现在收敛为完成，失败 prompt result 收敛为错误，两个状态都有 reducer 回归测试和真实 Electron 截图验收。
3. Desktop 真实探针现记录 final/prompt result 的 input、output、cache-hit、命中率和耗时；终态有运行中工具卡会直接判失败。

仍待修复（本轮不应掩盖）：

1. 多个明确只读的 `glob/grep/read` 工作流仍会在结束时错误触发“requested side effect has no verified WRITE/DANGER tool execution”。DTS-11 的原始 JSONL 已证明实际工具均为 READ，需在后端增加“设置副作用尝试标志”的可观测性后再做最小修复，不能凭猜测放宽安全门禁。
2. 已修复“installed skill”误路由到 `download_skill`（`a15b079`）：DTS-08 重跑实际调用了只读 `skill`。但随后仍命中上项只读工具的副作用证据误判；因此 Skill 路由问题已关闭，证据门禁问题仍待修复。
