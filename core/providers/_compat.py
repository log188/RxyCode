"""Compatibility imports for source-tree and installed-package layouts.

The project is exercised both as ``core.*`` from the repository root and as
``RxyCode.RxyCode1_1_0.*`` from the built package.  Keeping these lookups in a
single top-level helper avoids repeating function-scoped try/except imports in
every provider and preserves the P7 lazy-import budget.
"""

from __future__ import annotations

from importlib import import_module


def _load(module_suffix: str):
    last_error: ImportError | None = None
    for prefix in ("RxyCode.RxyCode1_1_0.", ""):
        try:
            return import_module(prefix + module_suffix)
        except ImportError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ImportError(module_suffix)


_capabilities = _load("config.model_capabilities")
_transport = _load("config.model_transport")
_endpoint = _load("config.model_endpoint")

DEFAULT_CAPABILITIES = _capabilities.DEFAULT_CAPABILITIES
ModelCapabilities = _capabilities.ModelCapabilities
ModelPricing = _capabilities.ModelPricing
UsageFieldMap = _capabilities.UsageFieldMap

ANTHROPIC_MESSAGES_TRANSPORT = _transport.ANTHROPIC_MESSAGES_TRANSPORT
LLMTransport = _transport.LLMTransport
OPENAI_CHAT_TRANSPORT = _transport.OPENAI_CHAT_TRANSPORT
OPENAI_RESPONSES_TRANSPORT = _transport.OPENAI_RESPONSES_TRANSPORT
normalize_api_transport = _transport.normalize_api_transport
normalize_transport_candidates = _transport.normalize_transport_candidates

llm_client_base_url = _endpoint.llm_client_base_url
normalize_llm_endpoint = _endpoint.normalize_llm_endpoint
