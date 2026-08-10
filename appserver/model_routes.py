"""JSON-RPC routes for model / credential management (Phase 4 D5 unblock).

Exposes the same capabilities as the HTTP API (``api_server_models.py``)
as JSON-RPC methods so the Desktop shell (DC1: protocol-client only) can
manage models and API keys without calling HTTP.

Frozen entry names:
  - ``models/list``            — structured model list (provider grouping, Phase 3 limit summary)
  - ``models/presets``         — provider presets (base URL only, no model ids)
  - ``models/discover``        — probe a provider catalogue with a credential (never persists)
  - ``models/onboard``         — probe + persist a single working model (credential via DPAPI)
  - ``models/onboard_batch``   — probe + persist multiple models with one credential
  - ``models/remove``          — remove a model by config key
  - ``models/set_active``      — switch the active model
  - ``models/test_connection`` — live credential test for an existing model
  - ``credentials/upsert``     — store/refresh a model's API key (DPAPI encrypted, never echoed)
  - ``credentials/delete``     — remove a stored credential

All routes delegate to ``config.model_manager`` / ``config.credential_store``;
this module is a thin transport adapter and never reimplements business logic.
"""

from __future__ import annotations

import asyncio
from typing import Any


def _run(coro):
    """Run a synchronous model_manager call off the event loop."""
    return asyncio.to_thread(coro)


def _redact(value: object, *secrets: str) -> str:
    from ..api_server import _redact_sensitive

    result = str(value)
    for secret_value in secrets:
        if secret_value:
            result = result.replace(secret_value, "[REDACTED]")
    return str(_redact_sensitive(result))


def list_models() -> dict[str, Any]:
    """models/list — structured model list with provider grouping + limit summary."""
    from ..config.settings import load_config
    from ..config.model_manager import (
        ensure_models_provider_metadata,
        infer_provider_group,
        prune_recent_models,
    )

    cfg = ensure_models_provider_metadata(load_config(), persist=False)
    models = cfg.get("models", {})
    active = cfg.get("active_model", "")
    model_limits_cfg = cfg.get("model_limits") or {}
    result = []
    for name, mcfg in models.items():
        vendor_id = mcfg.get("model_name", name)
        display = mcfg.get("nickname") or vendor_id
        inferred = infer_provider_group(mcfg.get("base_url", ""))
        provider_name = (
            inferred.get("name")
            or mcfg.get("provider_name")
            or mcfg.get("category")
            or "其他"
        )
        provider_id = inferred.get("id") or mcfg.get("provider_id") or ""
        item: dict[str, Any] = {
            "id": name,
            "name": vendor_id,
            "nickname": display,
            "provider_model_id": vendor_id,
            "base_url": mcfg.get("base_url", ""),
            "active": name == active,
            "category": provider_name or "其他",
            "provider_name": provider_name or "",
            "provider_id": provider_id or "",
        }
        try:
            from ..config.model_limits import resolve_configured_max_tokens

            resolution = resolve_configured_max_tokens(
                model_config=mcfg,
                capability_max_output_tokens=None,
                configured_max_tokens=mcfg.get("max_tokens"),
                model_limits_config=model_limits_cfg,
                input_tokens=None,
            )
            item["max_tokens_mode"] = (
                "auto" if mcfg.get("max_tokens") in (None, "auto") else "explicit"
            )
            item["resolved_max_tokens"] = resolution.resolved_max_tokens
            item["limit_source"] = resolution.source
            item["context_window"] = resolution.context_window
            item["warning"] = "; ".join(resolution.warnings) or None
        except Exception:
            item["max_tokens_mode"] = "auto"
            item["resolved_max_tokens"] = None
            item["limit_source"] = "legacy_server"
            item["context_window"] = None
            item["warning"] = None
        result.append(item)
    return {"models": result, "active": active, "recent": prune_recent_models(cfg)}


def list_presets() -> dict[str, Any]:
    """models/presets — provider connection presets (base URL only)."""
    from ..config.model_manager import list_provider_presets

    return {"presets": list_provider_presets()}


async def discover(params: dict[str, Any]) -> dict[str, Any]:
    """models/discover — probe a provider catalogue; never persists.

    params: {api_key, base_url}
    """
    from ..config.model_manager import discover_provider_models

    api_key = str(params.get("api_key", "")).strip()
    base_url = str(params.get("base_url", "")).strip()
    result = await asyncio.to_thread(
        discover_provider_models, api_key=api_key, base_url=base_url
    )
    if not result.get("success"):
        safe_error = _redact(result.get("error", "Discovery failed"), api_key)
        return {
            "ok": False,
            "error_code": result.get("error_code") or "transport",
            "message": f"Model discovery failed: {safe_error}",
        }
    return {
        "ok": True,
        "models": result.get("models", []),
        "base_url": base_url,
        "probe": {"elapsed": result.get("elapsed")},
    }


async def onboard(params: dict[str, Any]) -> dict[str, Any]:
    """models/onboard — probe credentials and persist a working model mapping.

    params: {provider_model_id, api_key, base_url, nickname?}
    """
    from ..config.model_manager import (
        add_model,
        list_models,
        local_model_key,
        probe_model_connection,
        resolve_provider_meta,
        set_active_model,
    )

    provider_model_id = str(params.get("provider_model_id", "")).strip()
    api_key = str(params.get("api_key", "")).strip()
    base_url = str(params.get("base_url", "")).strip()
    nickname = str(params.get("nickname") or "").strip() or None

    if not provider_model_id:
        return {"ok": False, "error_code": "invalid", "message": "provider_model_id must not be empty"}
    if not api_key:
        return {"ok": False, "error_code": "invalid", "message": "api_key must not be empty"}
    if not base_url:
        return {"ok": False, "error_code": "invalid", "message": "base_url must not be empty"}

    from ..config.model_manager import normalize_provider_base_url

    try:
        base_url = normalize_provider_base_url(base_url, require_https=True)
    except Exception as exc:
        return {"ok": False, "error_code": "invalid", "message": f"Invalid base_url: {exc}"}

    meta = resolve_provider_meta(base_url)
    config_key = local_model_key(provider_model_id, meta["id"])
    if config_key in list_models():
        return {"ok": False, "error_code": "exists", "message": f"Model already exists: {config_key}"}

    probe = await asyncio.to_thread(probe_model_connection, api_key, base_url, provider_model_id)
    if not probe.get("ok"):
        safe_error = _redact(probe.get("error", "probe failed"), api_key)
        return {"ok": False, "error_code": probe.get("error_code") or "probe", "message": safe_error}

    await asyncio.to_thread(
        add_model,
        api_key=api_key,
        base_url=base_url,
        model_name=provider_model_id,
        nickname=nickname,
    )
    await asyncio.to_thread(set_active_model, config_key)
    return {"ok": True, "id": config_key, "probe": {"elapsed": probe.get("elapsed")}}


async def onboard_batch(params: dict[str, Any]) -> dict[str, Any]:
    """models/onboard_batch — probe + persist multiple models with one credential.

    params: {api_key, base_url, model_ids: [..], provider_id?, provider_name?,
             active_model_id?, skip_probe?}
    """
    from ..config.model_manager import normalize_provider_base_url, onboard_models_batch

    api_key = str(params.get("api_key", "")).strip()
    base_url = str(params.get("base_url", "")).strip()
    model_ids = [str(x).strip() for x in params.get("model_ids") or [] if str(x).strip()]
    provider_id = params.get("provider_id") or None
    provider_name = params.get("provider_name") or None
    active_model_id = params.get("active_model_id") or None
    skip_probe = bool(params.get("skip_probe", True))

    if not api_key:
        return {"ok": False, "error_code": "invalid", "message": "api_key must not be empty"}
    if not base_url:
        return {"ok": False, "error_code": "invalid", "message": "base_url must not be empty"}
    if not model_ids:
        return {"ok": False, "error_code": "invalid", "message": "model_ids must not be empty"}

    try:
        base_url = normalize_provider_base_url(base_url, require_https=True)
    except Exception as exc:
        return {"ok": False, "error_code": "invalid", "message": f"Invalid base_url: {exc}"}

    try:
        result = await asyncio.to_thread(
            onboard_models_batch,
            api_key=api_key,
            base_url=base_url,
            model_ids=model_ids,
            provider_id=provider_id,
            provider_name=provider_name,
            active_model_id=active_model_id,
            skip_probe=skip_probe,
        )
    except Exception as exc:
        return {"ok": False, "error_code": "onboard", "message": _redact(str(exc), api_key)}
    return {"ok": True, **result}


def remove(params: dict[str, Any]) -> dict[str, Any]:
    """models/remove — remove a model by config key. params: {id}"""
    from ..config.model_manager import remove_model

    model_id = str(params.get("id", "")).strip()
    if not model_id:
        return {"ok": False, "error_code": "invalid", "message": "id must not be empty"}
    removed = remove_model(model_id)
    return {"ok": bool(removed), "removed": removed}


def set_active(params: dict[str, Any]) -> dict[str, Any]:
    """models/set_active — switch the active model. params: {id}"""
    from ..config.model_manager import set_active_model

    model_id = str(params.get("id", "")).strip()
    if not model_id:
        return {"ok": False, "error_code": "invalid", "message": "id must not be empty"}
    ok = set_active_model(model_id)
    return {"ok": ok, "id": model_id}


async def test_connection(params: dict[str, Any]) -> dict[str, Any]:
    """models/test_connection — live credential test. params: {id}"""
    from ..config.model_manager import test_model_connection

    model_id = str(params.get("id", "")).strip()
    if not model_id:
        return {"ok": False, "error_code": "invalid", "message": "id must not be empty"}
    result = await asyncio.to_thread(test_model_connection, model_id)
    return {
        "ok": bool(result.get("ok")),
        "message": result.get("message") or result.get("error") or "",
        "elapsed": result.get("elapsed"),
    }


def upsert_credential(params: dict[str, Any]) -> dict[str, Any]:
    """credentials/upsert — store/refresh a model API key (DPAPI, never echoed).

    Delegates to ``model_manager.add_model`` with the existing model's
    config key so the credential flows through ``_credential_config``
    (env-ref aware, DPAPI-encrypted ``api_key_secret``). The key is never
    returned; only a reference exists inside the backend config.

    params: {id, api_key}
    """
    from ..config.model_manager import (
        add_model,
        load_config,
        normalize_provider_base_url,
    )

    model_id = str(params.get("id", "")).strip()
    api_key = str(params.get("api_key", "")).strip()
    if not model_id:
        return {"ok": False, "error_code": "invalid", "message": "id must not be empty"}
    if not api_key:
        return {"ok": False, "error_code": "invalid", "message": "api_key must not be empty"}

    cfg = load_config()
    existing = (cfg.get("models") or {}).get(model_id)
    if not isinstance(existing, dict):
        return {
            "ok": False,
            "error_code": "not_found",
            "message": f"No model with id '{model_id}'",
        }

    try:
        add_model(
            name=model_id,
            api_key=api_key,
            base_url=normalize_provider_base_url(
                str(existing.get("base_url", "")), require_https=False
            ),
            model_name=existing.get("model_name") or model_id,
            nickname=existing.get("nickname"),
        )
    except Exception as exc:
        return {"ok": False, "error_code": "credential", "message": str(exc)}
    return {"ok": True, "id": model_id}


def delete_credential(params: dict[str, Any]) -> dict[str, Any]:
    """credentials/delete — clear a model's API key reference (DPAPI blob removed).

    params: {id}
    """
    from ..config.credential_store import delete_credential as _delete_secret
    from ..config.model_manager import load_config, save_config
    from ..config.settings import get_config_path

    model_id = str(params.get("id", "")).strip()
    if not model_id:
        return {"ok": False, "error_code": "invalid", "message": "id must not be empty"}

    cfg = load_config()
    entry = (cfg.get("models") or {}).get(model_id)
    if not isinstance(entry, dict):
        return {"ok": False, "error_code": "not_found", "message": f"No model with id '{model_id}'"}

    reference = entry.get("api_key_secret")
    if reference:
        _delete_secret(reference, get_config_path())
    entry.pop("api_key_secret", None)
    entry.pop("api_key_env", None)
    save_config(cfg)
    return {"ok": True, "id": model_id}
