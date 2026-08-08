# RxyCode v1.2.8

RxyCode 是一个规划执行型的 AI 编程助手：把复杂任务自动拆解成子任务，通过安全工具编排器执行、验证结果后综合出最终答案，全程实时流式输出到终端界面。
> **推荐使用 v1.2.8。** 本版完成模型适配层的全面收尾：新增/补全 DeepSeek v4、豆包（Doubao）、Anthropic Claude 5 全家族的模型支持，并为每个模型族带上了精确的能力、定价、缓存与思考参数；同时修复了多模型共用端点时"识别串台"和未知模型错误继承能力的问题。

## 简要说明 / Summary

这一版是**模型支持全面版**：Phase A 模型适配层全部完成并通过出口检查。
- 新增：DeepSeek v4（flash/pro）思考型模型的完整适配
- 新增：豆包（Doubao / ark）provider 收尾，pro 保持保守边界
- 新增：Anthropic Claude 5 家族五主力（Opus 5 / Sonnet 5 / Haiku 4.5 / Fable 5 / Opus 4.8）完整适配
- 修复：未知模型不再继承已调研能力（context / 定价 / 思考 / 缓存）
- 修复：按子串匹配模型的误识别（如 `"v4" in name`、`"ark" in url`）
- 验证：Phase A 出口检查通过，evals 对比基线无回归（94.7% ≥ 89.5%）

## 亮点 / Highlights

- **模型支持大幅扩展** —— 一次补齐 DeepSeek v4、豆包、Anthropic Claude 5 三个家族，加上此前的 Kimi / GLM / MiniMax / MIMO / Qwen，模型矩阵从"能用"变成"适配完整"
- **能力声明精确可靠** —— 每个模型的能力字段（上下文、最大输出、思考默认、缓存参数、定价）都来自带来源 URL 的三方审计调研，未知变体一律保守
- **不再"识别串台"** —— 修掉了 `"v4" in name`、`"ark" in url` 这类宽松匹配：豆包不会抢走 ark 上的其他模型，未知 v4 变体不会误当 v4-flash
- **thinking 模式稳定** —— DeepSeek v4 / Claude 的思考内容正确回传，工具调用轮次不再触发 400
- **零回归发布** —— 10412 个测试全绿，evals 对比基线 94.7% vs 89.5%，token 消耗与耗时双双下降

## 详细说明 / Details

### 新增功能

- **DeepSeek v4 适配（A22）** —— 精确识别 `deepseek-v4-flash` / `deepseek-v4-pro`：1M 上下文、384K 最大输出、thinking 默认开启（effort 档位 fast/balanced/deep → low/high/max）；旧型号 `deepseek-chat` / `deepseek-reasoner` 保持 A3 行为不回归；带 tools 的轮次正确回传 `reasoning_content`（否则 400）
- **豆包 Doubao provider 收尾（A23）** —— 适配火山方舟 ark coding 端点：256k 上下文、256k 软上限输出、`reasoning_content` 提取、function calling 实测可用；`doubao-seed-2.1-pro` 未实测，能力声明保持保守（R1 边界）
- **Anthropic Claude 5 家族（A18）** —— 五主力完整适配（Opus 5 / Sonnet 5 / Haiku 4.5 / Fable 5 / Opus 4.8）：1M / 200k 上下文、128k / 64k 最大输出、按型号思考默认值、分条定价（含缓存写入价）、缓存最小块 / TTL / 断点；`supports_prompt_cache` 按端点区分（原生 api.anthropic.com 才开启）；非默认采样参数按官方 400 契约拒绝
- **per-model 优化旋钮（A19-A21）** —— 缓存参数（最小块 / TTL / 断点布局）、token 治理（输出上限 / 截断策略）、延迟 / 思考档位（effort presets），均按模型族落到能力字段

### 修复的 Bug

- **未知模型能力泄漏（DC1）** —— 未调研的模型变体（如 `deepseek-v4-foo`、`doubao-seed-3.0`、`claude-opus-3`）不再继承已调研模型的能力（context / 定价 / 思考 / 缓存 / prompt variant），一律回落到全局默认
- **子串匹配误识别** —— 把 `"v4" in name`、`"ark" in url`、`"v4-flash" in name` 等宽松匹配改成精确 hostname / 模型名匹配：豆包不再抢走 ark 上的 minimax / glm，未知 v4 变体不会误当 v4-flash
- **bash 绝对路径逃逸与 Windows 递归删除防护（stress S1/S12）** —— 收紧工具安全边界

### 验证与回归

- Phase A 出口检查全绿：`ruff check .` 通过、全量 `pytest` **10412 passed / 3 skipped**、`tests/test_providers` 407 passed
- evals 对比基线 **GATE PASS（94.7% ≥ 89.5%）**：pass rate 89.5% → 94.7%（refactor-extract-function FAIL→PASS）、tokens −24.4 万、耗时 −11.3 分钟
- 前端（Ink + OpenTUI）测试全绿；打包契约 / 安装器 / 已装包元数据版本断言全部同步到 1.2.8

## 安装 / Install

**推荐（v1.2.8）：**

```powershell
# Windows
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/xin-yi33/RxyCode/v1.2.8/install.ps1 | iex"
```

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/xin-yi33/RxyCode/v1.2.8/install.sh | sh
```

```bash
uv tool install --force "git+https://github.com/xin-yi33/RxyCode.git@v1.2.8"
```

**下载策略：** 仅本页（v1.2.8）提供 wheel / sdist。更早版本的 GitHub Release **不开放**安装包下载。

## 资产 / Assets

- `rxycode-1.2.8-py3-none-any.whl`
- `rxycode-1.2.8.tar.gz`
