"""P6 request routing: explicit directives and inventory coverage."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from RxyCode.RxyCode1_1_0.core.agent_v2 import AgentV2
from RxyCode.RxyCode1_1_0.core.request_routing import (
    ROUTING_INVENTORY,
    RoutingDirective,
    detect_download_intent,
    has_structured_pipeline_signal,
    is_simple_query,
    parse_routing_directive,
)


class _Memory:
    async def initialize(self):
        return None

    def load_session(self):
        return None

    def get_context_for_prompt(self):
        return ""

    def add_interaction(self, *_args):
        return None

    def save_session(self):
        return None


def _routed_agent() -> AgentV2:
    agent = object.__new__(AgentV2)
    agent._cancelled = False
    agent._active_task = None
    agent._session_loaded = True
    agent._session_id = "request-routing"
    agent._memory = _Memory()
    agent._llm = None
    agent._tool_orchestrator = None
    agent._tool_tracer = None
    agent._thinking_history = []
    agent._last_thinking = ""
    agent._detect_file_operation = MagicMock(return_value=None)
    agent._detect_download_intent = MagicMock(return_value=None)
    agent._is_simple_query = AgentV2._is_simple_query.__get__(agent, AgentV2)
    agent._is_social_chat = AgentV2._is_social_chat.__get__(agent, AgentV2)
    agent._has_creation_product_intent = AgentV2._has_creation_product_intent.__get__(
        agent, AgentV2
    )
    agent._should_use_subagents = MagicMock(return_value=False)
    agent._fast_reply = AsyncMock(return_value="fast")
    agent._fast_reply_with_tools = AsyncMock(return_value="tool path")
    agent._run_plan_only = AsyncMock(return_value="plan only")
    agent._graph = SimpleNamespace(
        ainvoke=AsyncMock(return_value={"final_response": "graph answer"})
    )
    return agent


REFACTOR = "帮我重构整个项目的认证模块，把代码整理干净。"
CODE_TASK = "分析当前目录的代码并修复 calc.py 里的 bug。"
PROJECT_TASK = "给这个项目补测试并跑一遍。"


def test_routing_inventory_has_twenty_five_sites():
    assert len(ROUTING_INVENTORY) == 25


def test_full_directive_forces_complex_path():
    directive, stripped = parse_routing_directive("/full explain decorators")
    assert directive == RoutingDirective.FORCE_FULL
    assert stripped == "explain decorators"
    assert is_simple_query(stripped, directive=directive) is False


def test_pipeline_alias_forces_complex_path():
    directive, stripped = parse_routing_directive("/pipeline build auth service")
    assert directive == RoutingDirective.FORCE_FULL
    assert is_simple_query(stripped, directive=directive) is False


def test_fast_directive_forces_simple_path_even_for_game_request():
    directive, stripped = parse_routing_directive("/fast 写一个跑酷小游戏")
    assert directive == RoutingDirective.FORCE_FAST
    assert is_simple_query(stripped, directive=directive) is True


def test_auto_keeps_parkour_game_on_tool_pipeline():
    assert is_simple_query("帮我写一个跑酷小游戏") is False


def test_auto_keeps_plain_chat_simple():
    assert is_simple_query("what happened?") is True


def test_file_bugfix_request_is_not_classified_simple():
    text = (
        "当前目录下有一个 calc.py，"
        "请修复 sum_up_to(n) 的 off-by-one bug，"
        "然后运行 pytest。"
    )
    assert has_structured_pipeline_signal(text) is True
    assert is_simple_query(text) is False


def test_mutable_default_bugfix_request_is_not_classified_simple():
    text = (
        "当前目录下的 cart.py 里 Cart 类使用了可变默认参数 items=[]，"
        "请修复这个经典 bug，然后运行 python -m pytest test_cart.py -q 确认通过。"
    )
    assert has_structured_pipeline_signal(text) is True
    assert is_simple_query(text) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [REFACTOR, CODE_TASK, PROJECT_TASK])
async def test_code_project_sentences_do_not_enter_langgraph(text):
    agent = _routed_agent()
    result = await agent._run_impl(text, mode="build")
    assert result == "tool path"
    agent._fast_reply_with_tools.assert_awaited_once_with(text)
    agent._graph.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_plan_mode_code_task_does_not_enter_langgraph():
    agent = _routed_agent()
    result = await agent._run_impl(REFACTOR, mode="plan")
    assert result == "plan only"
    agent._run_plan_only.assert_awaited_once_with(REFACTOR)
    agent._graph.ainvoke.assert_not_awaited()
    agent._fast_reply_with_tools.assert_not_awaited()


@pytest.mark.asyncio
async def test_pipeline_directive_enters_langgraph():
    agent = _routed_agent()
    result = await agent._run_impl("/pipeline " + REFACTOR, mode="build")
    assert result == "graph answer"
    agent._graph.ainvoke.assert_awaited_once()
    agent._fast_reply_with_tools.assert_not_awaited()


def test_relative_py_mention_without_modify_stays_simple():
    assert has_structured_pipeline_signal("calc.py is a common filename") is False
    assert is_simple_query("what does calc.py usually contain?") is True


def test_agent_v2_compat_routing_reexports():
    from RxyCode.RxyCode1_1_0.core.agent_v2 import (
        GIT_ONLY_TOOL_NAMES,
        _GIT_FORCE_RE,
        _PURE_SOCIAL_GREETING_RE,
    )

    assert _PURE_SOCIAL_GREETING_RE.match("hello")
    assert "git" in GIT_ONLY_TOOL_NAMES
    assert _GIT_FORCE_RE.search("必须调用 git 工具")


@pytest.mark.asyncio
async def test_social_tools_failure_returns_comfort_message():
    """FX2 equivalence: build-mode social non-greeting turns that fail on the
    tools fast path return the comfort message, never [error]/research."""
    agent = _routed_agent()
    agent._fast_reply_with_tools = AsyncMock(side_effect=RuntimeError("boom"))
    result = await agent._run_impl("i'm sad", mode="build")
    assert "刚才没能完整回复你" in result


@pytest.mark.asyncio
async def test_compose_social_tools_failure_returns_comfort_message():
    agent = _routed_agent()
    agent._fast_reply_with_tools = AsyncMock(side_effect=RuntimeError("boom"))
    result = await agent._run_impl("i'm sad", mode="compose")
    assert "刚才没能完整回复你" in result


def test_mcp_explanatory_question_is_not_download_intent():
    """Regression: asking about the MCP protocol must never be routed to
    download_mcp, which would add an npx MCP server to the user's config."""
    text = (
        "请使用网页搜索工具搜索'MCP Model Context Protocol 是什么'，"
        "然后写一份200字左右的《MCP协议简介》保存到当前目录的 mcp_intro.md，"
        "内容包括：什么是MCP、核心概念、适用场景。"
    )
    assert detect_download_intent(text) is None


def test_mcp_explanation_and_file_save_are_not_download_intent():
    assert detect_download_intent("MCP是什么？解释一下Model Context Protocol") is None
    assert detect_download_intent("写一份MCP协议介绍保存到 mcp_intro.md") is None


def test_using_an_installed_skill_tool_is_not_a_skill_download_request():
    text = "Use the installed skill tool exactly once with name=tdd, then summarize its guidance."
    assert detect_download_intent(text) is None


def test_mcp_install_intent_still_detected():
    assert detect_download_intent("安装 mcp server 叫 filesystem") == (
        "mcp",
        "filesystem",
        "",
    )
    assert detect_download_intent("add mcp server named filesystem") == (
        "mcp",
        "filesystem",
        "",
    )
    assert detect_download_intent("请添加一个MCP服务器叫chrome-devtools") == (
        "mcp",
        "chrome-devtools",
        "",
    )
