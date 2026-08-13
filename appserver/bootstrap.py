"""Agent bootstrap for appserver (mirrors api_server._init_agent without HTTP)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any


def bootstrap_agent(
    *, stub: bool = False, workspace_root: Path | str | None = None
) -> Any:
    """Initialize AgentV2 (or stub) for stdio appserver."""
    import logging

    log = logging.getLogger(__name__)
    delay_raw = os.environ.get("RXYCODE_APPSERVER_BOOTSTRAP_DELAY")
    if delay_raw:
        time.sleep(float(delay_raw))
    if stub:
        from .stub import StubAgent

        log.info("bootstrap_agent: using StubAgent")
        return StubAgent()

    if workspace_root is not None:
        root = Path(workspace_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        os.chdir(root)
        log.info("bootstrap_agent: workspace_root=%s", root)
    else:
        project_root = Path(__file__).resolve().parents[1]
        os.chdir(project_root)

    try:
        from ..config.settings import load_config
        from ..utils.i18n import i18n
    except ImportError:
        from config.settings import load_config
        from utils.i18n import i18n

    log.info("bootstrap_agent: loading config")
    cfg = load_config()
    i18n.set_lang(cfg.get("language", "zh"))

    # 2026-08-13: 预导入 langchain_openai（含 torch 传递链，实测 ~6.5s）——
    # AgentV2 已改懒导入（首次 _build_llm_from_config 才触发），这里在
    # bootstrap 阶段一次性预加载：运行时/切换模型的首次 LLM 构造不再卡 6.5s
    # （切换模型走 worker.switch_model 复用进程，秒级完成）。
    try:
        import langchain_openai  # noqa: F401 - 预导入消除运行时首次构造延迟
    except Exception as exc:  # pragma: no cover - 预导入失败不阻断 bootstrap
        log.warning("bootstrap_agent: langchain_openai preimport failed: %s", exc)

    try:
        from ..core.agent_v2 import AgentV2 as Agent
    except ImportError:
        from core.agent_v2 import AgentV2 as Agent

    log.info("bootstrap_agent: constructing AgentV2")
    agent = Agent()
    log.info("bootstrap_agent: AgentV2 ready")
    return agent
