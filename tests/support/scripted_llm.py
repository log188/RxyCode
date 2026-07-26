"""Deterministic chat model backed by recorded response messages."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.tools import BaseTool


class ScriptedChatModel(GenericFakeChatModel):
    """Use LangChain's fake chat model while preserving the tool-binding API."""

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> "ScriptedChatModel":
        return self

