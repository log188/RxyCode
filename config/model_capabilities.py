"""模型能力元数据。

RxyCode 历史上把所有模型都当成 "OpenAI 兼容 + 全局常量" 处理：上下文窗口
硬编码 256000，token 一律用 gpt-4o 的分词器估算，provider 的 usage 字段靠
"两个都试一遍" 猜。模型一多这套就撑不住了。

本模块把这些隐式假设变成显式的、可配置的能力声明。

优先级（高到低）：
  1. 用户在模型配置里显式写的字段
  2. Provider 的探测结果
  3. Provider 的默认值
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

#: token 估算方式。
#: - "tiktoken:<encoding>" 用 tiktoken 的具名编码
#: - "chars:<ratio>"       用 字符数 / ratio 估算（无官方分词器时的兜底）
TokenizerSpec = str

#: 结构化输出的实现方式。
#: - "function_calling" 走 OpenAI 原生 tools 字段
#: - "json_in_text"     让模型在正文里输出 JSON，我们扫出来（RxyCode 现有的
#:                      planning/validation/synthesis 路径就是这种）
StructuredOutputMode = Literal["function_calling", "json_in_text"]


@dataclass(frozen=True)
class ModelPricing:
    """每百万 token 单价（美元）。Phase E 的 CostAccountant 用它做成本核算。

    字段来源必须是 A0 调研报告（§7.X）里带 URL 的官方定价页。
    任何字段为 None 时调用方必须显式处理（保守高估或警告），不得静默当 0。
    """

    input_per_mtok: float | None = None
    output_per_mtok: float | None = None
    cached_input_per_mtok: float | None = None
    #: 写缓存 token 单价（§7.2 ③：5.6+ 按 uncached input × 1.25 计费）。
    #: 更早型号写缓存无额外费，通常为 None。
    cache_write_per_mtok: float | None = None
    #: 显式缓存创建价（§7.7 问 7a：cache_control 显式标记创建，如 Qwen 2.5/7.5 等）。
    #: None = 未找到 / 不适用。
    cache_creation_per_mtok: float | None = None
    #: 显式缓存命中价（§7.7 问 7a：cache_control 显式命中，如 Qwen 0.2/0.6 等）。
    #: None = 未找到 / 不适用。
    explicit_cache_hit_per_mtok: float | None = None
    as_of: str = ""
    source_url: str = ""


@dataclass(frozen=True)
class UsageFieldMap:
    """不同 provider 的 token usage 字段名差异。

    对应 core/agent_v2.py::_extract_cache_read 里原先的 "两个字段都试一遍"。
    """

    #: 命中前缀缓存的 token 数所在字段（顶层 usage 下）
    cache_read_flat: tuple[str, ...] = ("prompt_cache_hit_tokens",)
    #: 命中前缀缓存的 token 数所在嵌套路径，形如 ("prompt_tokens_details", "cached_tokens")
    cache_read_nested: tuple[tuple[str, str], ...] = (
        ("prompt_tokens_details", "cached_tokens"),
        ("input_token_details", "cache_read"),
    )
    #: 写入前缀缓存的 token 数所在嵌套路径（§7.2 ③：Chat Completions 5.6+ 的
    #: `cache_write_tokens`；写入按 uncached input × 1.25 计费）。
    cache_write_nested: tuple[tuple[str, str], ...] = (
        ("prompt_tokens_details", "cache_write_tokens"),
    )
    #: 写入前缀缓存的 token 数所在顶层 usage 字段（§7.8 ③：Anthropic 顶层
    #: `usage.cache_creation_input_tokens`；与 OpenAI 嵌套 cache_write_tokens 不同）。
    cache_write_flat: tuple[str, ...] = ()
    #: 推理 token 数所在嵌套路径（§7.2 ⑤：Chat Completions 的
    #: `completion_tokens_details.reasoning_tokens`——是**计数**而非内容；
    #: OpenAI 不暴露原始 reasoning 文本）。
    reasoning_nested: tuple[tuple[str, str], ...] = (
        ("completion_tokens_details", "reasoning_tokens"),
    )
    #: 推理/思考内容所在字段（在 delta 或 message 上）
    reasoning: tuple[str, ...] = ("reasoning_content",)


@dataclass(frozen=True)
class ModelCapabilities:
    """一个具体模型的能力声明。

    所有默认值都**刻意**与 Phase A 之前的硬编码行为一致，这样未识别的模型
    落到默认值时行为不变。改默认值等于改所有模型的行为，不要随手改。
    """

    #: provider 标识，例如 "openai" / "deepseek" / "anthropic" / "qwen"
    provider: str = "openai"

    #: 上下文窗口（token）。默认值 256000 来自 utils/streaming.py:47 的旧硬编码。
    context_window: int = 256_000

    #: 触发上下文压缩的阈值。默认 232000 来自 config/settings.py:299。
    #: 一般设为 context_window 的 ~90%。
    compaction_threshold: int = 232_000

    #: 模型最大输出 token 上限（§7.2 ③ 等信息性能力值；默认 None = 未调研/未知）。
    #: 仅承载调研数据，**不改变默认输出**：llm_kwargs 仍由用户 `max_tokens`
    #: 配置决定（默认 8192），避免默认超大输出成本。
    max_output_tokens: int | None = None

    #: token 估算方式。默认 gpt-4o 来自 core/agent_v2.py:207 的旧硬编码。
    tokenizer: TokenizerSpec = "tiktoken:o200k_base"

    #: 是否支持 OpenAI 风格的原生 function calling。
    #: False 时 fast path 必须降级到 json_in_text。
    #: None = 未调研/未证实（§7.7 ③：qwen3.8-max-preview 无型号页勾选表），消费方
    #: 按 falsy 处理（不启用 FC），不得与「明确不支持」混淆但行为同为保守关闭。
    supports_function_calling: bool | None = True

    #: 是否支持厂商内置工具（§7.7 ③ Q1 第 3 能力列「内置工具」）。
    #: 仅承载调研数据（产品层 / Harness 不得覆盖）；None = 未找到。
    #: 默认 None 不改变任何现有行为。
    supports_builtin_tools: bool | None = None

    #: 计费形态标识（§7.7 问 7b：qwen3.8-max-preview 仅 Token Plan Credits）。
    #: 空串 = 按量（默认）；"token_plan_credits" 等由 Phase E CostAccountant 消费。
    billing: str = ""

    #: 是否是推理型模型（会产出 reasoning/thinking 内容）。
    supports_reasoning: bool = False

    #: 推理型模型通常不接受 temperature / top_p，传了会 400。
    accepts_temperature: bool = True

    #: 是否支持多模态图像输入。Phase C 会用到；Phase A 只是把字段先占上。
    supports_vision: bool = False

    #: 是否支持 prompt 前缀缓存（cache_control）。
    #: 对应 core/agent_v2.py:411-441 原先无条件注入 cache_control 的行为。
    supports_prompt_cache: bool = True

    #: 结构化输出走哪条路。
    structured_output: StructuredOutputMode = "function_calling"

    #: prompt 变体标识。core/prompts 会用 (stage, locale, prompt_variant)
    #: 三元组查模板；找不到变体就回退到通用模板。
    prompt_variant: str = "default"

    #: usage / reasoning 的字段名映射
    usage_fields: UsageFieldMap = field(default_factory=UsageFieldMap)

    #: 定价（Phase E 用）。默认空对象 = "未知"，不改变任何现有行为。
    pricing: ModelPricing = field(default_factory=ModelPricing)

    #: 推理力度档位映射：fast / balanced / deep → 厂商参数。
    #: 例如 {"fast": "minimal", "balanced": "medium", "deep": "high"}。
    #: A21 的延迟旋钮与 fast path 用它；为空表示该模型不支持档位控制。
    effort_presets: dict[str, str] = field(default_factory=dict)

    #: 该模型是否**默认开启 thinking（推理）模式**（API 层行为）。
    #: True = 确认支持后默认打开（§7 各批第 5 问结论）；False = 不主动发
    #: thinking 参数（保持现状行为）。
    #: ⚠️ 与前端"thinking 面板"无关：面板只是**展示** reasoning_content
    #: 思维链（_flush_thinking / write_reasoning 的显示层），模型开不开
    #: thinking 是 **API 层**的行为，由本字段 + llm_kwargs 决定。面板开着
    #: 而模型没开 thinking = 面板空转；面板关着而模型开了 = 思维链不展示
    #: 但仍在消耗 token。二者不互相绑定。
    thinking_default_on: bool = False

    #: 该模型族 prompt cache 的最小可缓存前缀（token）。Anthropic 系有明确
    #: 下限（如 512/1024/4096）；OpenAI/Kimi/MiniMax 自动缓存有各自要求；
    #: 未找到明确下限 → None（A19，§7 各批第 4 问）。
    cache_min_block_tokens: int | None = None

    #: 缓存 TTL（秒）。None = 不适用（自动缓存 / 未知 / 官方未承诺固定 TTL）。
    #: Anthropic/Qwen 显式缓存 TTL 5min=300s；OpenAI GPT-5.6 30m=1800s（A19，§7 第 4 问）。
    cache_ttl_s: int | None = None

    #: 断点布局（Anthropic 系显式 cache_control 用，最多 4 个）。
    #: 取值按"静态在前、动态在后"排序，只允许打在恒定内容末尾：
    #:   ["tools", "system", "session_static", "tail"]
    #: 空元组 = 不用显式断点。A8 的 _apply_cache_control 读取它（A19）。
    cache_breakpoints: tuple[str, ...] = ()

    #: few-shot 注入策略（A20）。None = 现状（全量注入，A9 前的行为）。
    #:   "full" 全量 / "first2" 只留前 2 条 / "none" 不注入
    #: A9 的 get_role_prompt(include_few_shot=...) 消费。
    few_shot_policy: str | None = None

    #: 工具描述发送策略（A20）。None = 现状（全量发送）。
    #:   "full" 全量 / "subset" 按任务子集（由调用方决定子集，会话内固定）
    #: agent_v2._get_core_tools 组包时消费。
    tool_send_policy: str | None = None

    #: 工具输出截断阈值（token）（A20）。None = 现状（不截断）。
    #: agent_v2._maybe_compress_context 按此截断注入上下文的工具结果文本副本
    #: （保留头尾；**不**改 ToolMessage 对象本身，避免破坏 tool_call_id 契约）。
    tool_output_token_limit: int | None = None

    #: 未归类的 provider 特有参数，会原样透传给 LLM 构造函数
    extra_body: dict[str, Any] = field(default_factory=dict)

    #: OpenAI 系是否要求请求级 prompt_cache_key=session_id（B2，codex/kimi 语义）。
    #: True = 请求组装处注入 prompt_cache_key；False = 不注入（DeepSeek 自动前缀、
    #: Anthropic 显式断点、未知模型现状不变）。默认 False 保持现状行为（CB8）。
    prompt_cache_key_required: bool = False

    def merged_with_overrides(self, overrides: dict[str, Any]) -> "ModelCapabilities":
        """应用用户在模型配置里写的显式覆盖。

        只接受本 dataclass 已声明的字段名，未知字段忽略（不报错），因为
        model_config 里还混着 base_url / api_key 等非能力字段。
        """
        known = {f for f in self.__dataclass_fields__ if f != "usage_fields"}
        applied = {k: v for k, v in overrides.items() if k in known}
        if not applied:
            return self
        return replace(self, **applied)


#: 兜底能力：完全等价于 Phase A 之前的全局硬编码行为。
DEFAULT_CAPABILITIES = ModelCapabilities()


def resolve_graph_context_token_limit(
    cfg: dict[str, Any] | None,
    caps: Any = None,
) -> int:
    """Resolve LangGraph compaction threshold from config override or model caps."""
    context_cfg = (cfg or {}).get("context") or {}
    limit = context_cfg.get("graph_context_token_limit")
    if limit:
        return max(1000, int(limit))
    if caps is not None:
        threshold = getattr(caps, "compaction_threshold", None)
        if threshold:
            return max(1000, int(threshold))
    return 232_000
