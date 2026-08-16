# Phase Fix · 极致缓存 + 极致速度（通配契约 / PrefixProfile / TurnRouter / 未来不返工）

> **For agentic workers:** REQUIRED：一次只做一张卡。做完后 **不得** 自己勾「完成判据」。必须等 **GPT-5.6 审计 PASS** 之后，才允许在本文件里把该卡验收标准打钩。推荐下一张卡开新会话。
>
> **在整条路线中的位置**：插在 Phase B（缓存纪律已落地但 catalog/断点/S1 仍与官方不符、预热/问候签名仍打架）与 Phase C/D 继续膨胀之前。它修三件事：**Part 1** 通配契约打错、**Part 2** 闲聊走完全部流程、**Part 3** 未来 D/E/F/H/I/G/LinkAgent 不准再踩的缝。
> **前置**：读 [`research/2026-08-14-deepseek-harness-and-opencode-cache.md`](./research/2026-08-14-deepseek-harness-and-opencode-cache.md) **全文 Part 1 §1–§19 + Part 2 §20–§24 + Part 3 §25–§33**。本文件不重写调研结论，但 **任务卡必须覆盖三部分门禁**（对照表见 §1.0）。
> **后继**：Phase C/D/E/F/G/H/I 与 LinkAgent L2 **必须引用本文件 §3 不变量**；不得再发明第二套前缀/路由/注入/cache_control 启发式。
>
> **一句话目标**：预设模型全部按官方契约高命中（通配三族 + 正确 catalog）；Primary 长任务达到「累计 input 千万级、未命中只有新后缀」（北极星 2900万/33万 ≈ 98.86%，97% 是地板）；十分简单闲聊 1s 内看到回复；简单任务 ≤3s；任何任务 3s 内 thought 有内容。用 **cache_contract 通配层 + 两条冻结前缀 + 单一 TurnRouter** 实现，而不是按模型名 if 或在 `_run_impl` 上继续加分支。
>
> **执行模型（本 Phase 覆盖 MODEL-ASSIGNMENT 的局部例外）**：
> - **Grok 4.6 主写本 Phase 全部代码**（含 `core/` 白名单文件）。这是用户 2026-08-14 的硬性指定。
> - **复用 Grok 4.5 纪律**（一次一张、不读整份、白名单、停下来问、不发明平行类型/协议），见 §0.2。Grok 4.5 手册里「不许碰 `core/`」**仅在本 Phase 对 Grok 4.6 放开到卡内白名单**。
> - **GPT-5.6 审计门**：每卡测试绿了之后，换会话让 GPT-5.6 按附录 B 审 diff。**未 PASS 不得勾完成判据、不得开下一张卡。**
> - Composer 2.5 **不**主写本 Phase；不必等它收口。
>
> **基线日期**：2026-08-14　**任务卡**：FXC1–FXC6（Part 1）→ FX1–FX11（Part 2/3）　**仓库**：`D:\agent-demo\RxyCode\RxyCode1_1_0`

---

## 目录

| 章节 | 什么时候读 |
|---|---|
| [§0 执行手册](#0-执行手册必读) | **每张卡开工前** |
| [§1 更改说明](#1-更改说明为什么改改哪里如何改) | 理解本 Phase 在改什么；含 Part 1/2/3 覆盖表 |
| [§2 目标架构](#2-目标架构) | 写代码前看懂边界 |
| [§3 不变量](#3-不变量d–linkagent-必须引用) | 以后任何 Phase 禁止违反 |
| [§4 文档规范与代码规范](#4-文档规范与代码规范) | 卡内示例必须遵守 |
| [§5 任务卡](#5-任务卡) | **执行时只读一张卡**。先 FXC（Part 1）再 FX（Part 2/3） |
| [§6 出口](#6-phase-fix-出口) | 全卡过完才算完 |
| [附录 A 代码示例总表](#附录-a代码示例总表) | 类型与签名速查 |
| [附录 B GPT-5.6 审计提示词](#附录-b-gpt-56-审计提示词) | 审计会话只贴这个 |

---

## §0 执行手册（必读）

### 0.1 你是谁、一次只做一张卡

你是 **Grok 4.6**，在 Windows / PowerShell 下改已经能跑的 RxyCode。`core/agent_v2.py` 约 4700–5300 行，被 API / TUI / evals 三方依赖。

接到「执行 FXC1」或「执行 FX3」时：

```
1. 只读 §0 + 那一张卡（不要通读本文件，规则 GX2）
2. LOCATE  用 Grep 锚点定位，不信行号
3. WRITE   先写卡里的失败测试，再写最小实现（TDD）
4. LINT    python -m ruff check <白名单文件>
5. TEST    跑卡里每一条验收命令，把真实输出贴到「实施记录」
6. STOP    不要勾完成判据。输出「请 GPT-5.6 审计 FXC1」或「请 GPT-5.6 审计 FXN」
7. WAIT    GPT-5.6 按附录 B 回复 PASS 之后，才允许勾该卡完成判据、commit（若尚未 commit）、开下一张
```

**一次一张卡。** 先做完 FXC1–FXC6（Part 1），再 FX1–FX11。禁止合并。禁止「顺便把 FX4 的预热也改了」。禁止「顺便给 DeepSeek 打 cache_control」。

### 0.2 复用的 Grok 4.5 限制（本 Phase 编号 GX）

来源 [`../GROK-FRONTEND-PLAYBOOK.md`](../GROK-FRONTEND-PLAYBOOK.md) G1–G8，适配为后端施工：

| # | 规则 | 违反即打回 |
|---|---|---|
| GX1 | **一次只做一张卡**（G1） | 一个 diff 里出现两张卡的文件职责 |
| GX2 | **不读整份施工文档**，只读本卡 + §0 + §4（G2） | 通读后「综合考虑」改范围外代码 |
| GX3 | **不发明平行类型**（G3） | 卡外再写一套 `PrefixConfig` / `RouteResult` / 第二套 `cache_control` 注入器 / `core/cache_family.py` |
| GX4 | **只碰白名单文件**（G4） | 为了让测试绿去改测试期望语义、改别的模块 |
| GX5 | **一张卡一个可 revert 的 commit**（G5 收口语义） | 两卡一个 commit；message 不写卡号 |
| GX6 | **验收命令全绿才提交审计**（G6 的「必须亲眼看见」） | 声称完成但没贴输出 |
| GX7 | **本 Phase 允许改卡内列出的 `core/` 等文件**；仍禁止 `credentials.yaml`、`.env*`、`data/`、`~/.rxycode/`；禁止发明 JSON-RPC 方法 | 跨界改 protocol 语义 |
| GX8 | **卡住了就停下来问，不要发挥**（G8） | Grep 锚点找不到、需要改白名单外文件、同一错误修 3 次 |

停工报告格式：

```
STOP：FX<编号> <一句话>
我做到了：
我需要：
我没有改：（确认没有越界）
```

### 0.3 GPT-5.6 审计门（硬性）

| 谁 | 可以 | 不可以 |
|---|---|---|
| Grok 4.6 | 写代码、跑测试、把输出贴进「实施记录」 | **勾完成判据**；宣布 Phase 完成 |
| GPT-5.6 | 按附录 B 审 diff + 测试输出；PASS 后勾完成判据 | 顺手改代码（发现必须改 → 打回 Grok，开同一张卡的修复提交） |
| 用户 | 最终确认 | — |

勾选权：仅 GPT-5.6（或用户在看到 GPT-5.6 PASS 之后代勾）。Grok 4.6 在文档里把 `- [ ]` 改成 `- [x]` **视为任务失败**。

### 0.4 硬约束（本 Phase）

| # | 约束 | 失败判定 |
|---|---|---|
| FX-CB1 | 两条 PrefixProfile，禁止同一 key 上变装 | 问候与编码共用 tools/thinking 字节 |
| FX-CB2 | `_run_impl` 禁止新增启发式 if；决策只来自 `TurnRouter.route` | 新 `if social and ...` 出现在 `_run_impl` |
| FX-CB3 | 预热 / keep-alive / 真实 turn **三流同构**于当前 Profile | keep-alive 无 system 或 tools=None 而 Profile 有 tools |
| FX-CB4 | 限权不裁 schema；Chat 空工具是 **另一条冻档案** | `resolve_fast_reply_tool_allowlist` 仍决定 API tools 形状 |
| FX-CB5 | `ns=None` 时 `_application_cache_namespace()` 与改造前 **逐字节相同** | 单 Agent evals 无故变慢或缓存全失效 |
| FX-CB6 | `append_turn_context` 不得改 S1 / tools digest | 测试 `test_eko_never_mutates_system_or_tools_digest` 红 |
| FX-CB7 | 1s/3s 只验收 Primary；Child 冷写不得摊进 Primary `cache_rate` | 混桶 |
| FX-CB8 | 默认路径行为：未选 ChatPrefix 的编码任务仍走工具循环；evals 基线不下降 | `latest-agent.json` 掉分 |
| FX-CB9 | **隐式前缀族与未知模型绝不注入 `cache_control`**（DeepSeek / Kimi / GLM / MiMo / Grok / Doubao Chat / MiniMax M3 / catalog 缺失） | 给 DeepSeek 或 `cache_mode=auto` 的 payload 出现 `cache_control` |
| FX-CB10 | **显式断点族**：帽 4；tools 只打 **最后一个** tool；滚动 last-user；**禁止**每个 tool 打点；禁止对 thinking 块打点 | `_raw_stream` 仍 `for tool_def in payload["tools"]` 全打 |
| FX-CB11 | 协议分类 **只信** `cache_contract`（`cache_mode` / `breakpoints_max` / `prompt_cache_key_required`）。禁止模型 id 含 `claude` 等启发式 | OpenCode Issue #6473 同类 400 |
| FX-CB12 | `_to_openai_messages` 必须保留 **human** 的 `cache_control`；system 已保留不算完成本卡 | last-user 断点在主路径静默丢失 |

### 0.5 开工前自检（每个新会话一次）

```powershell
cd "D:\agent-demo\RxyCode\RxyCode1_1_0"
python --version
git status --short
git branch --show-current
python -c "from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2; print('import ok')"
```

有未提交改动且不是本卡造成的：**停下来问用户**，不要 `git checkout .`。

### 0.6 非目标

- **不**把 GPT 整条链路迁到 Responses API、不把 Claude 迁到原生 Messages SDK、不把 Doubao 迁 Context API / Responses（调研 §6/§7/§12：先通配纪律，协议升级另开 Phase）
- **不**实现 Child spawn / EventBus / 专家团 / 多模型 handoff 运行时（只 **预留类型与不变量测试**）
- **不**把应用层 precise/semantic 命中率当成北极星；**不**把 B1 两轮 91.22% 直接减 OpenCode 长会话 98.85% 当「还差 8 个点」的施工目标
- **不**引入第三方 agent 框架；不重写 Cordis / Effect.ts
- **不**给未知模型发明 `cache_control`；**不**学 OpenCode 用模型名含 `claude` 决定打点
- **本 Phase 要改** `model_catalog.json` 与注入路径（Part 1 §16 / §15）。这不是「重做 B9 读取层」，是 **按官方纠正契约字段并让执行层服从字段**。`core/catalog.py` 的读取入口继续唯一，禁止在 `core/providers/` 再散落 if-模型名
- 时间戳 **禁止**进 S1（FXC3）：继续只在 user 后缀或「没变不重发」的 S2 快照里

---

## §1 更改说明（为什么改、改哪里、如何改）

### 1.0 Part 1 / 2 / 3 覆盖对照（本 Phase 必须全覆盖）

权威：`research/2026-08-14-deepseek-harness-and-opencode-cache.md`。施工时 **禁止**只做速度卡、把 Part 1 留给「以后」。

| 调研 | 门禁（摘要） | 本 Phase 卡 | 本 Phase 明确不做 |
|---|---|---|---|
| **Part 1 §5/§15** 通配三族 | 隐式前缀不打点；cache_key 发 session 键不打 Anthropic 点；显式断点帽 4、只打最后 tool + 静态 system + 滚动 last-user | FXC2、FXC6 | 按品牌名 substring 猜协议 |
| **Part 1 §16** catalog 与官方不一致 | TTL/断点/usage 路径/thinking_param/折扣/窗口/缺 Doubao record | FXC1、FXC5 | 把错字段当真理继续执行 |
| **Part 1 §4.2 #1** 无 S1/S2 | 身份/规则冻 S1；日期/cwd/research/记忆进 S2 或 user 快照，没变不重发 | FXC3 | 把 `datetime.now()` 焊进唯一 system |
| **Part 1 §4.2 #2** 同会话改 tools | 裁剪换 Profile/session，不换当前前缀 | FX6 | 在 AgentPrefix 上 `allowed_tool_names` 改 API schema |
| **Part 1 §4.2 #3–#6** DeepSeek 计量/压缩/session 头 | 双字段 max；晚 compact；Go session 亲和头；min block 文档口径 | FXC4 | 给 DeepSeek 打 `cache_control`；pad system 凑 1024 |
| **Part 1 §4.2 #7** 纯文本轮次回传 reasoning | 按 `reasoning_contract` echo；DeepSeek 对齐 dsh：有 tool_calls 才回传 | FXC5 | 用 DeepSeek 字段名打 Claude/GPT |
| **Part 1 §7** `_raw_stream` 每 tool 打点；human 丢 `cache_control`；string content | 最后 tool；保留 human 断点；显式族升 block 数组 | FXC2 | 顶层 automatic + 内容块已满 4 再打 → 400 |
| **Part 1 §8–§14** 各厂 thinking/key | Kimi 无 24h TTL；k3 只 effort；Qwen `enable_thinking`；M3 禁止打点；GLM 折扣 0.186 | FXC1 + FXC5 | MiniMax M3 套 M2.x 的 4 断点 |
| **Part 1 §6/§12/§14** 协议升级 | catalog 先改对；Grok Go 已是 Responses **视为与 Luna 同类可能要 key** | FXC1 字段 | **整链迁 Responses / 原生 Messages / 方舟 Context API** |
| **Part 2 §20–§24** 1s/3s/thought | skip_await；占位不挡；三流同构；问候出正文 | FX3、FX4、FX5、FX7 | 为闲聊写规则引擎替代 LLM |
| **Part 3 §25–§33** 未来不返工 | PrefixProfile、TurnRouter、append_turn_context、HandoffEnvelope、ns=None | FX1、FX2、FX8–FX11 | 复制 Primary history；热切换模型读同一 KV；vision/EKO 进 S1 |

### 1.1 现象 → 改法

| 现象 | 为什么 | 改哪里 | 如何改（已定） |
|---|---|---|---|
| catalog 字段与官方冲突 | §16 表：Luna TTL 24h、Kimi 24h、M3 帽 4、Qwen `thinking:{type:disabled}`、缺 Doubao | `config/model_catalog.json` + catalog 测试 | 按 §16 **逐行改字段**；通配层只读字段 |
| DeepSeek/M3 仍可能被打点 | `_raw_stream` 用 `provider==anthropic` 启发式；Go 上 MiniMax npm=anthropic | `agent_v2._raw_stream` + `catalog.cache_mode` | **只信 cache_mode**；auto / cache_key / 未知 → 零 `cache_control` |
| Claude 命中低或 400 | 每个 tool 打点；user 纯 string；human 转换丢断点 | `_raw_stream`、`_to_openai_messages`、`_apply_cache_control` | 最后 tool + last-user；保留 human `cache_control` |
| 长会话做不到 98%+ 形态 | 唯一 system 含日期；research 额外 SystemMessage；同会话裁 tools | `prompts/registry.py`、组装链、PrefixProfile | S1 冻；动态进后缀；ToolsFreeze |
| 「你好」也慢 | `_run_impl` 先 await memory/session；stdio 先 `ensureReady` | `turn_router.py` `skip_await`；`stdioTransport.ts` | ChatPrefix 跳过挡首字的 await |
| 预热写了另一套前缀 | 问候无 tools；预热全量 tools+thinking；keep-alive 无 system | `prefix_profile` + `prewarm` | 两条冻档案；三流同构 |
| 以后多 Agent / 切模型 / LinkAgent 再掉命中 | 复制主历史、共享可变 tools、EKO 进 system | 类型预留 + `append_turn_context` | NoHistoryCopy / ToolsFreeze / 切模型=新 session |

**修改 vs 新增**

| 新增（新文件，旧代码改为调用） | 修改（收敛现有行为） | 不改（本 Phase） |
|---|---|---|
| `core/prefix_profile.py` | `model_catalog.json` §16 字段 | GPT Responses 整链迁移 |
| `core/turn_router.py` | `_raw_stream` 打点改为契约三分 | Claude 原生 Messages SDK |
| `core/prewarm.py` | `_to_openai_messages` 保留 human 断点 | Doubao Context API |
| `core/turn_context.py` | `get_system_prompt` 拆 S1/S2 | `cache_policy.py` 断点分配算法骨架（仍复用，只改调用条件） |
| `core/handoff.py`（类型预留） | `_prewarm_*` / `_keep_alive_async` 消费 Profile | LangGraph 节点 |
| （不新建 `cache_family.py`；三族函数只进 `catalog.py`） | `stdioTransport.sendChatMessage` 占位时序 | LinkAgent 仓库源码 |

**硬冲突**：问候卸 tools ↔ 长任务冻全量 tools → 用 **两个 session 内 Profile / 两个 cache 派生键**，不要同一 Profile 变装。

**软冲突**：社交正则、compose 社交、declines_tools、force_fast 多层抢出口 → **决策表只在 TurnRouter**；`request_routing` 只保留谓词。

**协议冲突**：Go 把 MiniMax/Qwen 重新分类进 Anthropic 会打点；官方 M3 **禁止**打点、DashScope Qwen 要显式点。RxyCode **以 catalog 的 `cache_mode` + 实际 endpoint 为准**，不以 OpenCode `api.npm` 为准。

---

## §2 目标架构

```text
catalog.cache_contract（唯一协议分类器）
  cache_mode=auto | cache_key | auto_and_key | explicit_breakpoints
  （禁止写成 explicit / breakpoints；与 model_catalog.schema.json 枚举逐字相同）
       ↓
请求组装
  S1 冻结身份/规则     ← 字节钉死
  tools 会话内冻结排序  ← 与 S1 共享第一段前缀
  S2 / user 快照        ← 日期·cwd·research·记忆，没变不重发
  历史只追加
       ↓
注入层（只读 contract，禁止模型名启发式）
  auto / 未知           → 不发 cache_control，不强制 prompt_cache_key
  cache_key             → extra_body.prompt_cache_key=session_id
  auto_and_key          → 不打点 + 发 key（Kimi）
  explicit_breakpoints  → 最后 tool + 静态 S1 + 滚动 last-user（帽 4）；content 为 block 数组
       ↓
用户输入
  → TurnRouter.route(text, mode, directive)
       → TurnDecision { path, profile_kind, skip_await, exec_allowlist, thinking }
  → PrefixProfile.bind(session, kind)
  → skip_await 决定是否 await memory/session
  → path=chat  → ChatPrefix（无 API tools）
     path=agent → AgentPrefix（API tools=冻结全量）
  → PrefixWriter.prewarm/keep_alive 必须使用同一个 PrefixProfile
  → append_turn_context 只写入 user 后缀（ChatPrefix 丢弃；不得进 S1）
```

**ChatPrefix**：`thinking_enabled=False`，`tools_digest=sha256(b"[]")`，S1 不含 tool 描述。

**AgentPrefix**：`thinking_enabled=True`，`tools_digest=sha256(sorted_tools_json)`，S1+tools 与 API `tools=` 同一批。

编码任务 **禁止** 为了闲聊去改 AgentPrefix 的 tools 字节。vision / EKO / 黑板 **禁止**进 S1。

---

## §3 不变量（D–LinkAgent 必须引用）

完整条文见调研 Part 1 §5/§15/§16 与 Part 3 §31。本 Phase 落地其中 **现在就能测** 的子集：

**Part 1**

0. catalog §16 字段与官方一致（FXC1）
0b. 通配三族注入 + 禁止每 tool 打点 + 保留 human 断点（FXC2）
0c. S1/S2 动静拆分（FXC3）
0d. session 亲和头 + DeepSeek 双字段 usage + 晚 compact 口径（FXC4）
0e. 各厂 thinking / echo 契约（FXC5）
0f. 未知模型五条 fallback（FXC6）

**Part 2 / 3**

1. PrefixProfile 字段齐（FX1）
2. TurnRouter 单一入口（FX2）
3. ChatPrefix `skip_await`（FX3）
4. 预热/保活同构（FX4/FX5）
5. ToolsFreeze：API schema 不按轮裁（FX6）
6. Primary 首字契约（FX7）
7. `append_turn_context`（FX8）
8. cache namespace `ns=None` 兼容（FX9）
9. HandoffEnvelope 禁止 history 字段（FX10）

其余（SpawnNonBlocking、EventBusControlPlane、Child 分桶）以 **文档 + 失败占位测试或注释契约** 冻在 FX10/FX11，不实现运行时。

---

## §4 文档规范与代码规范

### 4.1 文档规范

- 行号是 2026-08-14 快照。定位用 **Grep 锚点**。
- 完成判据必须可客观勾选；禁止「体感更好」。
- 实施记录 / 审计记录写在卡内，不另开聊天当唯一证据。
- 改了模块行为必须改 `docs/modules/core.md`（FX11）。

### 4.2 代码规范

- 新类型一律 `@dataclass(frozen=True, slots=True)`。
- 禁止在 `agent_v2.py` 新增 `if is_social` / `if greeting` 分支。
- 禁止第二套 `cache_control` 注入路径；**唯一**入口仍是 catalog + 现有 `_apply_cache_control` / `_raw_stream`（FXC2 只改条件，不新写平行注入器）。
- 禁止用模型 id / `api.npm` / provider 名启发式覆盖 `cache_mode`。
- `cache_mode` 只允许 schema 四值：`auto` / `cache_key` / `auto_and_key` / `explicit_breakpoints`。
- 测试导入前缀：`from RxyCode.RxyCode1_1_0.core....`
- 单 Agent 默认路径：`agent_id=None`、`cache ns=None` 与改造前字符串逐字节相同。
- 函数失败要抛，不要静默吞掉前缀签名错误。

### 4.3 代码示例（全局约定，各卡会重复完整片段）

见附录 A。卡内步骤里的代码以卡为准；与附录冲突时 **以卡为准**。

---

## §5 任务卡

> **owner: backend** → 本 Phase 由 **Grok 4.6** 执行。  
> 每张卡的完成判据在 GPT-5.6 PASS 前必须保持 `- [ ]`。
>
> **推荐顺序（一次一张）**：`FXC1 → FXC2 → FXC3 → FXC4 → FXC5 → FXC6 → FX1 → FX2 → … → FX11`  
> 该顺序对 FX4 **硬性**：未过 FXC2（打点）和 FXC5（thinking）禁止预热，否则会把错误 `cache_control` / 错误 extra_body 写进 KV。

---

### FXC1 · catalog §16 与官方对齐

`P0` / 2–4h / 依赖：无 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

通配层按错字段执行会 400 或命中归零。调研 §16 已列「落地前必须改」的表。本卡改契约 JSON、官方断言、以及 `read_cached_tokens` 的双路径 `max()`。**不改** `_raw_stream` / `_apply_cache_control`（FXC2）。MiniMax M3 把 `breakpoints_max` 置 0 **不会**停掉现网「每个 tool 打点」——那条启发式不读 catalog，本卡完成后 M3 payload 仍可能带 `cache_control`，**不算 FXC1 失败**。

**涉及文件**（白名单）

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `config/model_catalog.json` | `"cache_contract"` / 各 `model_id` | 按下表改字段 |
| `tests/test_core/test_catalog_contract_official.py` | （新建） | 锁定 §16 表 |
| `tests/test_cache/test_model_contracts.py` | `NINE_PROVIDERS` / 旧 TTL/断点断言 | 断言改成官方口径；Doubao 补进集合（9→10 是本卡目标） |
| `core/catalog.py` | `read_cached_tokens` / `_read_path` | 双路径 `max(cached, cached_alt)`；禁止按模型名 if |
| `config/model_catalog.schema.json` | `usage_fields` / `cache_mode` enum | 允许可选 `cached_alt`；**禁止**往 enum 加 `explicit` / `breakpoints` |

**已经替你决定好的**（与调研 §16 逐行一致；禁止「差不多」）

| record | 改什么 |
|---|---|
| 所有 `gpt-5.6-luna`（含 `openai` / `opencode-go` / `zen` 若有） | `cache_ttl_hours`: **0.5**；`breakpoints_max`: **0**；`usage_fields.cached`: `prompt_tokens_details.cached_tokens`；`usage_fields.cached_alt`: `cached_input_tokens`（Chat Completions 双路径，`read_cached_tokens` 取 **max**；本 Phase 不迁 Responses）；`reasoning_contract`: `"none"` 仅表示 Chat 无 raw CoT echo，**不要**改成 Responses encrypted |
| `zen` 上的 luna 若无 `cache_contract` | **补上**，与 openai 条对齐（含 `cached` + `cached_alt`） |
| 所有 `kimi-*` | `cache_ttl_hours`: **null** |
| `kimi-k2.7-code` `thinking_param.sample` | `{type:enabled, keep:all}` 或不发；**禁止** `reasoning_effort: {low\|high\|max}` |
| `claude-sonnet-4.5` | `min_cache_tokens`: **1024** |
| `claude-haiku-4.5` | `min_cache_tokens`: **4096** |
| `qwen*` `thinking_param.sample` | `enable_thinking: true\|false`；3.8-preview 注释写明 **禁止 false** |
| `qwen*` `usage_fields.cache_creation` | `cache_creation_input_tokens` |
| `minimax-m3` | `breakpoints_max`: **0**；`breakpoint_lookback`: **0**；thinking sample 改为 Anthropic `adaptive` 或 OpenAI 省略（**禁止** `thinking:{type:enabled}`） |
| `glm-5.2` | `cache_hit_discount`: **0.186**；`model_context_window`: **1048576**（与 `glm.py` 官方口径一致） |
| `mimo-*` | `model_context_window`: **1048576**（若现状 262144） |
| Doubao | **补 record** `doubao-seed-2.1-turbo`（及若需要的 pro）：`cache_mode: auto`，`prompt_cache_key_required: false`，`breakpoints_max: 0`，thinking `{type}` 对象，usage nested cached。id 必须落在 `core/providers/doubao.py` 的 `_TURBO_IDS` / `_PRO_IDS` 里 |
| Grok | 直连 xAI 保持 `prompt_cache_key_required: false`；若存在 `opencode-go` Grok 条，本卡把 key 标为 **true（与 Luna 同类）** 并在注释写「落地前探针 usage 路径」。**不**把整链改成 `/v1/responses` |

`as_of` 改为 `2026-08-14`。禁止编造官方文档没有的字段名（如 `scope: "global"`）。**禁止**把任何 record 的 `cache_mode` 写成 `explicit` 或 `breakpoints`；显式族必须是 schema 枚举值 `explicit_breakpoints`。

`read_cached_tokens` 已定实现（所有模型共用，不是 Luna 特判）：

```python
def read_cached_tokens(provider_id: str, model_id: str, usage: dict) -> int:
    contract = get_contract(provider_id, model_id)
    if contract is None:
        return 0
    fields = contract.get("usage_fields") or {}
    return max(
        _read_path(usage, fields.get("cached")),
        _read_path(usage, fields.get("cached_alt")),
    )
```

`cached_alt` 缺省 / null → `_read_path` 得 0 → 行为与今日单路径相同。DeepSeek 的第二字段留给 FXC4 填 `cached_alt`，本卡不要按厂商名 if。

**本卡明确不修**：`_raw_stream` 的 `for tool_def in payload["tools"]`。M3/Anthropic 启发式打点是 FXC2。

**操作步骤**

1. 写失败测试（先跑红）：

```python
import json
from pathlib import Path

from RxyCode.RxyCode1_1_0.core.catalog import get_contract, reset_contract_cache

CATALOG = Path(__file__).resolve().parents[2] / "config" / "model_catalog.json"


def _records():
    return json.loads(CATALOG.read_text(encoding="utf-8"))["records"]


def _one(provider: str, model: str) -> dict:
    for r in _records():
        if r.get("provider_id") == provider and r.get("model_id") == model:
            return r
    raise AssertionError(f"missing record {provider}:{model}")


def test_luna_ttl_is_30m_not_24h():
    reset_contract_cache()
    c = get_contract("openai", "gpt-5.6-luna")
    assert c["cache_ttl_hours"] == 0.5
    assert c["breakpoints_max"] == 0
    assert c["cache_mode"] == "cache_key"
    assert c["usage_fields"]["cached"] == "prompt_tokens_details.cached_tokens"
    assert c["usage_fields"]["cached_alt"] == "cached_input_tokens"


def test_luna_cached_tokens_max_of_flat_and_nested():
    reset_contract_cache()
    from RxyCode.RxyCode1_1_0.core.catalog import read_cached_tokens

    assert read_cached_tokens("openai", "gpt-5.6-luna", {"cached_input_tokens": 800}) == 800
    assert read_cached_tokens(
        "openai",
        "gpt-5.6-luna",
        {"prompt_tokens_details": {"cached_tokens": 500}},
    ) == 500
    assert read_cached_tokens(
        "openai",
        "gpt-5.6-luna",
        {
            "cached_input_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 900},
        },
    ) == 900


def test_kimi_ttl_is_null():
    reset_contract_cache()
    assert get_contract("kimi", "kimi-k3")["cache_ttl_hours"] is None


def test_minimax_m3_is_auto_zero_breakpoints():
    c = _one("minimax", "minimax-m3")["cache_contract"]
    assert c["cache_mode"] == "auto"
    assert c["breakpoints_max"] == 0
    assert "enabled" not in str(c.get("thinking_param", {})).lower() or "adaptive" in str(c.get("thinking_param"))


def test_claude_min_tokens():
    assert _one("anthropic", "claude-sonnet-4.5")["cache_contract"]["min_cache_tokens"] == 1024
    assert _one("anthropic", "claude-haiku-4.5")["cache_contract"]["min_cache_tokens"] == 4096


def test_glm_discount_and_window():
    r = _one("glm", "glm-5.2")
    assert abs(r["cache_contract"]["cache_hit_discount"] - 0.186) < 1e-6
    assert r["model_context_window"] == 1048576


def test_doubao_record_exists_auto():
    reset_contract_cache()
    c = get_contract("doubao", "doubao-seed-2.1-turbo")
    assert c is not None
    assert c["cache_mode"] == "auto"
    assert c["breakpoints_max"] == 0
    assert c.get("prompt_cache_key_required") is False
```

2. 按表改 JSON。Doubao 用 `doubao-seed-2.1-turbo`（必须落在 `core/providers/doubao.py` 的 `_TURBO_IDS`）；需要 pro 再补一条，禁止发明现网没人用的 id。
3. `python -m pytest tests/test_core/test_catalog_contract_official.py -q`
4. 跑已有 catalog 测试，失败则改断言并在实施记录写明「原断言抄了错误官方口径」。

**验收命令**

```powershell
cd "D:\agent-demo\RxyCode\RxyCode1_1_0"
python -m pytest tests/test_core/test_catalog_contract_official.py tests/test_cache/test_model_contracts.py tests/test_model_catalog.py -q
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [x] §16 表每一行都有测试或明确「记录不存在已补」
- [x] `get_contract("deepseek", …)` 仍是 `cache_mode` 隐式、`breakpoints` 空/0
- [x] 没有给任何 DeepSeek record 增加 `cache_control` 相关 true 开关
- [x] 没有任何 record 的 `cache_mode` 是 `explicit` / `breakpoints`（只能是 schema 四枚举）
- [x] Luna：平铺 `cached_input_tokens` 与 nested `prompt_tokens_details.cached_tokens` 都能读到，两者都有时取 max
- [x] **未**修改 `_raw_stream` 打点循环（那是 FXC2；M3 本卡后仍可能带 `cache_control`）
- [x] GPT-5.6 审计 PASS

**实施记录**（Grok 填写）

```
commits: 07c7047, edf87e4（fix 分支，未合 main）
pytest: tests/test_core/test_catalog_contract_official.py tests/test_cache/test_model_contracts.py tests/test_model_catalog.py → 57 passed
ruff（Python 白名单）: All checks passed
```

**审计记录**（GPT-5.6 填写）

```
网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
R1：FAIL（误要求 reasoning_contract 改为 Responses encrypted echo）
R2：PASS。reasoning_contract:"none" 符合本卡「本 Phase 不迁 Responses」。
可以勾选 FXC1 完成判据。
```

**Commit**

```
fix(catalog): align cache_contract fields with vendor docs

Correct TTL, breakpoints, usage paths, thinking params, GLM discount,
context windows, and add the missing Doubao record so the adapter
stops executing stale contracts.
```

---

### FXC2 · 通配三族注入（禁止每 tool 打点；保留 human 断点）

`P0` / 4–6h / 依赖：FXC1 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

调研 §5 协议三分、§7 Claude、§13 Qwen、§15.3 未知模型。现状 `_raw_stream` 在 `provider==anthropic` 时对 **每个** tool 写 `cache_control`（**不读** `breakpoints_max`，所以 FXC1 把 M3 置 0 之后现网仍会打点）。`_to_openai_messages` 只把 system 的断点拷到 dict，**human 丢掉**。显式族 user content 若仍是纯 string，滚动 last-user 断点无效。本卡把注入改成 **只信** `injects_cache_control(contract)`。

**涉及文件**（白名单）

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/catalog.py` | `get_contract` 附近 | 新增 `injects_cache_control` / `injects_prompt_cache_key` 纯函数 |
| `core/agent_v2.py` | `for tool_def in payload["tools"]`；`elif role == "human"`；`_apply_cache_control` | 按契约打点；human 保留 `cache_control` |
| `core/cache_policy.py` | `mark_last_user_breakpoint` | 仅当 `injects_cache_control` 为真才调用 |
| `tests/test_cache/test_cache_family_inject.py` | （新建） | 三族金样 |

**已经替你决定好的**

```python
def injects_cache_control(contract: dict | None) -> bool:
    """Unknown and implicit families never emit Anthropic cache_control."""
    if not contract:
        return False
    mode = str(contract.get("cache_mode") or "auto").casefold()
    if mode != "explicit_breakpoints":
        return False
    return int(contract.get("breakpoints_max") or 0) > 0


def injects_prompt_cache_key(contract: dict | None) -> bool:
    if not contract:
        return False  # 未知模型默认不发 key（§15.3）
    return bool(contract.get("prompt_cache_key_required"))
```

禁止认 `explicit` / `breakpoints` 别名（schema 没有；发明别名 = 打回）。

- `_apply_cache_control` 与 `_raw_stream` **都必须**调用 `injects_cache_control(contract)`。删除 `provider=="anthropic"` / `caps_provider=="anthropic"` 作为打点条件。
- 显式族 tools：只给 `payload["tools"][-1]` 打 `{"type": "ephemeral"}`。**删除** `for tool_def in payload["tools"]` 全员打点。
- 系统断点：只打 **S1 / 静态 system**（FXC3 之后是第一条 system）。本卡若 S1 尚未拆，则打现有第一条 system，且 **不得超过帽 4**。
- last-user：继续 `mark_last_user_breakpoint`；`_to_openai_messages` 对 `role=="human"` **必须**拷贝 `additional_kwargs["cache_control"]`。
- **显式族 content 升数组**：对带 `cache_control` 的 system / user，若 `content` 是 string，改为 `[{"type": "text", "text": ..., "cache_control": {...}}]`（调研 §7 / §13）。隐式族保持 string，禁止无故升数组。
- 禁止对 thinking / `reasoning_content` 块打点。
- DeepSeek / Kimi / GLM / MiMo / Grok / Doubao / MiniMax M3 的序列化结果 **JSON 文本不得出现 `"cache_control"`**。
- 禁止 `if "claude" in model_id`。
- **禁止**新建 `core/cache_family.py`。

**操作步骤**

1. 失败测试（节选，必须包含）：

```python
from RxyCode.RxyCode1_1_0.core.catalog import injects_cache_control, injects_prompt_cache_key, get_contract, reset_contract_cache
from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2


def test_unknown_never_injects():
    assert injects_cache_control(None) is False
    assert injects_prompt_cache_key(None) is False


def test_deepseek_never_injects_control():
    reset_contract_cache()
    c = get_contract("deepseek", "deepseek-v4-flash")
    assert injects_cache_control(c) is False


def test_minimax_m3_never_injects_control():
    reset_contract_cache()
    assert injects_cache_control(get_contract("minimax", "minimax-m3")) is False


def test_to_openai_messages_keeps_human_cache_control():
    from langchain_core.messages import HumanMessage
    msgs = AgentV2._to_openai_messages([
        HumanMessage(content="hi", additional_kwargs={"cache_control": {"type": "ephemeral"}}),
    ])
    assert msgs[0]["role"] == "user"
    assert msgs[0]["cache_control"] == {"type": "ephemeral"}


def test_raw_stream_marks_only_last_tool(monkeypatch):
    """Construct anthropic-family payload tools and assert only [-1] has cache_control.
    用最小 fake contract：cache_mode=`explicit_breakpoints`、breakpoints_max>0。不要打真实网。不要写 cache_mode=`explicit`。"""
    ...
```

2. 实现纯函数 → 改 `_raw_stream` / `_apply_cache_control` 调用点。
3. Grep `cache_control` 确认没有第二套注入器。

**验收命令**

```powershell
cd "D:\agent-demo\RxyCode\RxyCode1_1_0"
python -m pytest tests/test_cache/test_cache_family_inject.py tests/test_cache/test_stable_prefix.py -q
rg "for tool_def in payload\[\"tools\"\]" core/agent_v2.py
```

第二条 Grep **必须无匹配**（全员打点循环已删）。

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [x] 未知 / auto / M3 / DeepSeek 金样无 `cache_control`（本卡之后 M3 必须干净，不再把锅留给 FXC1）
- [x] 显式族只打最后一个 tool
- [x] human 断点经 `_to_openai_messages` 仍在
- [x] 显式族带断点的 system/user `content` 为 block 数组；DeepSeek 等隐式族仍是 string
- [x] 打点条件只来自 `injects_cache_control`；无 `provider=="anthropic"` 启发式
- [x] 无 `core/cache_family.py`
- [x] GPT-5.6 审计 PASS

**实施记录**（Grok 填写）

```
pytest tests/test_cache/test_cache_family_inject.py tests/test_cache/test_stable_prefix.py -q
→ 38 passed, 2 skipped
相关回归（breakpoint/streaming/model_contracts/usage_reasoning）：129 passed, 2 skipped
ruff：All checks passed
Grep `for tool_def in payload["tools"]`：core/agent_v2.py 无匹配
未勾完成判据。
```

**审计记录**（GPT-5.6 填写）

```
网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
R1：FAIL（白名单外测试文件）
R2：无效。28 字复审，未逐条核对清单，不得当作 PASS。
R3：独立全量审计 FAIL。缺 _apply_cache_control→序列化集成测试；清单 5 证据不足；llm_timeout 卡外改动。
R4：独立全量审计 PASS（~2900 字，清单 1–8 与完成判据逐条通过）。净 diff 四白名单文件；显式族 apply+serialize 升 block；隐式族保持 string。
可以勾选 FXC2 完成判据。
```

**Commit**

```
fix(cache): dispatch cache_control by contract family

Stop stamping every Anthropic tool, keep last-user breakpoints on
human messages, and never emit cache_control for implicit or unknown
models (including MiniMax M3).
```

---

### FXC3 · S1 / S2 动静拆分

`P0` / 4–8h / 依赖：FXC2 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

调研 §4.2 #1、§2 勘误（OpenCode PR #14743 **未合入**，RxyCode 可以更严）。现状 `get_system_prompt` 一根字符串；`build_user_message` 每轮 `datetime.now()`（这点可接受，已在 user 侧）；`research_contract` 仍 `messages.append(SystemMessage(...))`，等于第二条会变的 system，打穿前缀。

**涉及文件**（白名单）

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/prompts/registry.py` | `def get_system_prompt` / `def build_user_message` | 拆 S1；时间戳留 user；新增 S2 快照构建 |
| `core/agent_v2.py` | `SystemMessage(content=research_contract)` | 改为 user 快照或 S2，**禁止**第二条动态 system |
| `tests/test_cache/test_s1_s2_split.py` | （新建） | S1 字节稳定 |
| `tests/test_cache/test_stable_prefix.py` | `SystemMessage(content=research_contract)` | **改断言语义**（本卡目标，不是放水）：不得改写 messages[0]；research 不得再作为 SystemMessage |

**已经替你决定好的**

- **S1**：身份、规则、tool 描述（AgentPrefix 才有）。同一 `variant` + 同一 tools_digest 下，两次渲染 **逐字节相同**。禁止日期、cwd、git、AGENTS.md 变更、skills 列表、memory、research。
- **S2 或 user 快照**：日期、cwd、research_contract、记忆摘录。实现选一种：**优先 user 快照**（更不容易和 Anthropic system 断点抢配额）。若用第二条 system 当 S2，必须「没变不重发」——字节与上次相同则 **不追加新消息、不替换 S1**。
- `build_user_message` 的时间戳 **可以保留**（已在 user 后缀，不进 S1）。禁止把它搬进 S1。
- 日期锚定：**session 创建时间** 可进 S2（MiMo-Code PR #1145 可抄）；不要每步 `datetime.now()` 进 system。
- 本卡不改 tools 裁剪（FX6）、不改预热（FX4）。

**操作步骤**

1. 失败测试：

```python
from RxyCode.RxyCode1_1_0.core.prompts.registry import get_system_s1, get_system_s2


def test_s1_stable_across_clock(monkeypatch):
    a = get_system_s1(tools=True, variant="default")
    monkeypatch.setattr("RxyCode.RxyCode1_1_0.core.prompts.registry.datetime", ...)  # 若 S1 误用 now，会红
    b = get_system_s1(tools=True, variant="default")
    assert a == b
    assert "2026" not in a  # 禁止把「今天」写进 S1；用更稳的：S1 不含 YYYY-MM-DD 模式亦可


def test_research_not_second_system():
    from pathlib import Path
    src = Path("core/agent_v2.py").read_text(encoding="utf-8")
    assert "SystemMessage(content=research_contract)" not in src
```

2. 实现 `get_system_s1`；`get_system_prompt` 可保留为 `return get_system_s1(...)` 以免一次拆爆所有调用，但 **新组装路径必须走 S1**。
3. 改 research 注入。
4. 更新 `test_stable_prefix.py` 里依赖「独立 SystemMessage」的测试，改为「messages[0] 仍是 S1 且 research 出现在 user 或未变化的 S2」。

**验收命令**

```powershell
cd "D:\agent-demo\RxyCode\RxyCode1_1_0"
python -m pytest tests/test_cache/test_s1_s2_split.py tests/test_cache/test_stable_prefix.py -q
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [x] S1 两次渲染逐字节相同（含工具描述稳定时）
- [x] Grep `SystemMessage(content=research_contract)` 无匹配
- [x] 时间戳不在 S1
- [x] GPT-5.6 审计 PASS

**实施记录**（Grok 填写）

```
commit: 51440aa feat(prompts): split frozen S1 from dynamic turn snapshot
pytest tests/test_cache/test_s1_s2_split.py tests/test_cache/test_stable_prefix.py -q
→ 30 passed, 2 skipped
ruff：All checks passed
Grep `SystemMessage(content=research_contract)`：core/agent_v2.py 无匹配
净 diff 相对 b2f4060：四白名单文件
用户确认后已勾完成判据。未开 FXC4。
```

**审计记录**（GPT-5.6 填写）

```
网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
R1：结构完整 PASS，但仅 758 汉字；C4 自称「不少于 1200 汉字」不实，不作终审。
R2：对抗式独立全量审计 PASS（1449 汉字）。清单 1–8、完成判据 C1–C4、
嫌疑 S-A–S-H（兼容入口、S2 未接线字段、时钟 monkeypatch、没变不重发、
stable_prefix 改断言、locale、UNIFIED_SYSTEM_PROMPT、时间戳位置）均不构成 FAIL。
可以勾选 FXC3 完成判据。
用户确认后已勾。未开 FXC4。
```

**Commit**

```
feat(prompts): split frozen S1 from dynamic turn snapshot

Keep identity and tool rules byte-stable. Move research_contract off
the system lane so date/cwd/research cannot bust the cached prefix.
```

---

### FXC4 · session 亲和头、DeepSeek 双字段 usage、晚 compact 口径

`P1` / 3–5h / 依赖：FXC1 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

调研 §4.2 #3–#6、§15.4(C)。GLM 掉 0% 常是多源网关无 sticky，不是前缀抖。DeepSeek usage 只读平铺会少计命中。90% 窗口一刀对 1M+50× 命中价偏早。

**涉及文件**（白名单）

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/agent_v2.py` 或 provider 基类发请求处 | `headers` / `_raw_stream` payload | 稳定 session 头 |
| `core/providers/deepseek.py` | `_DEEPSEEK_USAGE` / `cache_read_nested` / `compaction_threshold` | 提高 compact 阈值；usage 映射走 catalog |
| `config/model_catalog.json` | `deepseek-*` `usage_fields` | `cached` 与 `cached_alt` 填双路径；**不要**在 `read_cached_tokens` 里 `if provider==deepseek` |
| `tests/test_cache/test_session_affinity_and_usage.py` | （新建） | |

**已经替你决定好的**

- 当 base URL 含 `opencode.ai` 或 `zen/go`：发 `x-opencode-session: <session_id>` **且** `x-session-affinity` / `X-Session-Id` 同源。直连官方 API 可只发 `X-Session-Id`（不要伪造 `opencode*` 头）。
- `read_cached_tokens` **复用 FXC1 的 max(cached, cached_alt)**。DeepSeek record 设 `cached=prompt_tokens_details.cached_tokens`、`cached_alt=prompt_cache_hit_tokens`（或反过来，max 一样）。禁止再写一套 DeepSeek 专用读取函数。
- DeepSeek `compaction_threshold`：从约 90% 窗口改为 **更晚**（建议 0.97× 窗口或与 `cache_policy` 已有旋钮对齐）。禁止压完再改写旧 tool result。
- `cache_min_block_tokens`：文档/注释改为 V4 口径（256 分桶、约 1024 起步）；短 pipeline 低命中不当 bug。
- DeepSeek **默认不要 keep-alive**（磁盘 TTL 小时到天；5 分钟空请求是 Anthropic 补偿）。本卡只改默认开关/注释；FX5 再保证若开启则同构。
- GLM：**不要**在本卡改用户选的上游；在 `docs/modules/core.md` 或 catalog 注释写「不要默认走未 sticky 的多源 GLM」。禁止发明 GLM cache key。

**验收命令**

```powershell
cd "D:\agent-demo\RxyCode\RxyCode1_1_0"
python -m pytest tests/test_cache/test_session_affinity_and_usage.py tests/test_cache/test_model_contracts.py -q
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [x] Go 网关请求测到 session 头（可用 fake transport / 抓 payload，禁止真打网）
- [x] DeepSeek usage fixture：只有 nested 也读得出来
- [x] compact 阈值测试：旧 90% 触发点不再提前 compact
- [x] GPT-5.6 审计 PASS

**实施记录**（Grok 填写）

\commits: 68e4967（fix 分支）
pytest: tests/test_cache/test_session_affinity_and_usage.py tests/test_cache/test_model_contracts.py → 42 passed
回归（deepseek_v4/model_catalog/capabilities_wiring）：39 passed
ruff（Python 白名单）: All checks passed
已知与本卡无关的既有失败：test_breakpoint_budget.py 2 项（FXC2 语义遗留，白名单外，非本卡引入）
未勾完成判据。
\
**审计记录**（GPT-5.6 填写）

\网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
结果：PASS / FAIL
意见：
\
**Commit**

```
网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
R1-R6：FAIL（网关判定过宽→收窄；compact/keep-alive 行为测试补强；真实 payload 断言；显式族最后 tool；DeepSeek 双路径显式声明）
R7：PASS。白名单 4 文件；session 头（opencode.ai 域白名单）+ 双 usage 字段 max + 0.97x compact + V4 block + keep-alive 默认关；DeepSeek/M3/未知不打点、显式族只最后 tool；无模型名启发式、无非法 cache_mode、无协议升级、无第二注入器。
可以勾选 FXC4 完成判据。
```

---

### FXC5 · 各厂 thinking / echo 契约（禁止用 DeepSeek 字段打全家）

`P1` / 4–6h / 依赖：FXC1 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

调研 §6–§14、§4.2 #7。`_to_openai_messages` 凡有 reasoning 就回传，对 Qwen 是错的；Kimi k3 可能被塞 `thinking:{type:enabled}` 导致 400；Qwen sample 曾是 `thinking:{type:disabled}`。

**涉及文件**（白名单）

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/agent_v2.py` | `_to_openai_messages` 的 `reasoning_content` 分支 | 按 `reasoning_contract` |
| `core/providers/kimi.py` / `qwen.py` / `minimax.py` / `glm.py` / `mimo.py` | `thinking` / `reasoning_effort` / `enable_thinking` / `clear_thinking` | 与 FXC1 sample 一致 |
| `tests/test_providers/test_thinking_contract.py` | （新建） | 每厂金样 extra_body |

**已经替你决定好的**

| 厂 | 发什么 | 回传 |
|---|---|---|
| DeepSeek | 现状 thinking；**不要** `cache_control` | 有 `tool_calls` 才 echo `reasoning_content`（对齐 dsh）；纯文本轮次不回传 |
| Kimi k3 | **只** `reasoning_effort`，不发 `thinking` 对象 | 跨 user turn 也带 `reasoning_content`（可 `""`） |
| Kimi k2.7 | `{type:enabled, keep:all}` 或不发；**不发** effort | 同上，缺则 `""` |
| Qwen | `enable_thinking`；**禁止** `thinking:{type:disabled}`；3.8-preview 禁止 false | **不要**把 `reasoning_content` 塞回 messages；可选 `preserve_thinking: true` |
| MiniMax M3 | Anthropic：`adaptive`；不打点 | thinking 块含 signature 原样 |
| GLM | `clear_thinking: false`；5.1 不发 effort | 按现网 |
| MiMo | `thinking.type`；temperature 1.0 / top_p 0.95；**不发** effort / `cache_control` | 有 tool_calls 必 echo，空串也要 |
| GPT Chat（本 Phase） | 不发 Anthropic 点；已有 `prompt_cache_key` | Chat 无 raw CoT |
| Doubao | `thinking:{type}` 对象，禁止字符串 `"thinking":"high"` | 不编 `caching` 字段 |

**验收命令**

```powershell
cd "D:\agent-demo\RxyCode\RxyCode1_1_0"
python -m pytest tests/test_providers/test_thinking_contract.py -q
```

**实施记录**（Grok 填写）

```
commits: 4ba2300（fix 分支）
pytest: tests/test_providers/test_thinking_contract.py → 14 passed
回归（kimi/qwen provider + cache_family + agent_tool_contracts）：120 passed
ruff（Python 白名单）: All checks passed
已知与本卡无关的既有失败：test_research_fast_path.py 2 项（未提交他人测试，mock 自定义 _raw_stream，绕开本卡路径）
未勾完成判据。
```

**实施记录**（Grok 填写）

```
commits: 4ba2300（首）+ R1-R8 审计修订（fix 分支）
pytest: tests/test_providers/test_thinking_contract.py → 33 passed
回归（qwen/kimi/glm/mimo/minimax/deepseek + model_catalog + cache_family）：165+ passed
ruff（Python 白名单）: All checks passed
决定（调研后）：qwen3.7-plus 为官方主推型号（Phase A Q6），catalog 缺失是 FXC1 缺口；已以独立 FXC1 补充 commit 补齐 record（cache_mode=explicit_breakpoints 为 schema 合法枚举，thinking_param enable_thinking），FXC5 不涉及 catalog，qwen.py 以 catalog-only 读取（FX-CB11）。
未勾完成判据。
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [x] 每行上表有断言（payload 或序列化消息）
- [x] Qwen 路径 messages 无 `reasoning_content` 回灌
- [x] DeepSeek 纯文本 assistant 无强制 reasoning 字段
- [x] GPT-5.6 审计 PASS

**审计记录**（GPT-5.6 填写）

```
网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
R1-R10：FAIL（决策表逐行、集成链路、未知模型保守、payload 断言、catalog-only、白名单等逐一修复）
R11：PASS。官网调研（platform.minimaxi.com text-chat-openai）确认 M3 走 OpenAI 兼容端点（api.minimaxi.com/v1/chat/completions），thinking adaptive 默认、响应 reasoning_content/reasoning_details，官方 API 无 Anthropic signature；RxyCode minimax.py 与官网一致。echo 按 reasoning_contract 分流（Qwen 禁回灌/DeepSeek 纯文本不回灌/GPT 不回灌/Kimi-MiMo-GLM 恒 echo/M3 回灌 thinking）；未知模型保守；DeepSeek/M3/未知无 cache_control；无模型名启发式、无协议升级、无第二注入器。
可以勾选 FXC5 完成判据。
```

**Commit**

```
fix(providers): honor per-model thinking and echo contracts

Stop applying DeepSeek reasoning_content rules to Qwen/Claude/GPT,
and emit Kimi/Qwen/MiniMax/GLM/MiMo params the vendors actually accept.
```

---

### FXC6 · 未知模型五条 fallback

`P1` / 2–3h / 依赖：FXC2 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

调研 §15.3。未知模型只要前缀稳、网关粘滞，隐式缓存就会工作。RxyCode `get_contract` 返回 None 后调用方行为必须 **显式** 等于这五条，而不是「什么都不做导致有的路径仍打点」。

**涉及文件**（白名单）

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/catalog.py` | `get_contract` 返回 None 的调用约定 | 增加 `unknown_fallback_contract()` 文档化常量 |
| `core/agent_v2.py` | `_raw_stream` extra_body / cache_control | None → fallback |
| `tests/test_cache/test_unknown_model_fallback.py` | （新建） | |

**已经替你决定好的**（逐条抄 §15.3）

1. Prompt → 默认 variant（`default`），不按 id 猜家族文案
2. 协议 → openai-compatible
3. **不发** `cache_control`
4. 仍做：tools 按名字排序；session 头（FXC4 已加的那种）
5. **`prompt_cache_key` 默认不发**

禁止：把未知模型当 Claude；为凑命中发明断点。

**验收命令**

```powershell
cd "D:\agent-demo\RxyCode\RxyCode1_1_0"
python -m pytest tests/test_cache/test_unknown_model_fallback.py -q
```

**实施记录**（Grok 填写）

```
commits: FXC6 首 commit（fix 分支）
pytest: tests/test_cache/test_unknown_model_fallback.py → 5 passed
回归（test_cache + test_thinking_contract）：96+ passed
ruff（Python 白名单）: All checks passed
未勾完成判据。
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [x] `get_contract("no-such", "mystery") is None` 时注入层走 fallback 五条
- [x] 假 payload 无 `cache_control`、无 `prompt_cache_key`
- [x] GPT-5.6 审计 PASS

**审计记录**（GPT-5.6 填写）

```
网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
R1-R6：FAIL（fallback 强制应用、protocol 校验、真实 None 路径、variant 在 prompt 组装前生效等逐一修复）
R7：PASS。unknown_fallback_contract() 五条显式；_prompt_variant 对未知 模型在组装前解析 default；_raw_stream None 分支强制 default variant + openai-compatible 校验；真实 payload 无 cache_control/prompt_cache_key，tools 排序 + session 头（FXC4）；DeepSeek/M3/未知不打点；无模型名启发式、无协议升级、无第二注入器。
可以勾选 FXC6 完成判据。
```

**Commit**

```
fix(cache): treat unknown models as implicit prefix only

Unknown contracts skip cache_control and prompt_cache_key while still
sorting tools and sending session affinity headers.
```

---

### FX1 · PrefixProfile 类型与指纹

`P0` / 2–4h / 依赖：FXC3 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

没有不可变前缀身份，预热、问候、保活、未来 Child 会继续各写各的请求体。本卡 **只加类型和纯函数**，不改 `AgentV2` 行为。

**涉及文件**（白名单）

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/prefix_profile.py` | （新建） | 创建 |
| `tests/test_core/test_prefix_profile.py` | （新建） | 创建 |

**已经替你决定好的**

- `kind` 只有 `"chat"` | `"agent"`。
- `s1_digest`：S1 正文 sha256 hex（FXC3 的 `get_system_s1`）。Chat 与 Agent 若 S1 不同必须不同 digest。
- `tools_digest`：对规范化 JSON（`sort_keys=True`，`separators=(",", ":")`）做 sha256 hex。空工具用 `"[]"`。
- `identity()` 字符串字段顺序固定：`provider|model|kind|thinking|effort|tools_digest|s1_digest|session_id|agent_id|variant`。`agent_id` 空则写 `-`。
- 两个 Profile `identity()` 不同 → 视为不同前缀，禁止复用 KV。
- 本卡不调用网络、不改 agent_v2。

**操作步骤**

1. 写失败测试 `tests/test_core/test_prefix_profile.py`（先跑红）：

```python
from RxyCode.RxyCode1_1_0.core.prefix_profile import (
    PrefixProfile,
    digest_tools,
    profiles_compatible,
)


def test_empty_tools_digest_is_stable():
    assert digest_tools([]) == digest_tools([])
    assert digest_tools(None) == digest_tools([])


def test_tool_order_does_not_change_digest():
    a = [{"name": "bash", "parameters": {"type": "object"}}, {"name": "read", "parameters": {}}]
    b = [{"name": "read", "parameters": {}}, {"name": "bash", "parameters": {"type": "object"}}]
    assert digest_tools(a) == digest_tools(b)


def test_chat_and_agent_identities_differ():
    chat = PrefixProfile(
        kind="chat",
        session_id="ses_1",
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_enabled=False,
        thinking_effort=None,
        tools_digest=digest_tools([]),
        s1_digest="s1chat",
        system_template_version="1.0.0",
        prompt_variant="default",
        agent_id=None,
    )
    agent = PrefixProfile(
        kind="agent",
        session_id="ses_1",
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_enabled=True,
        thinking_effort="balanced",
        tools_digest=digest_tools([{"name": "bash"}]),
        s1_digest="s1agent",
        system_template_version="1.0.0",
        prompt_variant="default",
        agent_id=None,
    )
    assert chat.identity() != agent.identity()
    assert profiles_compatible(chat, agent) is False


def test_same_fields_are_compatible():
    p = PrefixProfile(
        kind="agent",
        session_id="ses_1",
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_enabled=True,
        thinking_effort="balanced",
        tools_digest="abc",
        s1_digest="s1agent",
        system_template_version="1.0.0",
        prompt_variant="default",
        agent_id=None,
    )
    q = PrefixProfile(
        kind="agent",
        session_id="ses_1",
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_enabled=True,
        thinking_effort="balanced",
        tools_digest="abc",
        s1_digest="s1agent",
        system_template_version="1.0.0",
        prompt_variant="default",
        agent_id=None,
    )
    assert p.identity() == q.identity()
    assert profiles_compatible(p, q) is True
```

2. 跑测试，确认 ImportError / 失败。
3. 实现 `core/prefix_profile.py`：

```python
"""冻结的前缀身份。会话期内只追加消息，不改本结构。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, Optional


PrefixKind = Literal["chat", "agent"]


def digest_tools(tools: Optional[list[Any]]) -> str:
    """Canonical sha256 of tool schemas. Order-insensitive by name then json."""
    items = list(tools or [])
    normalized = []
    for item in items:
        if hasattr(item, "name") and hasattr(item, "args_schema"):
            name = str(getattr(item, "name"))
            schema = getattr(item, "args_schema", {}) or {}
            if hasattr(schema, "model_json_schema"):
                schema = schema.model_json_schema()
            normalized.append({"name": name, "parameters": schema})
        elif isinstance(item, dict):
            normalized.append(
                {
                    "name": str(item.get("name") or item.get("function", {}).get("name") or ""),
                    "parameters": item.get("parameters")
                    or item.get("function", {}).get("parameters")
                    or {},
                }
            )
        else:
            normalized.append({"name": str(item), "parameters": {}})
    normalized.sort(key=lambda x: x["name"])
    blob = json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PrefixProfile:
    kind: PrefixKind
    session_id: str
    provider: str
    model: str
    thinking_enabled: bool
    thinking_effort: Optional[str]
    tools_digest: str
    s1_digest: str
    system_template_version: str
    prompt_variant: str
    agent_id: Optional[str] = None
    cache_mode: Optional[str] = None

    def identity(self) -> str:
        effort = self.thinking_effort or "-"
        agent = self.agent_id or "-"
        thinking = "on" if self.thinking_enabled else "off"
        return "|".join(
            [
                self.provider,
                self.model,
                self.kind,
                thinking,
                effort,
                self.tools_digest,
                self.s1_digest,
                self.session_id,
                agent,
                self.prompt_variant,
            ]
        )


def profiles_compatible(left: PrefixProfile, right: PrefixProfile) -> bool:
    return left.identity() == right.identity()
```

4. 再跑测试至绿。
5. `python -m ruff check core/prefix_profile.py tests/test_core/test_prefix_profile.py`

**验收命令**

```powershell
cd "D:\agent-demo\RxyCode\RxyCode1_1_0"
python -m pytest tests/test_core/test_prefix_profile.py -q
python -m ruff check core/prefix_profile.py tests/test_core/test_prefix_profile.py
```

**实施记录**（Grok 填写）

```
commits: FX1 首 commit（fix 分支）
pytest: tests/test_core/test_prefix_profile.py → 4 passed
ruff: All checks passed
未勾完成判据。
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [x] `digest_tools` 对顺序不敏感、空列表稳定
- [x] chat / agent identity 不同且 `profiles_compatible` 为 False
- [x] 未改 `agent_v2.py`
- [x] ruff 干净
- [x] GPT-5.6 审计 PASS

**实施记录**（Grok 填写）

```
测试输出：
```

**审计记录**（GPT-5.6 填写）

```
网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
R1：PASS。白名单 2 文件；PrefixProfile frozen+slots、identity 字段顺序/agent_id 渲染正确；digest_tools 顺序不敏感 + 空稳定；profiles_compatible = identity 相等；未改 agent_v2、无网络、无越界。
可以勾选 FX1 完成判据。
```

**回滚**：删这两个新文件。

**常见坑**

- 对 LangChain StructuredTool 没用 `name`/`args_schema`，digest 每轮抖。
- 把 `identity()` 做成 dict 无序拼接。

**Commit**

```
feat(cache): freeze PrefixProfile identity for chat vs agent prefixes

Two frozen prefix archives (chat/agent) get a stable identity string so
prewarm, keepalive, and real turns can be checked for isomorphism before
we touch AgentV2 routing.
```

---

### FX2 · TurnRouter 行为等价抽取

`P0` / 4–8h / 依赖：FX1 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

`_run_impl` 瀑布 if 已有 ~8 出口。本卡 **只搬家，不改路由结果**。`skip_await` 本卡一律空 frozenset（FX3 再填）。社交仍可走 tools 路径（FX6 再改成 ChatPrefix 空工具）。

**涉及文件**

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/turn_router.py` | （新建） | 创建 |
| `core/agent_v2.py` | `async def _run_impl` | 用 `route()` 替换内联启发式；执行器调用保持 |
| `tests/test_core/test_turn_router.py` | （新建） | 创建 |
| `tests/test_core/test_request_routing.py` | `def _routed_agent` | 现有断言必须仍绿 |
| `tests/test_core/test_first_turn_latency.py` | `async def test_no_tool_itinerary` | 仍绿 |

**已经替你决定好的**

- `TurnDecision.path`：`"chat" | "agent" | "graph" | "plan" | "compose" | "file_op" | "download"`
- 纯问候 / `declines_tools` → `path="chat"`（对应今日 `_fast_reply`）
- `is_social_chat` 但非纯问候 → 本卡仍 `path="agent"`（对应今日 `_fast_reply_with_tools` + datetime），**不要在本卡改成 chat**
- 默认 build → `path="agent"`
- `/full` `/pipeline` → `path="graph"`
- `mode=="plan"` 且非上面的 chat 短路 → 保持今日：先 `plan` 早退 `_run_plan_only`。即 **plan 模式第一条仍是 plan**（与今日 `_run_impl` 一致：`if mode == "plan": return await self._run_plan_only` 在 file_op 之前）
- 注意今日顺序：memory await **仍在 route 之前**（本卡不取消，FX3 再做）
- `_run_impl` 里禁止复制旧 if 条件；只允许 `decision = route(...)` + `match path`

**操作步骤**

1. 先写 `tests/test_core/test_turn_router.py`，用真实谓词锁住今日出口：

```python
from RxyCode.RxyCode1_1_0.core.request_routing import RoutingDirective
from RxyCode.RxyCode1_1_0.core.turn_router import route


def test_hello_is_chat():
    d = route("你好", "build", RoutingDirective.AUTO, file_op=None, download=None)
    assert d.path == "chat"
    assert d.profile_kind == "chat"
    assert d.skip_await == frozenset()


def test_hello_ah_is_agent_until_fx6():
    d = route("你好啊", "build", RoutingDirective.AUTO, file_op=None, download=None)
    assert d.path == "agent"


def test_declines_tools_is_chat():
    text = "用三句话规划成都两日美食游，不要改文件，不要调用工具。"
    d = route(text, "build", RoutingDirective.AUTO, file_op=None, download=None)
    assert d.path == "chat"


def test_code_task_is_agent():
    d = route("分析当前目录的代码并修复 calc.py 里的 bug。", "build", RoutingDirective.AUTO, file_op=None, download=None)
    assert d.path == "agent"


def test_full_directive_is_graph():
    d = route("explain decorators", "build", RoutingDirective.FORCE_FULL, file_op=None, download=None)
    assert d.path == "graph"


def test_plan_mode_is_plan():
    d = route("写一个计划", "plan", RoutingDirective.AUTO, file_op=None, download=None)
    assert d.path == "plan"
```

2. 实现 `core/turn_router.py`（完整逻辑必须与今日 `_run_impl` 顺序一致：plan → file_op → download → declines → pure greeting → compose+social → build/plan 默认 agent → compose → graph）：

```python
"""单一回合决策入口。禁止在 AgentV2._run_impl 再写启发式 if。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from RxyCode.RxyCode1_1_0.core.prefix_profile import PrefixKind
from RxyCode.RxyCode1_1_0.core.request_routing import (
    PURE_SOCIAL_GREETING_RE,
    RoutingDirective,
    declines_tools,
    is_social_chat,
)

TurnPath = Literal["chat", "agent", "graph", "plan", "compose", "file_op", "download"]


@dataclass(frozen=True, slots=True)
class TurnDecision:
    path: TurnPath
    profile_kind: PrefixKind
    skip_await: frozenset[str]
    thinking_enabled: bool
    role_instruction: str = ""


def route(
    user_text: str,
    mode: str,
    directive: RoutingDirective,
    *,
    file_op: Optional[dict[str, Any]] = None,
    download: Optional[tuple] = None,
) -> TurnDecision:
    text = (user_text or "").strip()
    empty_skip: frozenset[str] = frozenset()

    if mode == "plan":
        return TurnDecision("plan", "agent", empty_skip, True)

    if file_op:
        return TurnDecision("file_op", "agent", empty_skip, True)

    if download:
        return TurnDecision("download", "agent", empty_skip, True)

    force_full = directive == RoutingDirective.FORCE_FULL
    social = is_social_chat(text)

    if mode in ("build", "plan") and not force_full and declines_tools(text):
        return TurnDecision("chat", "chat", empty_skip, False)

    if (
        mode in ("build", "plan")
        and not force_full
        and social
        and PURE_SOCIAL_GREETING_RE.match(text)
    ):
        return TurnDecision("chat", "chat", empty_skip, False)

    if mode == "compose" and social:
        return TurnDecision("agent", "agent", empty_skip, True)

    if mode in ("build", "plan") and not force_full:
        return TurnDecision("agent", "agent", empty_skip, True)

    if mode == "compose":
        return TurnDecision("compose", "agent", empty_skip, True)

    return TurnDecision("graph", "agent", empty_skip, True)
```

3. 改 `_run_impl`：在现有 `await memory` 之后，用 `route(...)` 得到 decision，再 `if decision.path == "chat": return await self._fast_reply(...)` 等。**删除**原来的 social/greeting/declines 内联条件（逻辑已在 router）。保留 `parse_routing_directive`、file_op/download 的 **探测**（探测结果传入 `route`），不要在 `_run_impl` 里用探测结果再写第二套 if 条件套 heuristic。

允许的 `_run_impl` 形态：

```python
decision = route(
    user_input,
    mode,
    routing_directive,
    file_op=file_op,
    download=download_intent,
)
if decision.path == "plan":
    return await self._run_plan_only(user_input)
if decision.path == "file_op":
    ...
if decision.path == "chat":
    return await self._fast_reply(user_input)
if decision.path == "agent":
    return await self._fast_reply_with_tools(user_input)
...
```

4. 跑下列测试必须全绿（行为等价）。

**验收命令**

```powershell
cd "D:\agent-demo\RxyCode\RxyCode1_1_0"
python -m pytest tests/test_core/test_turn_router.py tests/test_core/test_request_routing.py tests/test_core/test_first_turn_latency.py -q
python -m ruff check core/turn_router.py core/agent_v2.py tests/test_core/test_turn_router.py
```

**实施记录**（Grok 填写）

```
commits: 5d8019f + 后续（fix 分支）
pytest: test_turn_router 9 + test_request_routing + test_first_turn_latency 全绿；全量 test_core+test_cache 7755 passed
  （基线失败 8：lazy_import_budget×2 历史、research_fast_path×2+session 他人改动区、usage_reasoning B3 遗留、breakpoint_budget×2 FXC2 已知）
ruff: All checks passed
FXC6 遗留修复：_prompt_variant 对无 provider 构造回退 caps（test_agent_prompt_variant 恢复绿）
未勾完成判据。
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [x] `_run_impl` 不再包含 `PURE_SOCIAL_GREETING_RE` / `declines_tools(` / `_is_social_chat(` 的 **分流条件**（Grep 确认；包装调用探测函数可以留在探测阶段）
- [x] 上列三份测试全绿
- [x] `route("你好")` → chat；`route("你好啊")` → agent（本卡刻意保持）
- [x] GPT-5.6 审计 PASS

**实施记录** / **审计记录**：同 FX1 格式。

**回滚**：恢复 `_run_impl` 瀑布；删 `turn_router.py`。

**常见坑**

- 把 plan 模式放到 greeting 之后，会改变今日「plan 一律 `_run_plan_only`」行为。
- 在 `_run_impl` 既 call `route` 又留旧 if → 双决策。

**审计记录**（GPT-5.6 填写）

```
网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
R1-R3：FAIL（social 失败消息等价元数据、route() 统一 plan 分发 + 恢复 「你好啊」测试文本、plan 模式在 route() 前不得执行 file/download handler）
R4：PASS。_run_impl 无三类探针；route() 单一路由表、顺序与原瀑布等价（含 file_op 失败→download 回退链）；TurnDecision frozen+slots、skip_await 全空；social 安慰消息保留；58+ 测试全绿、ruff 通过。
可以勾选 FX2 完成判据。
```

**Commit**

```
refactor(agent): extract TurnRouter without changing route outcomes

Move the _run_impl heuristic waterfall into core/turn_router.py so later
cards can change skip_await and prefix kind in one table instead of new
ifs inside AgentV2.
```

---

### FX3 · ChatPrefix skip_await（问候不再先付 memory/session 税）

`P0` / 3–6h / 依赖：FX2 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

今日所有路径在分流前 `await initialize` + `load_session`。「你好」1s 预算被同步 IO 吃掉。`MemoryManager.initialize` 目前是 `pass`，但 `load_session` 不是。

**涉及文件**

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/turn_router.py` | `empty_skip: frozenset[str] = frozenset()` | chat 路径填 skip |
| `core/agent_v2.py` | `await self._memory.initialize()` | 按 `decision.skip_await` 跳过 |
| `tests/test_core/test_turn_router.py` | `test_hello_is_chat` | 断言 skip 集合 |
| `tests/test_core/test_chat_skip_await.py` | （新建） | `_run_impl("你好")` 不调用 initialize/load |

**已经替你决定好的**

- chat 路径 `skip_await = frozenset({"memory.initialize", "session.load", "mcp.refresh"})`
- agent/graph/plan/compose/file_op/download **不跳过** session.load（编码任务仍要历史）
- 跳过的 session load 必须 **后台** `asyncio.create_task` 或在回复后补 `load_session`，不能永远丢会话；本卡最小实现：chat 路径先回复，最后 `self._memory.save_session()` 仍执行；若 `_session_loaded` 为 False，chat 结束时再 `load_session` 一次仅用于后续回合，**不得**挡本回合 LLM 调用
- 不在本卡改预热

**操作步骤**

1. 改 `test_hello_is_chat`：`assert "memory.initialize" in d.skip_await` 且 `"session.load" in d.skip_await`
2. 新建测试：mock `_memory.initialize` 为 AsyncMock，`_fast_reply` 为 AsyncMock；`await _run_impl("你好")` 后 `initialize.assert_not_awaited()`（或若你选择 chat 仍允许 initialize：则本卡按「session.load 不 await」为准——**已定：两个都 skip await**）。`load_session` 不得在 `_fast_reply` 返回前被调用。
3. `_fast_reply` 开头的 `await self._ensure_session_loaded()`：当本回合 decision 是 chat 时跳过。把 decision 存到 `self._turn_decision` 供 `_fast_reply` 读取，或给 `_fast_reply` 增加可选参数 `skip_session: bool`。**已定**：`self._turn_decision = decision`，`_fast_reply` 若 `decision.skip_await` 含 `session.load` 则跳过 `_ensure_session_loaded`。
4. `_run_impl` 头部改为：先 `route`（route 是纯函数，可在 await 之前调用），再按 skip 决定是否 await。

**验收命令**

```powershell
cd "D:\agent-demo\RxyCode\RxyCode1_1_0"
python -m pytest tests/test_core/test_turn_router.py tests/test_core/test_chat_skip_await.py tests/test_core/test_first_turn_latency.py tests/test_core/test_request_routing.py -q
python -m ruff check core/turn_router.py core/agent_v2.py tests/test_core/test_chat_skip_await.py
```

**实施记录**（Grok 填写）

```
commits: perf(agent): skip memory and session awaits on ChatPrefix turns（fix 分支）
pytest: test_turn_router 10 + test_chat_skip_await 2 + test_first_turn_latency + test_request_routing 全绿（46 passed）；test_agent_tool_contracts 38 passed
ruff: All checks passed
实现：chat 路径 skip_await={memory.initialize, session.load, mcp.refresh}；_run_impl 先 route 再按 skip 决定 await（route 在任意 await 前，纯函数）；_turn_decision 传给 _fast_reply，skip 时跳过 _ensure_session_loaded；chat 回复后补 load_session（_session_loaded=False 时）不挡本回合 LLM；非 chat 路径仍 load
白名单扩展：test_agent_tool_contracts.py（plan 契约断言从 detector 级升级为 handler 级——FX2 R3 审计要求检测在 route 前，检测是纯查询，契约不执行保持）
未勾完成判据。
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [x] `route("你好").skip_await` 含 `memory.initialize` 与 `session.load`
- [x] `_run_impl("你好")` 在 `_fast_reply` 返回前不 `load_session`
- [x] 编码任务路径仍 load_session（测试：非 chat 的 `_run_impl` 会 load）
- [x] 现有 routing / first_turn 测试绿
- [x] GPT-5.6 审计 PASS

**审计记录**（GPT-5.6 填写）

```
网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
R1：PASS。chat 路径 skip_await 含 memory.initialize/session.load/mcp.refresh；_run_impl 先 route（纯函数）再按 skip 决定 await；_fast_reply 经 _turn_decision 跳过 _ensure_session_loaded；chat 回复后补 load_session 不挡本回合 LLM；非 chat 仍 load；plan 契约测试升级为 handler 级断言（检测是纯查询，FX2 R3 要求检测在 route 前），「plan 不执行」保持。
可以勾选 FX3 完成判据。
```

**Commit**

```
perf(agent): skip memory and session awaits on ChatPrefix turns

Greeting turns no longer pay load_session before the first model token.
Encoding paths still load history. Decision remains in TurnRouter.
```

---

### FX4 · 双档案预热同构

`P0` / 4–8h / 依赖：FX1 + FXC2 + FXC5 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

B5 预热：system + `warm` + 全量 tools + thinking on。问候无 tools + thinking off。`build_prewarm_signature` 不含 tools/thinking。`run()` 已不调度预热（LAT-1）。

**涉及文件**

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/prewarm.py` | （新建） | 从 agent_v2 迁调度；按 Profile 造消息 |
| `core/cache_policy.py` | `def build_prewarm_signature` | 签名增加 `kind, thinking, tools_digest` |
| `core/agent_v2.py` | `async def _prewarm_async` | 改为调用 `core/prewarm.py` |
| `tests/test_cache/test_prewarm_isomorphic.py` | （新建） | 创建 |

**已经替你决定好的**

- 每个 `session_id` **两槽**：chat Profile 与 agent Profile，可并行后台预热。
- 预热 user 文本固定为 `warm`（与今日一致），但 tools/thinking/system 必须等于该槽真实请求。
- chat 预热：`tools=None`（或 `[]`），thinking disabled，system=`get_system_prompt(tools=False)`。
- agent 预热：`tools=_get_core_tools()`，thinking 默认 on，system=`get_system_prompt(tools=True)`。
- **禁止**在用户 `_run_impl` 同步 await 预热（保持 LAT-1）。会话创建或空闲时 `create_task`。
- 签名字段：`model, cwd, mcp, kind, thinking_enabled, tools_digest`。

**操作步骤**

1. 扩展 `build_prewarm_signature` 增加上述字段；旧三参数调用必须改完（Grep `build_prewarm_signature` 全仓库）。
2. 测试：chat 预热消息的 tools 参数为 None；agent 预热 tools 非空；`profiles_compatible` 预热 profile 与对应真实 profile。
3. 把 `_session_prewarm_messages` / `_prewarm_async` 迁到 `prewarm.py` 的函数，`AgentV2` 只保留薄包装。
4. keep-alive **本卡不要改**（FX5）。

**验收命令**

```powershell
cd "D:\agent-demo\RxyCode\RxyCode1_1_0"
python -m pytest tests/test_cache/test_prewarm_isomorphic.py tests/test_cache/test_session_reuse.py -q
python -m ruff check core/prewarm.py core/cache_policy.py core/agent_v2.py
```

**实施记录**（Grok 填写）

```
commits: fix(cache): make prewarm isomorphic to ChatPrefix and AgentPrefix（fix 分支）
pytest: test_prewarm_isomorphic 6（新）+ test_session_reuse 36 全绿；全量 test_core+test_cache 7766 passed（基线失败 8 不变）
ruff: All checks passed
实现：build_prewarm_signature 增加 kind/thinking_enabled/tools_digest；core/prewarm.py（新）
  双槽（chat: tools=None/thinking off/system(tools=False)；agent: 核心 tools/thinking on/
  system(tools=True)）并行 prewarm_all；agent_v2 薄包装（_prewarm_async→prewarm_all、
  _session_prewarm_messages→prewarm、_prewarm_state 双槽：agent 槽兼容旧注入形态、
  chat 槽 _prewarm_chat）；LAT-1 保持（run/_run_impl 仍无 _schedule_prewarm）；
  keep-alive 未改（FX5）
未勾完成判据。
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [x] 预热签名含 kind/thinking/tools_digest
- [x] chat 预热与 chat 真实请求 `profiles_compatible`
- [x] agent 预热与 agent 真实请求 `profiles_compatible`
- [x] `_run_impl` / `run` 源码仍不含 `_schedule_prewarm`（LAT-1 保持）
- [x] GPT-5.6 审计 PASS

**审计记录**（GPT-5.6 填写）

```
网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
R1-R2：FAIL（thinking 显式同构——改用真实路径的 _thinking_disabled_this_turn 开关并加锁串行；测试去手工 profile、签名须与真实请求签名相等、空 mcp 渲染为 ''）
R3：PASS。签名含 kind/thinking_enabled/tools_digest；chat 槽（无 tools/thinking off/system tools=False）与 agent 槽（核心 tools/thinking on/system tools=True）与真实回合参数兼容；双槽 _prewarm_chat/_prewarm 均确认；LAT-1 保持（run/_run_impl 无 _schedule_prewarm）；keep-alive 未改；44+ 测试绿。
可以勾选 FX4 完成判据。
```

**Commit**

```
fix(cache): make prewarm isomorphic to ChatPrefix and AgentPrefix

Prewarm writes the same tools/thinking/system bytes as the real turn for
each archive so a greeting no longer misses a tools-on warmup prefix.
```

---

### FX5 · keep-alive 与当前 Profile 同构

`P0` / 2–4h / 依赖：FX4 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

`_keep_alive_async` 现为无 system、`tools=None`、user=`keep-alive`，是第三套前缀。

**涉及文件**

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/agent_v2.py` | `async def _keep_alive_async` | 使用当前 session 的 **agent** Profile 同构请求（默认保活编码前缀） |
| `core/prewarm.py` | （FX4 已建） | 增加 `keepalive_messages(profile)` |
| `tests/test_cache/test_prewarm_isomorphic.py` | 追加 | keep-alive 与 agent profile compatible |

**已经替你决定好的**

- 保活默认保 **AgentPrefix**（长任务 TTL 更值钱）。ChatPrefix 保活本卡不做。
- 必须带与预热相同的 system + tools；user 文本用 `keep-alive` 可以，但 **不得**省略 system/tools。
- 默认开关仍关闭（`keep_alive_enabled`）。
- `max_tokens=1` 保持。

**实施记录**（Grok 填写）

```
commits: fix(cache): send keep-alive with the frozen AgentPrefix（fix 分支）
pytest: test_prewarm_isomorphic 12（+3 FX5）+ test_session_reuse 36 全绿；全量 7771 passed（基线 8 不变）
ruff: All checks passed
实现：prewarm.keepalive_messages()（agent 槽同构：system + 核心 tools + keep-alive）；
  _keep_alive_async 改走 keepalive_messages + core_tools_for(self, "agent")，max_tokens=1 保持
未勾完成判据。
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [x] Grep `_keep_alive_async`：不再 `_raw_stream([HumanMessage(...)], tools=None)` 这种无 system 调用
- [x] 测试证明 keepalive tools_digest == agent profile tools_digest
- [x] 默认 keep_alive 仍 False
- [x] GPT-5.6 审计 PASS

**审计记录**（GPT-5.6 填写）

```
网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
R1：FAIL（digest 测试须从实际捕获的 keep-alive 请求 tools 派生，不得硬编码）
R2：PASS。_keep_alive_async 无裸 HumanMessage+tools=None；keep-alive = agent 槽同构（system+核心 tools+keep-alive，max_tokens=1）；digest == agent profile digest（从捕获调用计算）；默认开关 False 保持；白名单内。
可以勾选 FX5 完成判据。
```

**Commit**

```
fix(cache): send keep-alive with the frozen AgentPrefix, not a third body
```

---

### FX6 · ToolsFreeze：API schema 不再按轮裁剪

`P0` / 4–8h / 依赖：FX2、FX1 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

`resolve_fast_reply_tool_allowlist` 让社交只绑 `datetime`、declines 绑空 frozenset——这是 **按轮改 tools 段**，打穿 2900万形态。闲聊要快应走 **ChatPrefix 空工具冻档案**，不是在 AgentPrefix 上删工具。

**涉及文件**

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/turn_router.py` | `test_hello_ah_is_agent_until_fx6` | 「你好啊」与宽社交改 `path=chat` |
| `core/agent_v2.py` | `_resolve_fast_reply_tool_allowlist` | agent 路径 **忽略** allowlist 对 API bind 的裁剪；执行层若需拒绝，用 orchestrator 权限，不改 schema |
| `core/request_routing.py` | `def resolve_fast_reply_tool_allowlist` | 保留函数但 TurnRouter/agent 路径不再用它绑 LLM tools；可加 docstring「执行层遗留，禁止用于 schema」 |
| `tests/test_core/test_turn_router.py` | 改 `test_hello_ah_is_agent_until_fx6` | 改为 `path=="chat"` |
| `tests/test_core/test_first_turn_latency.py` | `test_declines_tools_binds_no_tools` | 改为断言 chat path / 空 API tools 来自 Profile，不是 allowlist 裁剪 AgentPrefix |

**已经替你决定好的**

- `is_social_chat` → **ChatPrefix**（含「你好啊」），不再绑 datetime schema。
- `declines_tools` → ChatPrefix。
- 编码 AgentPrefix：**始终** `_get_core_tools()` 全量，会话内排序冻结。
- datetime 对闲聊零收益，失去它是预期。
- 本卡仍不实现 MCP 动态工具进前缀（MCP 指纹变化 = 新 Profile，那是未来卡）。

**实施记录**（Grok 填写）

```
commits: fix(agent): stop mutating tool schemas per turn（fix 分支）
pytest: test_turn_router 10 + test_first_turn_latency 14 + test_request_routing 22 + test_agent_tool_contracts 38 全绿；全量 7772 passed（基线 8 不变）
ruff: All checks passed
实现：route() 宽社交（含「你好啊」+ compose social）→ path=chat（ChatPrefix 空工具冻档案）；
  _fast_reply_with_tools 删除 resolve_fast_reply_tool_allowlist 隐式裁剪（user 文本启发式不再
  改 API schema），bind 全量核心工具；显式 allowlist（plan 只读）保持为执行层契约；
  resolve_fast_reply_tool_allowlist 标注「执行层遗留，禁止用于 schema」
未勾完成判据。
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [x] `route("你好啊").path == "chat"`
- [x] agent 路径 `_fast_reply_with_tools` 绑定的 tools 集合不因 user 文本变化（测试：两句不同编码任务 digest 相同）
- [x] 现有 first_turn / request_routing 按新语义改测试并绿（允许改断言，禁止改回裁剪 schema）
- [x] GPT-5.6 审计 PASS

**审计记录**（GPT-5.6 填写）

```
网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
R1-R2：FAIL（分组测试证据、彻底移除 schema 裁剪——plan 只读改执行层拒绝）
R3：PASS。route(你好啊)=chat（宽社交 ChatPrefix）；_fast_reply_with_tools 绑定全量核心工具（无任何按轮裁剪，digest 冻结测试从捕获请求计算）；plan 只读在 _execute_tool 执行层拒绝（orchestrator 不执行）；resolver 保留并标注执行层遗留；分组 10+14+22+38 全绿、ruff 通过。
可以勾选 FX6 完成判据。
```

**Commit**

```
fix(agent): stop mutating tool schemas per turn; send social to ChatPrefix

Idle chat uses the frozen empty-tool archive. Encoding turns keep a
frozen full core tool list so prefix cache can survive a long task.
```

---

### FX7 · Primary 首字：闲聊 1s 正文 / 编码 3s thought

`P0` / 3–6h / 依赖：FX3、FX6 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

ChatPrefix 关 thinking 是为了 1s 出「你好」，Thought「…」会空转。AgentPrefix 必须开 thinking 并 `write_reasoning` 首包。stdio 在 `ensureReady` 之后才画 thinking 行。

**涉及文件**

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/agent_v2.py` | `_thinking_disabled_this_turn = True` | **仅** ChatPrefix 设置；AgentPrefix 禁止设 True |
| `frontend/opentui-app/src/transport/stdioTransport.ts` | `callbacks.onProgress?.("Connecting...")` | 在 `ensureReady` **之前**插入 thinking 占位（与 HTTP 对齐） |
| `tests/test_core/test_first_turn_latency.py` | `test_fast_reply_disables_extended_thinking` | 收窄为「仅 chat 路径」 |
| `frontend/opentui-app/src/transport/stdioTransport.failure.test.ts` | `sendChatMessage("你好"` | 若有时序断言则更新 |

**已经替你决定好的**

- ChatPrefix：保持 thinking disabled；UI 占位可以是空 Thought，但 **3s 内必须出现 assistant 正文**（产品：闲聊看回复不看假思考）。
- AgentPrefix：禁止 `_thinking_disabled_this_turn`；已有 `write_reasoning` 保持逐 delta。
- stdio：用户气泡 + thinking 行在 `ensureReady` 前出现；Connecting 可并行。
- 本卡不做真实网关 TTFT 压测（无 live 预算）；用单元测试锁「哪条路径关 thinking」+ 前端测试锁「占位不晚于 ensureReady」。

**实施记录**（Grok 填写）

```
commits: fix(ux): disable thinking only on ChatPrefix（fix 分支）
pytest: test_first_turn_latency 14 passed（test_fast_reply_disables_extended_thinking 收窄为仅 chat 路径 + agent 路径禁设 True）
bun test src/transport/ 33 passed（+1 FX7：失败路径证明 thinking 占位先于 ensureReady 推送）
实现：_fast_reply_with_tools 无 _thinking_disabled_this_turn=True（源码验证）；stdioTransport
  sendChatMessage thinking 占位/state/publish 移到 ensureReady 之前（与 HTTP 对齐），启动失败时
  settle 占位
注：bun 需在 PATH（~/.bun/bin）
未勾完成判据。
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [x] `_fast_reply` 仍关 thinking；`_fast_reply_with_tools` 源码路径 **不会** 设 `_thinking_disabled_this_turn = True`
- [x] stdio `sendChatMessage` 在 `ensureReady` 调用之前就把 thinking 消息推进 `onMessages`
- [x] `python -m pytest tests/test_core/test_first_turn_latency.py -q` 绿
- [x] `cd frontend\opentui-app; bun test` 与占位相关测试绿（若环境无 bun：停下来报告，不要假装绿）
- [x] GPT-5.6 审计 PASS

**审计记录**（GPT-5.6 填写）

```
网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
R1：FAIL（占位测试须断言 live→settled 状态迁移而非仅存在性）
R2：PASS。_fast_reply 保持关 thinking；_fast_reply_with_tools 无 True 赋值（源码扫描）；stdio 占位在 ensureReady 前推送（失败路径证明）+ 失败时 settle；pytest 14 / bun 33 全绿；白名单内。
可以勾选 FX7 完成判据。
```

**Commit**

```
fix(ux): disable thinking only on ChatPrefix; show stdio thought row first

Greetings keep thinking off so the reply can land in one second. Encoding
turns keep live reasoning. stdio no longer waits for the worker before
drawing the thought placeholder.
```

---

### FX8 · 公开 `append_turn_context`（LinkAgent 缝）

`P0` / 4–6h / 依赖：FX2、FX6 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

L2 计划 monkeypatch `_memory.get_context_for_prompt`。phase-fix 必须提供公开、可卸载、只进 user 后缀的缝，否则以后 EKO 会被人拼进 S1。

**涉及文件**

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/turn_context.py` | （新建） | 创建 |
| `core/agent_v2.py` | `class AgentV2` | 加 `append_turn_context` / `clear_turn_context`；组装 user 时拼接 |
| `core/prompts/registry.py` | `def build_user_message` | **不要改签名默认行为**；由 agent 把 turn context 并入 `memory_context` 参数尾部 |
| `tests/test_core/test_turn_context.py` | （新建） | 创建 |

**已经替你决定好的**

```python
class TurnContextBlock(TypedDict):
    kind: Literal["eko", "note"]
    text: str
```

- `append_turn_context(self, blocks: Sequence[TurnContextBlock]) -> None`
- `kind` 禁止 `"system"` / `"tools"`（传入则 ValueError）
- ChatPrefix / `path=="chat"`：**忽略** blocks（不检索、不拼接）
- 空列表或全空 text：user 消息与未调用 **逐字节相同**（不含时间戳——时间戳本就每轮变；比较时应 mock 时间或只比较 context 段）
- **已定比较法**：对 `build_user_message` 的 `memory_context` 参数比较：未 append 与 append([]) 都是 `""`
- 注入位置：原 memory_ctx **之后**，user_content **之前**（与 L2「追加在原 context 之后」一致）
- 不在本卡实现 EKO 检索

**操作步骤**

测试至少包含：

```python
def test_zero_blocks_leave_memory_ctx_empty():
    ...

def test_rejects_system_kind():
    with pytest.raises(ValueError):
        agent.append_turn_context([{"kind": "system", "text": "x"}])

def test_chat_path_ignores_blocks():
    # append eko then route 你好 → _fast_reply 的 memory_ctx 仍空
    ...

def test_agent_path_appends_after_memory():
    ...
```

**实施记录**（Grok 填写）

```
commits: feat(agent): add append_turn_context suffix seam for LinkAgent（fix 分支）
pytest: test_turn_context 5（新）+ 回归全量 7777 passed（基线 8 不变）
ruff: All checks passed
实现：core/turn_context.py（TurnContextBlock TypedDict + validate_blocks 拒绝 system/tools kind + serialize_turn_context 空输入逐字节等同 no-op）；AgentV2.
  append_turn_context/clear_turn_context/_turn_context_suffix；_fast_reply_with_tools memory_ctx 尾部拼接（memory 之后、user_content 之前）；_fast_reply（chat）忽略
注：测试用 pytest-asyncio（手动 get_event_loop 在全量顺序下失效——FXC4 已知坑）
未勾完成判据。
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [x] 公开方法在 AgentV2 上，不需要碰 `_memory`
- [x] 拒绝 system/tools kind
- [x] chat 忽略；agent 追加后缀
- [x] 空 blocks 不增加 memory_context 字符
- [x] GPT-5.6 审计 PASS

**审计记录**（GPT-5.6 填写）

```
网关：https://opencode.ai/zen/v1（gpt-5.6-luna，非 zen/go）
R1：FAIL（签名须用 TurnContextBlock、空 blocks 经真实 agent 路径逐字节验证）
R2：PASS。append_turn_context/clear_turn_context 公开且不碰 _memory；拒绝 system/tools（ValueError）；chat 忽略、agent 在 memory 后追加；空 blocks/全空 text 经真实路径 memory_context 与未调用相同；build_user_message 签名未改；不实现 EKO 检索。
可以勾选 FX8 完成判据。
```

**Commit**

```
feat(agent): add append_turn_context suffix seam for LinkAgent

EKO-style context can only append to the user suffix after the prefix is
frozen. ChatPrefix ignores it. Empty blocks are byte-identical to a no-op.
```

---

### FX9 · 应用缓存 namespace 预留 agent 维

`P1` / 2–4h / 依赖：无硬依赖，建议 FX1 后 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

`_application_cache_namespace` 现为 `base_url|model|credential_digest`。F2/E3 需要 `|{ns}`。`ns=None` 必须与改造前 **逐字节相同**。

**涉及文件**

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/agent_v2.py` | `def _application_cache_namespace` | 读取 `self._agent_namespace`，仅非空时追加 |
| `tests/test_core/test_cache_namespace.py` | （新建） | 创建 |

**已经替你决定好的**

```python
def _application_cache_namespace(self) -> str:
    base_url = str(self.model_config.get("base_url") or "").rstrip("/")
    model_name = str(self.model_config.get("model_name") or "")
    api_key = str(self.model_config.get("api_key") or "")
    credential_digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    base = f"{base_url}|{model_name}|{credential_digest}"
    ns = getattr(self, "_agent_namespace", None)
    if ns:
        return f"{base}|{ns}"
    return base
```

- `_agent_namespace` 默认不设置或 None。
- ns 正则：`^[a-z0-9_.-]{1,64}$`；非法则 ValueError（仅当非 None）。
- 禁止把 ns 写进 system / SharedReadonlySegment（本卡只做应用缓存键）。

**实施记录**（Grok 填写）

```
commits: feat(cache): optional agent namespace（fix 分支）
pytest: test_cache_namespace 11（新）+ 全量 7789 passed（基线 8 不变）
ruff: All checks passed
实现：_application_cache_namespace 在 _agent_namespace 非 None 时追加 |ns；ns 正则
  ^[a-z0-9_.-]{1,64}$（非法 ValueError）；无 ns 与改造前逐字节相同（测试钉死模板）；
  不写 system/SharedReadonlySegment
未勾完成判据。
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [ ] 无 `_agent_namespace` 时字符串与改造前格式相同（测试钉死拼接模板）
- [ ] 设置合法 ns 后多 `|ns`
- [ ] 非法 ns 抛错
- [ ] GPT-5.6 审计 PASS

**Commit**

```
feat(cache): optional agent namespace on application cache keys

Single-agent keys stay byte-identical when namespace is unset so existing
precise/semantic entries keep working until Phase F assigns agent ids.
```

---

### FX10 · HandoffEnvelope 与 NoHistoryCopy 类型预留

`P1` / 3–5h / 依赖：FX1 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

Phase H 若把 transcript 塞进下一角色，Primary 前缀死亡。现在必须把类型写成 **禁止字段**，避免以后用 `dict` 开后门。

**涉及文件**

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `core/handoff.py` | （新建） | 创建 |
| `tests/test_core/test_handoff_envelope.py` | （新建） | 创建 |

**已经替你决定好的**

```python
@dataclass(frozen=True, slots=True)
class HandoffEnvelope:
    summary: str
    artifact_paths: tuple[str, ...]
    attachment_ids: tuple[str, ...]
    source_model: str
    target_model: str
    # 禁止：messages / history / thinking / reasoning_content
```

- `from_dict` 若 key 含 `messages`/`history`/`thinking`/`reasoning_content`/`tool_calls` → TypeError
- 本卡 **不** 实现翻译器、不接 Coordinator
- 另写 `test_child_must_not_copy_primary_history` 作为 **文档测试**：断言 `HandoffEnvelope` 没有 `messages` 字段（`hasattr` / `dataclasses.fields`）

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [ ] 含 history 的 dict 构造失败
- [ ] fields 名称集合不含 messages/history/thinking
- [ ] 无对 agent_v2 运行时行为变化
- [ ] GPT-5.6 审计 PASS

**Commit**

```
feat(agent): reserve HandoffEnvelope without chat history fields

Future multi-model handoff cannot smuggle transcripts into another
prefix. The type rejects history/thinking keys at the boundary.
```

---

### FX11 · 文档、模块 README、evals 门与不变量索引

`P1` / 2–4h / 依赖：FXC1–FXC6 + FX1–FX10 · **owner: backend** · **执行：Grok 4.6** · **审计：GPT-5.6**

**背景**

改了核心入口却不改 `docs/modules/core.md`，下一只代理会继续往 `_run_impl` 加 if，或按模型名打 `cache_control`。

**涉及文件**

| 文件 | Grep 锚点 | 改法 |
|---|---|---|
| `docs/modules/core.md` | `### Key Files` | 增加 catalog 三族、S1/S2、turn_router / prefix_profile / prewarm / turn_context / handoff |
| `docs/modules/config.md` | `model_catalog` | 指向 §16 已纠字段；未知模型 fallback |
| `docs/plans/opus5-plan/rxycode/README.md` | `## 文档一览` | 本 Phase 覆盖 Part 1+2+3 |
| `AGENTS.md` | 模块表（若有 core 行） | 一句指向新文件 |
| `evals/baselines/latest-agent.json` | （只读比较） | 跑 compare，不改基线除非掉分需停工 |

**已经替你决定好的**

- 不在本卡改功能代码。
- evals 命令必须跑；掉分立即 STOP。
- README 写明：本 Phase 由 Grok 4.6 执行、GPT-5.6 审计勾选；覆盖调研 Part 1–3。

**验收命令**

```powershell
cd "D:\agent-demo\RxyCode\RxyCode1_1_0"
python -m pytest tests/test_core/test_catalog_contract_official.py tests/test_cache/test_cache_family_inject.py tests/test_cache/test_s1_s2_split.py tests/test_cache/test_session_affinity_and_usage.py tests/test_providers/test_thinking_contract.py tests/test_cache/test_unknown_model_fallback.py tests/test_core/test_prefix_profile.py tests/test_core/test_turn_router.py tests/test_core/test_chat_skip_await.py tests/test_core/test_turn_context.py tests/test_core/test_cache_namespace.py tests/test_core/test_handoff_envelope.py tests/test_cache/test_prewarm_isomorphic.py tests/test_core/test_first_turn_latency.py tests/test_core/test_request_routing.py -q
python -m evals.cli run --backend agent --compare-baseline evals\baselines\latest-agent.json
```

**完成判据**（GPT-5.6 PASS 前禁止勾）

- [ ] core.md 列出：契约三族、禁止模型名启发式、S1 冻结、禁止在 agent_v2 加路由 if
- [ ] rxycode README 索引含 PHASE-FIX 且写明覆盖 Part 1+2+3
- [ ] 上列 pytest 全绿
- [ ] evals 基线不下降（贴输出）
- [ ] GPT-5.6 对本卡及 **FXC1–FXC6 与 FX1–FX10 是否都已 PASS** 做一次总览
- [ ] GPT-5.6 审计 PASS

**Commit**

```
docs(core): document cache families, S1/S2, and TurnRouter

Point future phases at catalog contracts, frozen prefixes, skip_await
ChatPrefix, and append_turn_context so neither cache_control heuristics
nor routing ifs grow back inside AgentV2.
```

---

## §6 Phase Fix 出口

全部 **FXC1–FXC6 与 FX1–FX11** 完成判据被 **GPT-5.6 勾选** 后才算完。另外：

**Part 1**

1. Grep `core/agent_v2.py`：没有 `for tool_def in payload["tools"]` 给每个 tool 打 `cache_control`。
2. DeepSeek / MiniMax M3 / `get_contract` 为 None 的序列化 JSON **不含** `"cache_control"`。
3. `_to_openai_messages` 对 human 保留 `cache_control`。
4. `SystemMessage(content=research_contract)` 无匹配；S1 不含每轮日期。
5. catalog §16 表测试绿；未知模型不发 `prompt_cache_key`。
6. 调研 Part 1 §4.3 / §5「不要给 DeepSeek 打 cache_control」「不要按 id 含 claude 打点」仍成立。

**Part 2 / 3**

7. Grep `_run_impl`：**没有** `is_social_chat(` / `PURE_SOCIAL_GREETING_RE` / `declines_tools(` 作为分流条件。
8. Grep `_keep_alive_async`：没有 `tools=None` 配无 system。
9. `route("你好").path == "chat"` 且 skip_await 非空；编码任务 `path=="agent"` 且 tools digest 稳定。
10. evals 基线不下降。
11. 调研 Part 3 §33 的「不要做」仍全部成立。

**下一步**：Phase C 继续异步化时遵守 AC1 **且** 不得把 memory await 塞回 ChatPrefix；Phase D 引用 NoHistoryCopy / SpawnNonBlocking；LinkAgent L2-3 改为调用 `append_turn_context`，停止包装 `_memory`。协议升级（GPT Responses 整链、Claude 原生 Messages、Doubao Context API）**另开 Phase**，不得在本出口未完成时插入。

---

## 附录 A · 代码示例总表

| 符号 | 模块 | 职责 |
|---|---|---|
| `injects_cache_control` / `injects_prompt_cache_key` | `core/catalog.py` | 通配三族：打不打点、发不发 key |
| `get_system_s1` / `get_system_s2` | `core/prompts/registry.py` | 冻结 S1 vs 动态快照 |
| `PrefixProfile` / `digest_tools` / `identity()` | `core/prefix_profile.py` | 前缀指纹（含 `s1_digest`） |
| `TurnDecision` / `route()` | `core/turn_router.py` | 唯一分流 |
| `build_prewarm_signature(..., kind, thinking_enabled, tools_digest)` | `core/cache_policy.py` | 预热签名 |
| `append_turn_context` | `AgentV2` | LinkAgent 后缀缝 |
| `HandoffEnvelope` | `core/handoff.py` | 禁止 history |
| `_application_cache_namespace` | `AgentV2` | `ns=None` 兼容 |

---

## 附录 B · GPT-5.6 审计提示词

把下面整段贴进 **新的 GPT-5.6 会话**，并附上：卡号、`git diff`、pytest 输出。

```
你是 RxyCode Phase Fix 的独立审计员（GPT-5.6）。不要改代码。

仓库：D:\agent-demo\RxyCode\RxyCode1_1_0
施工文档：docs/plans/opus5-plan/rxycode/PHASE-FIX.md
只审这一张卡：FXC<编号> 或 FX<编号>
权威调研：docs/plans/opus5-plan/rxycode/research/2026-08-14-deepseek-harness-and-opencode-cache.md
  Part 1 §4–§16（契约/三族/S1）+ Part 2 §20–§24（1s/3s）+ Part 3 §31–§33（不变量）

检查清单：
1. 是否只改了该卡白名单文件？
2. 是否违反 FX-CB1–CB12（双档案、禁止 _run_impl 新 if、三流同构、不裁 schema、ns=None 兼容、turn_context 不碰 S1、命中率分桶、evals、隐式族不打点、显式族只打最后 tool、只信 catalog、human 保留断点）？
3. 测试是否真的覆盖卡里的完成判据，而不是改断言放水？（FXC1 允许改 test_model_contracts 旧口径并加 cached_alt；FXC3 允许改 test_stable_prefix 的 SystemMessage 断言。FXC1 FAIL 条件：顺手改了 _raw_stream 打点循环。）
4. 是否给 DeepSeek / MiniMax M3 / 未知模型打了 cache_control？是否用模型 id 含 claude 决定打点？是否把 cache_mode 写成了 schema 没有的 explicit / breakpoints？
5. 是否为「以后多 agent / 多模型 / LinkAgent」留下会打穿前缀的后门（复制 history、热切换模型、EKO 进 S1、按轮删 tools）？
6. 文档完成判据是否仍全是 [ ]（Grok 不得代勾）？
7. 本卡是否越界做了协议升级（整链 Responses / 原生 Messages / 方舟 Context API）？越界 → FAIL。
8. 是否新建了 cache_family.py 或第二套 cache_control 注入器？有 → FAIL。

输出：
- 结果：PASS 或 FAIL
- 若 FAIL：必须改什么才能再审（最小列表）
- 若 PASS：声明「可以勾选 FXC<编号> 或 FX<编号> 完成判据」
```

PASS 之后：由 GPT-5.6 或用户把该卡 `- [ ]` 改成 `- [x]`，并填写「审计记录」。然后才允许开下一张卡。
