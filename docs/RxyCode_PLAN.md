# RxyCode 开发计划

## 一、项目概述

RxyCode 是一个基于 LangChain/LangGraph 的 CLI 通用 AI Agent，采用 Plan-And-Execute 架构。

## 二、用户目录结构

```
D:\agent-demo\
├── RxyCode/                    # Agent 源码目录
│   ├── main.py                 # CLI 入口
│   ├── cli.py                  # CLI 交互层(输入解析、命令路由、输出渲染)
│   ├── agent.py                # Agent 主编排(Plan-And-Execute 循环)
│   ├── prompts/                # 提示词模板
│   │   ├── system_prompt.txt
│   │   ├── plan_prompt.txt
│   │   ├── replan_prompt.txt
│   │   ├── execute_prompt.txt
│   │   └── compress_prompt.txt
│   ├── tools/                  # 工具实现
│   │   ├── __init__.py
│   │   ├── registry.py         # 工具注册表
│   │   ├── bash.py
│   │   ├── read.py
│   │   ├── write.py
│   │   ├── edit.py
│   │   ├── glob_tool.py
│   │   ├── grep_tool.py
│   │   ├── webfetch.py
│   │   ├── websearch.py
│   │   └── file_ops.py         # 文件操作工具集
│   ├── chains/                 # LangChain Chains
│   │   ├── __init__.py
│   │   ├── plan_chain.py
│   │   ├── replan_chain.py
│   │   ├── execute_chain.py
│   │   └── compress_chain.py
│   ├── memory/                 # 记忆系统
│   │   ├── __init__.py
│   │   ├── short_term.py       # 短时记忆(ConversationBufferWindowMemory)
│   │   ├── long_term.py        # 长时记忆(文件存储 + 摘要压缩)
│   │   └── manager.py          # 记忆管理器(自动转换、加载)
│   ├── config/                 # 配置
│   │   ├── __init__.py
│   │   ├── settings.py         # 配置加载/管理
│   │   └── model_manager.py    # 模型添加/测试/管理
│   ├── cache/                  # 缓存优化
│   │   ├── __init__.py
│   │   └── prompt_cache.py     # 提示词缓存策略
│   └── utils/                  # 工具函数
│       ├── __init__.py
│       ├── streaming.py        # 流式输出处理
│       └── parser.py           # 输出解析器(thinking/final_answer)
├── data/                       # 运行时数据目录
│   ├── config.yaml             # 模型配置文件
│   ├── memory/                 # 记忆持久化
│   │   ├── sessions/           # 会话记忆
│   │   └── projects/           # 项目记忆
│   └── cache/                  # 缓存数据
├── requirements.txt
├── setup.py
├── README.md
└── RxyCode_PLAN.md             # 本文件
```

## 三、技术选型

| 组件 | 技术 | 说明 |
|------|------|------|
| Agent 框架 | LangChain | Plan-And-Execute 架构 |
| LLM 接口 | langchain-openai | 兼容 OpenAI API 格式的所有模型 |
| CLI 框架 | click + rich | 命令行解析 + 美化输出 |
| 配置管理 | PyYAML | YAML 配置文件 |
| 记忆存储 | 文件系统 | Markdown 文件持久化 |
| 流式输出 | LangChain astream | 异步流式 token 输出 |

## 四、模型管理功能(重要)

### 4.1 添加模型

用户通过 CLI 命令添加模型,需要手动输入:
- **模型名称**:如 `mimo-v2.5`、`gpt-4o` 等
- **API Key**:模型的 API 密钥
- **API Base URL**:模型的 API 地址(如 `https://api.openai.com/v1`)

```bash
# 添加模型
python -m RxyCode config add-model

# 交互式输入:
# 模型名称: mimo-v2.5
# API Key: sk-xxx
# API Base URL: https://api.example.com/v1
```

### 4.2 测试模型连接

添加模型后自动测试连接,也可手动测试:

```bash
# 测试模型连接
python -m RxyCode config test-model mimo-v2.5

# 输出:
# ✅ 模型 mimo-v2.5 连接成功
#    响应时间: 1.2s
#    模型返回: "Hello! How can I help you?"
```

### 4.3 模型配置文件格式

```yaml
# data/config.yaml
models:
  mimo-v2.5:
    api_key: "sk-xxx"
    base_url: "https://api.example.com/v1"
    model_name: "mimo-v2.5"
    max_tokens: 8192
    temperature: 0.7

  gpt-4o:
    api_key: "sk-xxx"
    base_url: "https://api.openai.com/v1"
    model_name: "gpt-4o"
    max_tokens: 8192
    temperature: 0.7

active_model: "mimo-v2.5"

memory:
  short_term_window: 20
  long_term_threshold: 50
  compress_model: "mimo-v2.5"

cache:
  enabled: true
  prompt_prefix_cache: true
  ttl: 3600
```

### 4.4 使用指定模型

```bash
# 使用默认模型
python -m RxyCode chat

# 指定模型
python -m RxyCode chat --model mimo-v2.5

# 切换默认模型
python -m RxyCode config set-active-model mimo-v2.5
```

## 五、缓存优化策略(重要)

### 5.1 提示词前缀缓存(Prompt Prefix Caching)

**核心思路**:保持 system prompt 和历史前缀不变,只追加新内容,利用模型的 KV Cache。

- System prompt 固定不变,作为前缀
- 工具描述固定不变,紧随 system prompt
- 历史消息按时间顺序排列,只在末尾追加新消息
- **不要**在每次请求时重新排列或修改历史消息

### 5.2 对话上下文缓存

- 维护一个会话级别的上下文窗口
- 当对话超过阈值时,压缩早期对话为摘要
- 摘要作为 system context 注入,保持前缀稳定

### 5.3 工具描述缓存

- 工具描述在会话开始时一次性加载
- 不随每次请求变化,提高前缀缓存命中率

### 5.4 实现方案

```python
class PromptCacheManager:
    """管理提示词缓存,最大化 KV Cache 命中率"""

    def __init__(self):
        self._system_prefix = None  # 缓存的系统前缀
        self._tools_prefix = None   # 缓存的工具描述前缀

    def build_messages(self, system_prompt, tools_desc, history, new_input):
        """
        构建消息列表,保持前缀稳定:
        [system_prompt] + [tools_desc] + [history...] + [new_input]
        """
        messages = []

        # 固定前缀(不变 → 缓存命中)
        if self._system_prefix is None:
            self._system_prefix = system_prompt
        messages.append({"role": "system", "content": self._system_prefix})

        if self._tools_prefix is None:
            self._tools_prefix = tools_desc
        messages.append({"role": "system", "content": self._tools_prefix})

        # 历史消息(只追加,不修改)
        messages.extend(history)

        # 新输入
        messages.append({"role": "user", "content": new_input})

        return messages
```

### 5.5 缓存友好规则

1. **System prompt 绝不变化** — 放在最前面
2. **工具描述固定** — 紧随 system prompt
3. **历史消息只追加不修改** — 保持前缀稳定
4. **压缩摘要替换时,保持位置不变** — 用摘要替换原始消息,但不改变其他消息的顺序
5. **避免在每次请求中注入动态时间戳等变化内容**

## 六、实施步骤

### Phase 1: 项目骨架(基础结构)
1. 创建目录结构
2. 创建 requirements.txt 和 setup.py
3. 创建 README.md
4. 实现配置加载(config/settings.py)
5. 实现模型管理器(config/model_manager.py)

### Phase 2: 工具系统
6. 实现工具注册表(tools/registry.py)
7. 实现核心工具:bash, read, write, edit, glob, grep

### Phase 3: 记忆系统
8. 实现短时记忆(memory/short_term.py)
9. 实现长时记忆(memory/long_term.py)
10. 实现记忆管理器(memory/manager.py)

### Phase 4: Chain 系统
11. 实现 Plan Chain
12. 实现 RePlan Chain
13. 实现 Execute Chain
14. 实现 Compress Chain

### Phase 5: Agent 核心
15. 实现 Agent 主编排(agent.py)
16. 实现缓存管理器(cache/prompt_cache.py)
17. 实现流式输出(utils/streaming.py)

### Phase 6: CLI 交互层
18. 实现 CLI 入口(main.py)
19. 实现命令路由(cli.py)
20. 实现三种模式切换

### Phase 7: 提示词模板
21. 编写所有提示词模板文件

### Phase 8: 测试与验证
22. 单元测试
23. 集成测试(多轮对话测试)
24. 端到端测试

## 七、启动方式

```bash
# 安装依赖
cd D:\agent-demo
pip install -r requirements.txt

# 添加模型
python -m RxyCode config add-model

# 启动 Agent
python -m RxyCode

# 或指定模型启动
python -m RxyCode --model mimo-v2.5
```

## 八、注意事项

1. 所有 LLM 调用使用流式输出(astream)
2. thinking 内容实时输出,用 `<thinking>` 标签包裹
3. 工具调用结果不计入 final_answer
4. 模型确认完成用户提问后才输出 `<final_answer>`
5. 缓存策略以不牺牲功能为前提
