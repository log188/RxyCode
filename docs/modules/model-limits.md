# model-limits — 模型输出上限解析（Phase 3）

RxyCode 的模型输出上限（`max_tokens`）不再由新增模型时统一写入的数字决定，
而是通过**可解释的来源链**逐级解析，最终只允许 `OutputLimitResolution.resolved_max_tokens`
进入 SDK。

## 与 Phase A 的边界

| 层 | 回答的问题 | 载体 |
|----|-----------|------|
| Phase A 能力调研值 | 这个模型**能力上**能输出多少 | `ModelCapabilities.max_output_tokens`（`config/model_capabilities.py`） |
| Phase 3 请求决策 | 这次请求**实际**要多少 | `ModelCatalog` + `OutputLimitResolver`（`config/model_catalog.py`、`config/model_limits.py`） |

Phase A 的值是**能力值**（死数据，不被请求路径直接消费）；Phase 3 的解析器可以把它作为
`provider_default` 或目录记录的输入来源之一，但最终请求值只由
`OutputLimitResolution.resolved_max_tokens` 产出。

## 解析优先级（冻结）

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | `explicit_config` | 用户显式 `max_tokens: <正整数>` |
| 2 | `catalog_exact_provider` | `provider_id + model_id` 精确目录项 |
| 3 | `catalog_exact_model` | `model_id` 精确目录项（无 Provider 冲突时） |
| 4 | `catalog_family` | 已审计的 family pattern |
| 5 | `provider_default` | Provider 明确默认（可来自 Phase A 能力值） |
| 6 | `unknown_fallback` | 未知模型高位兜底（默认 `32768`，不再回退 `8192`） |

额外钳制来源：`context_cap`（context window 预算钳制）、`explicit_clamped`（显式值超硬上限被钳）。

## 配置

```yaml
model_limits:
  unknown_model_max_tokens: 32768      # 未知模型高位兜底
  context_safety_margin_tokens: 1024   # 上下文安全余量
```

模型级配置：
```yaml
models:
  deepseek/deepseek-v4-flash:
    max_tokens: auto       # 省略或 auto = 走目录解析
  custom/manual:
    max_tokens: 4096       # 正整数 = 用户显式覆盖
```

约束：`max_tokens` 只接受正整数、`auto` 或省略；`0`/负数/空串/浮点数都拒绝。

## 迁移与诊断

```powershell
# 只读报告每个模型的 max_tokens 来源（不写磁盘、不泄漏凭证）
python -m RxyCode config model-limits inspect

# 把单个模型迁移到 auto（先备份、显示变更、dry-run 不写盘）
python -m RxyCode config model-limits set-auto deepseek/deepseek-v4-flash --dry-run
python -m RxyCode config model-limits set-auto deepseek/deepseek-v4-flash
```

旧配置兼容策略（ML7）：
- 旧 `max_tokens = 正整数` → 保持为用户显式覆盖，不悄悄扩大费用
- 旧配置缺少 `max_tokens` → 进入 auto
- 新 `max_tokens: auto` → 走目录解析
- 新 `max_tokens: 正整数` → 显式覆盖

## 目录

`config/model_catalog.json` 是版本化目录。每条记录必须包含：

```json
{
  "provider_id": "deepseek",
  "model_id": "deepseek-v4-flash",
  "model_context_window": 1048576,
  "model_max_output_tokens": null,
  "source": "phase-a:deepseek",
  "source_url": "https://api-docs.deepseek.com/guides/thinking_mode",
  "as_of": "2026-08-02"
}
```

- 键允许同一 `model_id` 跨 Provider 共存（`deepseek:deepseek-v4-flash` 与
  `opencode-go:deepseek-v4-flash`）；
- 同 Provider 同 ID 重复项 fail closed（不按文件顺序覆盖）；
- 未验证的数字不能进入目录；查不到就保留 `null` 或走 `unknown_fallback`；
- family pattern 只能显式登记，禁止昵称或模糊包含匹配。

## API 摘要

`GET /models`、`POST /models/onboard` 响应新增可选字段：

```json
{
  "id": "deepseek/deepseek-v4-flash",
  "provider_model_id": "deepseek-v4-flash",
  "max_tokens_mode": "auto",
  "resolved_max_tokens": 65536,
  "limit_source": "catalog_exact_provider",
  "context_window": 131072,
  "warning": null
}
```

- UI/CLI 只显示摘要，不在客户端自行计算 `min()` 或重新加载目录；
- 能力未知时显示"未知模型兜底 32768"及来源，不显示"模型最大值 32768"；
- 旧客户端收到新字段时忽略未知可选字段；新客户端收到旧服务器时显示
  `source=legacy_server`。

## 回滚

1. 优先恢复配置备份（`set-auto` 会自动备份 `config.yaml.bak-<ts>`）；
2. 代码按层级回滚：UI/API 摘要 → Provider 接线 → 目录/解析器；
3. 不得通过恢复全局 `8192` 掩盖目录或解析器错误。

## 已知限制

- 目录数字来自 Phase A 调研/审计；官方未公布精确上限的模型保持 `null`；
- `reserved_output_tokens`（治理/限流预留）与请求 `max_tokens` 是两个字段，
  不可混用；
- context budget 耗尽时返回结构化 `MODEL_CONTEXT_BUDGET_EXHAUSTED`，不发送
  `0`/负数/`8192`。

## M1 现状盘点记录（2026-08-07）

生产路径 `8192` 来源定位与分类：

| 位置 | 值 | 分类 | 处置 |
|------|-----|------|------|
| `config/model_manager.py add_model()` | 默认 `max_tokens=8192` | 请求上限（错误） | M5 改为默认 `auto` |
| `core/providers/base.py llm_kwargs()` | `max_tokens fallback 8192` | 请求上限（错误） | M4 改走 resolver，无解析值时用 `UNKNOWN_MODEL_FALLBACK` |
| `core/agent_v2.py _raw_stream()` | `max_tokens fallback 8192` | 请求上限（错误） | M4 改走 `_resolve_request_max_tokens` |
| `config/settings.py governance.rate_limit.reserved_output_tokens` | `8192` | 治理/限流预留（**正确，不改**） | 保持 |
| `evals/runner.py _eval_llm_kwargs` | pop 掉 max_tokens | 评测不设上限（**正确，不改**） | 保持 |

关键边界确认：
- `ModelCapabilities.max_output_tokens`（Phase A 能力调研值）**未被任何请求路径消费**，
  是死数据；M4 只把它作为 resolver 的 `provider_default` 输入之一。
- 发现列表主键为 Provider 返回的真实 `model_id`，`_parse_discovered_models` 只保留
  allowlist 字段（id/owned_by/context_window/max_output_tokens/max_completion_tokens）。
  **id 是唯一主键**：nickname / owned_by / UI 显示名均不参与目录查找；发请求仍使用
  原始 Provider id（`resolve_output_limit` 内 `model_id` 原样保留，仅目录键 casefold）。
- 旧配置正整数 `max_tokens` 按用户显式覆盖处理（ML7），不悄悄扩大费用；
  用户可通过 `config model-limits set-auto` 手动迁移。
- 零回归基线：Phase 3 前后全量 pytest 均通过（2026-08-07：10051 passed, 2 skipped）。

评测基线（`python -m evals.cli run --backend agent --compare-baseline
evals/baselines/latest-agent.json`）结果见 `artifacts/phase3-evals-baseline.log`；
与 Phase 1 基线对比无通过率回归（无 API Key 时该命令跳过真实评测，见 §7.6 说明）。
