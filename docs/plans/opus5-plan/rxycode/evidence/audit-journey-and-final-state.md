# Phase E · 审计修订历程与最终状态（luna 6 轮）

## 审计历程

| 轮次 | 结论 | 主要修订 |
|---|---|---|
| 1 | 需修订（~20 项） | bench smoke 全实测；RB2/RB4 契约证据注入；routing_reason 约束；会话级 cache counter；E3 运行时集成（context/mechanical/cache_key） |
| 2 | 需修订（~12 项） | 运行时 token 快照+去重；共享预算池；AgentContext 写保护；死信目标语义；interrupt checkpoint；熔断统一 stop()；codegen cwd |
| 3 | 需修订（~9 项） | 生命周期事件快照；深度只读上下文；日志不可变；构造期 ns 校验；真实 stdio codec 测试；基线失败登记 |
| 4 | 需修订（~8 项） | interrupt checkpoint FAILED 语义；source 默认 internal；跨 agent 总线证据；执行过程记录 |
| 5 | 需修订（~6 项） | replay 深拷贝隔离；EB8 序列化字节预算；source 对象层三态；golden 字节级测试 |
| 6 | **功能全达标，剩 6 项结构性约束** | 见下 |

## 第六轮审计最终判定（功能面）

- **E1/E2/E5/E6 功能通过**；E3/E4/E7 功能实现与契约测试全部通过
- **RB1-RB5 全部通过**（吞吐 1.98-2.00×、interrupt 0.09-0.11ms、
  熔断 0.35-0.45ms、30min stress 无挂起、跨 agent 总线链路）
- **EB1/EB2/EB3/EB4/EB5/EB6/EB8 满足**；C1/C4 硬前置满足
- 契约测试 165 passed（6 文件），ruff 全过
- 全量回归：6 项主工作区同款基线失败已正式登记
  （evidence/acceptance-baseline-failures.md，逐一复现）

## 剩余结构性约束（环境/范围，非 E 层缺陷）

| # | 项 | 性质 | 处置 |
|---|---|---|---|
| 1 | 真实 SSE agent 事件接线 | `api_server.py` StreamTUI 无 agent_* 输出类型且不在 E4 白名单；接线属 F13 消费方 | stdio 真实 codec 往返 + SSE 线格式往返已测；完整接线待 F 层 |
| 2 | Grok 4.5 强制参与 | 执行环境无 Grok 实例 | 以 E4-grok-field-crosscheck.md 逐字段对照生成物替代 |
| 3 | E3/E4/E6 白名单越界 | 依赖驱动（E3 需 _last_error、E4 判据强制 BusEvent 收口、E6 需 E3 测试适配） | 范围与锁定测试记录于 execution-process-and-boundaries.md |
| 4 | 修订 commit 无卡号 | 多轮审计迭代修订（初始交付满足一卡一 commit） | 初始 E1-E7 主 commit 含卡号；修订 commit 以 round 标注 |
| 5 | 全量回归 6 失败 | 主工作区同款基线遗留（B/P7/C8/master 责任） | 正式登记为验收基线（acceptance-baseline-failures.md） |
| 6 | 契约测试先行证据 | 测试与实现同 commit（执行过程为测试先行） | 过程记录于 execution-process-and-boundaries.md |

## 终态

Phase E 功能实现、契约测试、验收基准、RB1-RB5 演示全部达标；
luna 审计 6 轮后功能面无剩余修订项，仅剩 6 项结构性约束
（需用户/流程裁决：基线登记、Grok 实例、SSE 接线归属、白名单
依赖、修订 commit 形式、测试先行证据形式）。
