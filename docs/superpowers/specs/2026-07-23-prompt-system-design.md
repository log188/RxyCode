# Prompt 注册表系统设计

> 日期: 2026-07-23
> 状态: 已批准（方案 B: Python 原生 Prompt 注册表）

## 1. 目标

缝合 OpenHands prompt 设计模式，构建 `core/prompts/` 注册表，实现：
- **模板收敛**：所有 pipeline 阶段的 role prompt 收敛到单一来源
- **工具清单单一来源**：从 `ToolRegistry` 动态注入工具描述
- **few-shot 示例**：每个阶段附带结构化示例
- **re_planner 修复**：统一使用共享 prompt 基础设施
- **多语言**：配置化 locale，模板根据 locale 渲染
- **evals 回归验证**：新增 prompt 质量评估任务

## 2. 架构

```
core/prompts/
├── __init__.py          # 导出 get_system_prompt, build_user_message, get_role_prompt
├── registry.py          # PromptRegistry: 注册/查询/渲染 role prompts
├── templates.py         # 所有 prompt 模板 (Python 字符串常量)
├── few_shot.py          # few-shot 示例数据
├── i18n.py              # 多语言文本包 (zh, en)
└── tool_list.py         # 从 ToolRegistry 动态生成工具描述
```

保留 `core/prompts.py` 作为向后兼容入口（re-export 新包的公共 API）。

### 2.1 PromptRegistry

```python
class PromptRegistry:
    """所有 pipeline 阶段 role prompt 的单一来源。
    
    设计缝合自 OpenHands:
    - XML 标签结构化分区 (<ROLE>, <INSTRUCTIONS>, <OUTPUT_FORMAT>, <EXAMPLES>)
    - 工具描述从 ToolRegistry 动态注入
    - few-shot 示例可选附加
    - locale 感知的多语言渲染
    """
    def register(self, key: str, template: str, few_shot: list[dict] | None = None)
    def get_role_prompt(self, key: str, locale: str = "zh", tools: list[str] | None = None) -> str
    def list_keys(self) -> list[str]
```

### 2.2 模板结构 (XML 标签分区)

每个 role prompt 使用 OpenHands 风格的 XML 标签：

```
<ROLE>
You are the Goal Planner stage of the RxyCode pipeline.
</ROLE>

<INSTRUCTIONS>
Analyze the user's request and extract:
1. goal: A single sentence describing the final objective
2. constraints: A list of constraints
3. output_format: The desired output format
</INSTRUCTIONS>

<OUTPUT_FORMAT>
Respond with JSON only: {"goal": "...", "constraints": ["..."], "output_format": "markdown"}
</OUTPUT_FORMAT>

<EXAMPLES>
{few_shot_examples}
</EXAMPLES>
```

### 2.3 工具清单单一来源

`tool_list.py` 从 `ToolRegistry` 动态生成工具描述：

```python
def get_tool_descriptions(tool_names: list[str] | None = None) -> str:
    """从 ToolRegistry 生成工具清单文本。
    
    不再在 system prompt 中硬编码工具名，
    而是运行时从注册表动态注入。
    """
    from RxyCode.RxyCode1_1_0.tools.registry import registry
    if tool_names is None:
        return registry.get_descriptions()
    # 按 tool_names 过滤
    ...
```

`UNIFIED_SYSTEM_PROMPT` 不再硬编码工具列表，而是通过 `get_system_prompt(tools=True)` 在运行时注入。

### 2.4 few-shot 示例

每个阶段附带 1-2 个结构化示例：

```python
FEW_SHOT_EXAMPLES = {
    "goal_planner": [
        {
            "input": "写一个 Python 爬虫，爬取豆瓣电影 Top 250",
            "output": '{"goal": "实现豆瓣电影 Top 250 爬虫", "constraints": ["Python", "requests+bs4", "输出CSV"], "output_format": "code"}'
        },
    ],
    "decomposer": [
        {
            "input": "Task: 实现用户注册登录系统",
            "output": '[{"title": "设计数据库表结构", ...}, {"title": "实现注册API", ...}]'
        },
    ],
    # ...每个阶段都有
}
```

### 2.5 多语言 (i18n)

```python
I18N_TEXTS = {
    "zh": {
        "language_requirement": "始终使用中文回复用户。即使用户使用英文提问，也使用中文回答。代码注释使用中文。",
        "time_label": "当前时间",
        "context_label": "对话上下文",
    },
    "en": {
        "language_requirement": "Always respond in English.",
        "time_label": "Current time",
        "context_label": "Conversation Context",
    },
}

def get_locale() -> str:
    """从 config 读取 locale，默认 zh。"""
    from RxyCode.RxyCode1_1_0.config.settings import load_config
    cfg = load_config() or {}
    return cfg.get("locale", "zh")
```

### 2.6 re_planner 修复

当前 `re_planner.py` 的问题：
1. 不使用 `get_system_prompt()` / `build_user_message()`，直接用 `prompt.format()` + 裸 `HumanMessage`
2. 不注入 system prompt，导致缓存失效

修复后：
```python
from RxyCode.RxyCode1_1_0.core.prompts import get_system_prompt, build_user_message, get_role_prompt

# 使用注册表获取 role prompt
role_prompt = get_role_prompt("re_planner", tools=tool_names)
user_msg = build_user_message(role_prompt, task_content, memory_context)
messages = [SystemMessage(content=get_system_prompt()), HumanMessage(content=user_msg)]
```

### 2.7 validator_node bug 修复

`core/graph.py` 中 `validator_node` 引用未定义的 `memory` 变量（第 279 行）。修复为从 state 获取：
```python
memory = state["_memory"]  # 添加这行
```

## 3. 数据流

```
用户输入
  ↓
get_system_prompt(tools=True)  ← tool_list.py 从 ToolRegistry 注入
  ↓
build_user_message(role, content, ctx)  ← i18n.py 提供 locale 标签
  ↓
get_role_prompt("goal_planner")  ← registry.py 从 templates.py + few_shot.py 渲染
  ↓
LLM 调用 (SystemMessage + HumanMessage)
```

## 4. 向后兼容

`core/prompts.py` 保留为兼容入口：
```python
# core/prompts.py (兼容层)
from RxyCode.RxyCode1_1_0.core.prompts.registry import (
    get_system_prompt, build_user_message, get_role_prompt
)
```

现有调用方 `from core.prompts import get_system_prompt, build_user_message` 无需修改。

## 5. 修改清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `core/prompts/__init__.py` | 新建 | 导出公共 API |
| `core/prompts/registry.py` | 新建 | PromptRegistry 类 |
| `core/prompts/templates.py` | 新建 | 所有 role prompt 模板 (XML 标签结构) |
| `core/prompts/few_shot.py` | 新建 | few-shot 示例数据 |
| `core/prompts/i18n.py` | 新建 | 多语言文本包 |
| `core/prompts/tool_list.py` | 新建 | 从 ToolRegistry 动态生成工具描述 |
| `core/prompts.py` | 修改 | 改为兼容层 re-export |
| `planning/goal_planner.py` | 修改 | 从 registry 获取 role prompt |
| `planning/decomposer.py` | 修改 | 从 registry 获取 role prompt |
| `execution/executor.py` | 修改 | 从 registry 获取 role prompt |
| `validation/validator.py` | 修改 | 从 registry 获取 role prompt |
| `validation/re_planner.py` | 修改 | 修复：使用共享 prompt 基础设施 |
| `synthesis/synthesizer.py` | 修改 | 从 registry 获取 role prompt |
| `core/graph.py` | 修改 | 修复 validator_node 的 memory 变量 bug |
| `tests/test_core/test_prompts.py` | 修改 | 新增 registry/i18n/few_shot 测试 |
| `evals/tasks/readcode-prompt-registry.yaml` | 新建 | prompt 注册表回归验证任务 |

## 6. 测试策略

1. **单元测试** (`tests/test_core/test_prompts.py`):
   - PromptRegistry 注册/查询/渲染
   - i18n locale 切换
   - few-shot 注入
   - 工具描述动态注入
   - 向后兼容性 (旧 API 仍可用)

2. **evals 回归** (`evals/tasks/readcode-prompt-registry.yaml`):
   - 验证 prompt 注册表包含所有 6 个阶段
   - 验证工具描述从 ToolRegistry 注入
   - 验证 re_planner 使用共享基础设施

## 7. 成功标准

- [x] 所有 6 个 pipeline 阶段的 role prompt 从 PromptRegistry 获取
- [x] system prompt 不再硬编码工具列表
- [x] re_planner 使用 `get_system_prompt()` + `build_user_message()`
- [x] validator_node 的 `memory` bug 修复
- [x] locale 可通过 config 配置
- [x] 现有测试全部通过
- [x] 新增 eval 任务验证 prompt 注册表
