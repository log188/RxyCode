# Upstream Test-Pattern Provenance

最后核对日期：2026-07-25。

本文记录测试体系设计时参考的官方 GitHub 文件和许可证边界。它不是 Star 排名，也不声称这些项目构成固定“前 20”；项目热度和仓库结构会变化。本次 RxyCode 实现仅借鉴公开的测试模式和边界划分，没有声明从下列文件逐行复制代码，也没有复制上游 provider cassette。

## 参考记录

| 项目 | 官方文件 | 参考模式 | 许可证 |
|---|---|---|---|
| Gemini CLI | [`packages/test-utils/src/test-rig.ts`](https://github.com/google-gemini/gemini-cli/blob/main/packages/test-utils/src/test-rig.ts), [`integration-tests/parallel-tools.test.ts`](https://github.com/google-gemini/gemini-cli/blob/main/integration-tests/parallel-tools.test.ts), [`integration-tests/checkpointing.test.ts`](https://github.com/google-gemini/gemini-cli/blob/main/integration-tests/checkpointing.test.ts) | 隔离 HOME/workspace、脚本响应、PTY、进程树清理、并行 wave、checkpoint 恢复 | [Apache-2.0](https://github.com/google-gemini/gemini-cli/blob/main/LICENSE) |
| OpenAI Codex | [`codex-rs/core/tests/common/streaming_sse.rs`](https://github.com/openai/codex/blob/main/codex-rs/core/tests/common/streaming_sse.rs), [`codex-rs/core/tests/suite/approvals.rs`](https://github.com/openai/codex/blob/main/codex-rs/core/tests/suite/approvals.rs), [`codex-rs/app-server/tests/suite/v2/process_exec.rs`](https://github.com/openai/codex/blob/main/codex-rs/app-server/tests/suite/v2/process_exec.rs) | 可门控 SSE chunk、权限/沙箱矩阵、进程退出与输出事件 | [Apache-2.0](https://github.com/openai/codex/blob/main/LICENSE) |
| OpenCode | [`packages/http-recorder/src/cassette.ts`](https://github.com/anomalyco/opencode/blob/dev/packages/http-recorder/src/cassette.ts), [`packages/opencode/test/session/snapshot-tool-race.test.ts`](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/test/session/snapshot-tool-race.test.ts), [`packages/app/e2e/utils/sse-transport.ts`](https://github.com/anomalyco/opencode/blob/dev/packages/app/e2e/utils/sse-transport.ts) | 录制显式开关、路径校验、secret scanner、checkpoint/tool 竞态、SSE burst/split/disconnect | [MIT](https://github.com/anomalyco/opencode/blob/dev/LICENSE) |
| Aider | [`tests/basic/test_sendchat.py`](https://github.com/Aider-AI/aider/blob/main/tests/basic/test_sendchat.py), [`tests/basic/test_repo.py`](https://github.com/Aider-AI/aider/blob/main/tests/basic/test_repo.py) | 最小 LLM mock seam、重试序列、真实临时 Git fixture | [Apache-2.0](https://github.com/Aider-AI/aider/blob/main/LICENSE.txt) |
| OpenHands Software Agent SDK | [`openhands-sdk/openhands/sdk/testing/test_llm.py`](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/testing/test_llm.py), [`openhands-sdk/openhands/sdk/agent/parallel_executor.py`](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/agent/parallel_executor.py) | typed scripted LLM、取消信号、资源锁和有序并行结果 | [MIT](https://github.com/OpenHands/software-agent-sdk/blob/main/LICENSE) |
| Cline | [`sdk/packages/llms/src/tests/provider-vcr.test.ts`](https://github.com/cline/cline/blob/main/sdk/packages/llms/src/tests/provider-vcr.test.ts), [`sdk/packages/core/src/session/checkpoint-restore.test.ts`](https://github.com/cline/cline/blob/main/sdk/packages/core/src/session/checkpoint-restore.test.ts) | 录制失败回滚、动态字段规范化、恢复前验证 checkpoint | [Apache-2.0](https://github.com/cline/cline/blob/main/LICENSE) |
| Goose | [`crates/goose/src/providers/testprovider.rs`](https://github.com/aaif-goose/goose/blob/main/crates/goose/src/providers/testprovider.rs), [`crates/goose/tests/subprocess_cleanup.rs`](https://github.com/aaif-goose/goose/blob/main/crates/goose/tests/subprocess_cleanup.rs) | 语义消息哈希回放、缺失录制明确失败、孤儿子进程清理 | [Apache-2.0](https://github.com/aaif-goose/goose/blob/main/LICENSE) |
| Continue | [`extensions/cli/src/test-helpers/mock-llm-server.ts`](https://github.com/continuedev/continue/blob/main/extensions/cli/src/test-helpers/mock-llm-server.ts), [`extensions/cli/src/permissions/precedenceResolver.ts`](https://github.com/continuedev/continue/blob/main/extensions/cli/src/permissions/precedenceResolver.ts) | 随机端口 mock SSE、请求捕获、权限来源优先级 | [Apache-2.0](https://github.com/continuedev/continue/blob/main/LICENSE) |

这些链接指向便于阅读的活动分支，只用于说明设计参考，不是不可变的代码来源记录。

## 本项目采用的模式

- 队列式 `ScriptedChatModel` 只替换 provider，保留真实 Agent/graph/tool/validator 边界。
- 临时 HOME、data/config 和 workspace 隔离，测试结束恢复进程级状态。
- unit/integration/contract/system/live/pty 分层，普通 CI 排除收费和平台不稳定边界。
- JUnit 与 coverage artifact 可追踪失败；Windows 单独验证 ConPTY。
- fixtures 使用项目自建最小语义数据，禁止自动从真实流量更新。

这些模式由 RxyCode 重新实现并适配现有 Python、FastAPI、LangChain 和 Ink 代码；模式相似不等于复制上游表达。

## 未来逐行移植代码时的要求

在复制任何上游代码、测试或 substantial fixture 前，必须：

1. 固定完整 upstream commit SHA，不能只记录可变的 `main`/`dev` 链接。
2. 记录仓库、原文件、行或符号、移植日期、修改内容和负责人员。
3. 核对该路径适用的 LICENSE、NOTICE、版权头和第三方依赖，而不是只看 GitHub API 的仓库级标签。
4. MIT 代码保留版权和许可证文本；Apache-2.0 代码保留 LICENSE/NOTICE、标记修改，并遵守其专利和商标边界。
5. 将所需 NOTICE/attribution 随源码和发行物分发，并在本表增加不可变链接。
6. 对 PolyForm、source-available、双许可证或 `enterprise/` 路径先取得明确法律批准；没有批准时不移植。
7. Provider cassette、真实会话和凭据即使许可证允许也不复制；只在隔离账户中重新生成并执行 secret scan。

特别说明：高关注度的 [`OpenHands/OpenHands`](https://github.com/OpenHands/OpenHands) 根仓库包含 MIT 与 `enterprise/` PolyForm Free Trial 边界，本表因此只把当前 MIT 的 `software-agent-sdk` 作为代码模式参考。AutoGPT 的 `autogpt_platform` 也有 PolyForm Shield 边界，未作为 RxyCode 移植来源。
