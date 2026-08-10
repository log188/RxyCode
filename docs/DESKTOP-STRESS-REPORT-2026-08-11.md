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
