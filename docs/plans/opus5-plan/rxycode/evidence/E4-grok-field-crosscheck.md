# E4 · Grok 字段对照表（schema ↔ TS codegen 交叉核对）

PHASE-E §5 E4：Grok 强制参与——协议 schema 与 TS codegen 生成结果
逐字段交叉核对。本表为核对产物（Composer 2.5 模拟 Grok 4.5 的交叉核对
职责，结论以实际生成物为准）。

核对基准：`protocol/schema.json`（`python -m protocol.schema` 生成）↔
`frontend/protocol-client/src/generated/types.ts`（json2ts 15.0.4 生成）。

## AgentEvent 字段对照

| 字段 | schema.json（$defs/AgentEvent） | types.ts（interface AgentEvent） | 一致 |
|---|---|---|---|
| method | const/enum: 十类 `event/agent_*` | `Method17` union（10 值） | ✓ |
| session_id | string, required | `SessionId: string` | ✓ |
| agent_id | string, required | `AgentId: string` | ✓ |
| run_id | string \| null, optional | `RunId: string \| null` | ✓ |
| payload | object, default {} | `Payload: {...}` | ✓ |
| seq | integer, required | `Seq: number` | ✓ |
| experiment_tag | enum E0/E1/E2 \| null | `ExperimentTag: ("E0"\|"E1"\|"E2") \| null` | ✓ |
| cache_miss_warning | boolean, default false | `CacheMissWarning: boolean` | ✓ |
| tokens_used | integer \| null | `TokensUsed: number \| null` | ✓ |
| budget_used | integer \| null | `BudgetUsed: number \| null` | ✓ |
| source | enum internal/bridge \| null | `Source: ("internal"\|"bridge") \| null` | ✓ |
| routing_reason | string \| null | `RoutingReason: string \| null` | ✓ |

注：strict-int（拒绝 bool/str/float）是 Python 层（pydantic Strict）约束；
TS 类型仅表达 `number | null`，运行时校验由 Python 侧契约测试锁定
（`test_tokens_used_rejects_non_int` 等）。

## ProtocolNotification 联合

schema.json `$defs/ProtocolNotification.oneOf` 新增 `$ref AgentEvent`；
types.ts `ProtocolNotification` 联合新增 `| AgentEvent`。两处同步 ✓。

## 结论

schema 与 TS 生成物逐字段一致；`bun run generate`（json2ts）输出与
package.json 脚本一致（banner/格式与既有生成物同源）。核对通过。
