# B9 独立模型审计证据链（2026-08-11）

B9 卡（per-model 缓存契约层）审计产物。审查角色：zen/gpt-5.6-luna（`https://opencode.ai/zen/v1`）。

## 实现范围

1. **model_catalog.json 追加 9 家 cache_contract**：deepseek×2 / openai×2（含 opencode-go）/
   kimi×2 / qwen×2 / anthropic×2 / mimo×2 / minimax / glm / grok×2（16 条 record）。
   每条含 cache_mode（auto|explicit_breakpoints|cache_key|auto_and_key）、
   cache_hit_discount、cache_ttl_hours、min_cache_tokens、breakpoints_max、
   breakpoint_lookback、usage_fields（cached/cache_read/cache_creation/cost_ticks/reasoning
   路径）、reasoning_contract（mandatory_echo|thinking_blocks_echo|none|no_thinking）、
   thinking_param、temperature_override（MiMo 1.0/0.95）、prompt_cache_key_required。
2. **core/catalog.py**：契约读取唯一入口——get_contract / read_cached_tokens /
   read_reasoning_tokens / read_cost_ticks / hit_discount / reasoning_contract /
   temperature_override / requires_prompt_cache_key / reset_contract_cache。
   未识别模型 → None/0（CB8）。
3. **usage 归一化**：点分路径读取（DeepSeek prompt_tokens_details.cached_tokens、
   Kimi cached_tokens、Claude cache_read_input_tokens、OpenAI cached_input_tokens、
   Grok cached_prompt_text_tokens、MiMo prompt_tokens_details.cached_tokens）。
4. **schema 扩展**：model_catalog.schema.json 定义 cache_contract（enum/required 校验）。
5. **分派改造**：_apply_cache_control（cache_mode=explicit_breakpoints 才注入断点）、
   _raw_stream（prompt_cache_key_required 以契约为准）——caps 兜底（CB8）。
6. **限制性规范 9 条测试**：reasoning 回传 / MiMo 温度强制 / DeepSeek 必回传 /
   Qwen schema 一致 / Kimi key 恒定 / Claude 字节匹配 / 换模型失效 / Grok 单独计费 /
   TPM 配额不臆断。
7. **conftest 隔离**：reset_contract_cache 加入 _isolate_process_singletons。

## 验收证据

- `b9-pytest-v.txt`: 25 passed（test_model_contracts）
- `b9-ruff.txt`: All checks passed
- 全量回归 test_core+test_cache+test_memory+test_validation+test_execution+test_tools
  +test_model_catalog+test_model_limits: 9090 passed, 2 failed（P7 lazy-import 遗留）
- evals GATE PASS 94.7% ≥ 89.5%（零回归，1 改善）；唯一失败 websearch-summary 基线即 FAIL
- 验收方式：并行 4 组 + 失败重试 3 轮（本地工具，不提交）

## 审计轮次（3 轮）

| 轮次 | 结论 | 核心阻断项 |
|---|---|---|
| R1 | FAIL | Qwen 显式断点被 anthropic 早退拦截；Kimi prompt_cache_key 被 openai 条件拦截；schema required 不足；规范测试非行为测试 |
| R2 | FAIL | Kimi 测试非真行为测试（需 payload 级）；模型切换未使 key 失效（需 provider:model 派生）；breakpoints_max null 处理 |
| R3 | **PASS** | 无剩余阻断项，判据 1-6 + CB1-CB8 全过 |

## 最终结论

zen/gpt-5.6-luna 第 3 轮审计 **PASS**：B9 完成判据 1-6 全过，八条硬约束 CB1-CB8 无违反。
B9 卡可在开发文档验收处打钩（2026-08-11）。

