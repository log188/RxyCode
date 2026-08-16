# PHASE-FIX 开发交接文档（Agent-to-Agent Handover）

> 生成时间：2026-08-15
> 用途：本仓库 PHASE-FIX（极致缓存 + 极致速度）开发任务的完整上下文，供
> 其他 Agent 窗口无缝接手继续施工。开发进度截至 **FXC1–FXC5 已完成并勾选**。

---

## 1. 仓库与开发地址

| 项 | 值 |
|---|---|
| 仓库路径 | `D:\agent-demo\RxyCode\RxyCode1_1_0` |
| 开发分支 | **`fix`**（当前 checkout 在此分支） |
| 开发文档 | `docs\plans\opus5-plan\rxycode\PHASE-FIX.md`（1844 行，权威施工文档） |
| 权威调研 | `docs\plans\opus5-plan\rxycode\research\2026-08-14-deepseek-harness-and-opencode-cache.md`（1595 行，Part 1 §1-19 / Part 2 §20-24 / Part 3 §25-33） |
| 审计产物 | `artifacts\FXC*-luna-audit*.txt` |
| 提交基线 | master 为 `41b8649`；fix 分支在其上前进 |

注意：`docs/plans` 被 `.gitignore` 忽略，文档改动需 `git add -f`。

---

## 2. 任务全景（17 张卡）

**Part 1（通配契约）**：FXC1 catalog 对齐 → FXC2 通配三族注入 → FXC3 S1/S2 动静拆分 → FXC4 session 亲和头+DeepSeek 双字段+晚 compact → FXC5 各厂 thinking/echo 契约 → FXC6 未知模型五条 fallback

**Part 2（1s/3s 延迟）**：FX3 ChatPrefix skip_await、FX4 双档案预热同构、FX5 keep-alive 同构、FX7 Primary 首字

**Part 3（未来不返工）**：FX1 PrefixProfile、FX2 TurnRouter、FX6 ToolsFreeze、FX8 append_turn_context、FX9 ns=None 兼容、FX10 HandoffEnvelope、FX11 文档+evals

**推荐顺序（一次一张）**：FXC1 → FXC2 → … → FXC6 → FX1 → FX2 → … → FX11（FX4 硬性依赖 FXC2+FXC5）

---

## 3. 开发纪律（GX1-GX8 + FX-CB1-CB12，违反即打回）

| # | 规则 |
|---|---|
| GX1 | **一次只做一张卡**，禁止合并、禁止"顺便改" |
| GX2 | **不读整份施工文档**，只读 §0 + 本卡 + §4 |
| GX3 | 不发明平行类型（禁第二套 PrefixConfig/RouteResult/cache_control 注入器/`core/cache_family.py`） |
| GX4 | **只碰白名单文件**（每卡白名单见卡内表格） |
| GX5 | 一张卡一个可 revert 的 commit（message 含卡号） |
| GX6 | 验收命令全绿才提交审计（贴真实输出） |
| GX7 | 允许改卡内 `core/` 等文件；禁 credentials.yaml/.env*/data/；禁发明 JSON-RPC 方法 |
| GX8 | 卡住就停下问用户（Grep 锚点找不到/需改白名单外/同一错误修 3 次） |

**FX-CB 硬约束（节选关键）**：
- FX-CB2 `_run_impl` 禁止新增启发式 if（决策只来自 TurnRouter）
- FX-CB9 隐式前缀族与未知模型**绝不注入 cache_control**（DeepSeek/Kimi/GLM/MiMo/Grok/Doubao/M3/catalog 缺失）
- FX-CB10 显式断点族帽 4、tools 只打**最后一个** tool、滚动 last-user、禁对 thinking 块打点
- FX-CB11 协议分类**只信 cache_contract**（`cache_mode` 四枚举：auto/cache_key/auto_and_key/explicit_breakpoints），禁模型 id 含 claude 启发式
- FX-CB12 `_to_openai_messages` 保留 human 的 cache_control
- 每卡完成判据在 GPT-5.6 PASS 前必须保持 `- [ ]`，**Grok 代勾视为任务失败**

---

## 4. 开发流程（每张卡七步）

```
1. LOCATE  用 Grep 锚点定位（不信行号）
2. WRITE   先写卡里的失败测试（红）→ 再最小实现（绿）
3. LINT    python -m ruff check <白名单文件>
4. TEST    跑卡里每一条验收命令，把真实输出贴到「实施记录」
5. STOP    不要勾完成判据。输出「请 GPT-5.6 审计 FXC<编号>」
6. WAIT    GPT-5.6 按附录 B 回复 PASS 之后，才允许勾该卡完成判据、commit、开下一张
```

**开工自检（每新会话一次）**：
```powershell
cd "D:\agent-demo\RxyCode\RxyCode1_1_0"
python --version
git status --short          # 有非本卡未提交改动 → 停下问用户，不要 git checkout .
git branch --show-current   # 必须是 fix
python -c "from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2; print('import ok')"
```

---

## 5. luna 审计机制（关键，写清楚）

### 5.1 网关与凭据

| 项 | 值 |
|---|---|
| **网关 URL** | `https://opencode.ai/zen/v1/chat/completions`（**ZEN 网关，严禁走 go 网关**） |
| **模型** | `gpt-5.6-luna` |
| **API Key** | 从 `C:\Users\Administrator\.local\share\opencode\auth.json` 读 `opencode-go.key` 字段 |
| **Key 值** | `sk-test-secret-placeholder-do-not-commit` |
| 请求参数 | `{"model": "gpt-5.6-luna", "messages": [...], "max_tokens": 4000, "temperature": 0.2}` |
| Header | `Authorization: Bearer <key>` |
| 注意 | 网关非 go 网关；审计每轮新会话，附卡号 + git diff + pytest 输出 |

### 5.2 审计脚本模式（复制改卡号即可）

参考：`C:\Windows\TEMP\opencode\fxc5_luna_audit.py`（FXC5 版，可复制为 FXC6/FX*）

要点：
- 读取 PHASE-FIX.md 的**本卡段**（`src.find("### FXC5")` 到下一个 `### FXC6`）作为「卡原文」
- 读取权威调研节选
- `git diff <卡首 commit>^..HEAD -- <白名单文件>`（**必须限定白名单文件**，避免把独立 commit（如 FXC1 补充）算进本卡 diff）
- pytest 验收命令输出 + ruff 输出 + 受影响回归输出
- prompt 结构 = 附录 B 检查清单（8 条通用 + 卡专项）+ 卡原文 + 调研节选 + 交付物 diff + 测试输出
- HTTP POST 到 ZEN 网关 → 结果存 `artifacts/FXC*-luna-auditN.txt`
- **审计返回 FAIL → 逐项修复 → 重新审计（下一轮 R2/R3...）→ PASS 才可勾判据**

### 5.3 附录 B 审计检查清单（通用 8 条）

1. 是否只改本卡白名单文件？
2. 是否违反 FX-CB1-CB12？
3. 测试是否真覆盖完成判据（非改断言放水）？
4. 是否给 DeepSeek/M3/未知模型打了 cache_control？是否用模型 id 含 claude 打点？cache_mode 是否写 schema 没有的 explicit/breakpoints？
5. 是否为未来多 agent/多模型/LinkAgent 留下打穿前缀的后门？
6. 文档完成判据是否仍全 `[ ]`（Grok 不得代勾）？
7. 是否越界做协议升级（整链 Responses/原生 Messages/方舟 Context API）？
8. 是否新建 cache_family.py 或第二套注入器？

### 5.4 审计循环经验（FXC4/FXC5 实测）

- 审计会逐轮追加要求（R1→R2→...→R11），每轮必须把 FAIL 项最小修复
- 审计**前后可能矛盾**（如 qwen3.7-plus 补 catalog：R3 要求补、R4 说越界、R7 又要求）——处理原则：**调研真实契约（官网/Phase A 文档）+ 拆到正确责任卡（独立 commit）+ 在实施记录写明依据**
- 涉及**架构/协议边界**（如 M3 signature）时：去官网调研（`platform.minimaxi.com/docs/api-reference/text-chat-openai` 确认 M3 走 OpenAI 兼容、无 Anthropic signature），把官网证据附进审计 prompt
- 审计脚本 prompt 里的 f-string 花括号要转义（`{` → `{{`）或避免字面 `{}`

---

## 6. 当前进度（截至 FXC5 完成）

| 卡 | 状态 | 关键 commit |
|---|---|---|
| FXC1 catalog 对齐 | ✅ 判据 7/7 勾 + PASS | 07c7047, edf87e4 |
| FXC2 通配三族注入 | ✅ 判据 7/7 勾 + PASS | 1ae2c7a, be96bf7, b2f4060 |
| FXC3 S1/S2 拆分 | ✅ 判据 4/4 勾 + PASS | 51440aa |
| FXC4 session 头+usage+compact | ✅ 判据 4/4 勾 + PASS（R7） | 68e4967 + R1-R6 修订 |
| FXC5 thinking/echo 契约 | ✅ 判据 4/4 勾 + PASS（R11） | 4ba2300 + R1-R10 修订 |
| FXC1 补充（qwen3.7-plus） | ✅ 独立 commit | 47c896c |
| **FXC6 未知模型 fallback** | ⬜ **下一步** | — |
| FX1-FX11 | ⬜ 未开始 | — |

**FXC5 关键实现**（后续卡会用到）：
- `_should_echo_reasoning(reasoning_contract, provider_id, has_tool_calls, reasoning)`（agent_v2 模块级）
- `_to_openai_messages(messages, *, reasoning_contract=None, provider_id=None)`（echo 分派）
- kimi-k3 只 effort / qwen 无 thinking 对象 / GLM clear_thinking（均 catalog 驱动）
- 测试：`tests/test_providers/test_thinking_contract.py`（40 passed）

**重要代码位置**：
- `core/catalog.py`：`get_contract` / `read_cached_tokens`（max 双路径）/ `injects_cache_control` / `injects_prompt_cache_key`
- `core/agent_v2.py`：`_raw_stream`（FXC2 打点 + FXC5 echo）、`_to_openai_messages`、`_apply_cache_control`、`build_session_headers`、`_should_echo_reasoning`
- `core/prompts/registry.py`：`get_system_s1`（FXC3）
- 各 provider：`core/providers/{kimi,qwen,glm,mimo,minimax,deepseek}.py`

---

## 7. 环境陷阱与既有基线（接手前必读）

**环境陷阱**：
- PowerShell `python -c "..."` 多行/引号/反斜杠转义极坑——优先写脚本文件执行
- 主工作区被多会话共用：偶发 `frontend/desktop-app/scripts/desktop-cd-report.mts` unmerged（stash/index 锁竞争残留）→ 处理：备份 → `git reset <file>` → `git checkout -- <file>`（恢复 HEAD），再 commit
- `docs/plans` 被 gitignore → 文档 commit 用 `git add -f`
- 另一会话的进程（rxycode.exe/appserver/agent_worker）会抢占资源导致全量 pytest 间歇超时（~88% 处）——非代码问题

**未提交的他人改动（接手时保留，勿动）**：
- `core/research_policy.py`、`tests/test_core/test_research_fast_path.py`（+69）、`tests/test_core/test_session.py`、`tests/test_logging_observability.py`、`tests/test_providers/test_token_governance.py`、`tests/test_tools/test_websearch.py`、`tools/websearch.py`
- `diag_compare.py`、`diag_raw_api.py`（未跟踪诊断脚本）
- 其中 test_research_fast_path 2 项测试（reasoning continuation / websearch 注入）**已知失败**（mock 自定义 _raw_stream，绕过 FXC5 路径，非本 Phase 责任）

**已知基线失败（与本 Phase 无关）**：
- `tests/test_cache/test_breakpoint_budget.py` 2 项（FXC2 语义遗留，白名单外）
- `tests/test_contract/test_bench_gate.py`（C8 async bench 环境依赖）
- `test_tool_async.py::test_open_file_async_windows_startfile_fire_and_forget`（Windows 环境）

---

## 8. 下一卡执行提示（FXC6 未知模型五条 fallback）

- 白名单：`core/catalog.py`（`unknown_fallback_contract()` 文档化常量）、`core/agent_v2.py`、`tests/test_cache/test_unknown_model_fallback.py`（新建）
- 五条（§15.3）：① Prompt 默认 variant；② openai-compatible 协议；③ **不发 cache_control**；④ tools 按名排序 + session 头；⑤ **prompt_cache_key 默认不发**
- 依赖：FXC2（注入层已就绪）
- 验收：`python -m pytest tests/test_cache/test_unknown_model_fallback.py -q`
- 审计脚本照抄 `fxc5_luna_audit.py` 改卡号即可

---

## 9. 收尾检查（§6 出口，全部卡完成后）

- Grep `core/agent_v2.py`：无 `for tool_def in payload["tools"]` 全员打点
- DeepSeek/M3/未知模型序列化 JSON 无 `"cache_control"`
- `SystemMessage(content=research_contract)` 无匹配；S1 不含每轮日期
- Grep `_run_impl`：无 `is_social_chat(`/`PURE_SOCIAL_GREETING_RE`/`declines_tools(` 分流
- `route("你好").path == "chat"` 且 skip_await 非空；evals 基线不下降
- FX11 时跑全卡总览审计 + evals compare
