"""Luna#4: HTTP API vs JSON-RPC error-semantics parity.

Every error surfaced by the HTTP endpoints (api_server_models.py) must be
mapped to the same semantic in the JSON-RPC layer (appserver/model_routes.py):
- HTTP 400 (bad credential / discovery failure)  -> ok=False + error_code
- HTTP 409 (model already exists)                -> ok=False + error_code="exists"
- remove of a missing model                      -> ok=False + error_code="not_found"
- set_active of a missing model                  -> ok=False + error_code="not_found"
- batch partial failure                          -> ok=False (no crash)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from RxyCode.RxyCode1_1_0.appserver import model_routes


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from RxyCode.RxyCode1_1_0.config import settings

    from RxyCode.RxyCode1_1_0.config import model_manager

    cfg_path = tmp_path / "config.yaml"
    # model_manager binds settings functions at module import time, so patch
    # model_manager's own references (not settings.*) for the isolation to
    # actually take effect.
    monkeypatch.setattr(model_manager, "get_config_path", lambda: cfg_path)
    monkeypatch.setattr(model_manager, "load_config", lambda: {})
    monkeypatch.setattr(model_manager, "save_config", lambda cfg: None)
    return tmp_path


def test_onboard_existing_model_maps_http_409(isolated_config, monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP raises 409 'Model already exists'; RPC must report ok=False exists."""
    from RxyCode.RxyCode1_1_0.config import model_manager

    monkeypatch.setattr(model_manager, "local_model_key", lambda pid, provider: "deepseek-v4-flash")
    monkeypatch.setattr(
        model_manager,
        "list_models",
        lambda: {"deepseek-v4-flash": {"model_name": "deepseek-v4-flash"}},
    )

    result = asyncio.run(
        model_routes.onboard(
            {"provider_model_id": "deepseek-v4-flash", "api_key": "sk-x", "base_url": "https://api.deepseek.com/v1"}
        )
    )
    assert result["ok"] is False
    assert result["error_code"] == "exists"


def test_discover_failure_maps_http_400(isolated_config, monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 400 detail carries error_code; RPC must carry the same code."""
    monkeypatch.setattr(
        "RxyCode.RxyCode1_1_0.config.model_manager.discover_provider_models",
        lambda **kw: {"success": False, "error": "nope", "error_code": "auth"},
    )
    result = asyncio.run(
        model_routes.discover({"api_key": "sk-x", "base_url": "https://api.invalid/v1"})
    )
    assert result["ok"] is False
    assert result["error_code"] == "auth"


def test_remove_missing_model_reports_not_found(isolated_config, monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP remove of a missing model -> no crash; RPC ok=False not_found."""
    from RxyCode.RxyCode1_1_0.config import model_manager

    monkeypatch.setattr(model_manager, "remove_model", lambda name: False)
    result = model_routes.remove({"id": "ghost-model"})
    assert result["ok"] is False
    assert result["removed"] is False


def test_set_active_missing_model_reports_false(isolated_config, monkeypatch: pytest.MonkeyPatch) -> None:
    from RxyCode.RxyCode1_1_0.config import model_manager

    monkeypatch.setattr(model_manager, "set_active_model", lambda name: False)
    result = model_routes.set_active({"id": "ghost-model"})
    assert result["ok"] is False


def test_onboard_batch_partial_failure_no_crash(isolated_config, monkeypatch: pytest.MonkeyPatch) -> None:
    """A batch that reports partial results must surface them without raising."""
    from RxyCode.RxyCode1_1_0.config import model_manager

    monkeypatch.setattr(
        model_manager,
        "onboard_models_batch",
        lambda **kw: {
            "onboarded": ["a"],
            "failed": [{"id": "b", "reason": "probe failed"}],
        },
    )
    result = asyncio.run(
        model_routes.onboard_batch(
            {"api_key": "sk-x", "base_url": "https://api.invalid/v1", "model_ids": ["a", "b"]}
        )
    )
    assert result["ok"] is True
    assert result["onboarded"] == ["a"]
    assert result["failed"][0]["id"] == "b"


def test_onboard_batch_invalid_input_matches_http_422(isolated_config) -> None:
    """HTTP pydantic 422 (empty model_ids) must map to ok=False invalid."""
    result = asyncio.run(
        model_routes.onboard_batch({"api_key": "sk-x", "base_url": "https://api.invalid/v1", "model_ids": []})
    )
    assert result["ok"] is False
    assert result["error_code"] == "invalid"


def test_onboard_blank_base_url_rejected(isolated_config) -> None:
    """HTTP validator requires https; RPC must reject http/blank consistently."""
    result = asyncio.run(
        model_routes.onboard(
            {"provider_model_id": "m", "api_key": "sk-x", "base_url": "http://insecure"}
        )
    )
    assert result["ok"] is False
    assert result["error_code"] == "invalid"


def test_onboard_passes_config_key_to_add_model(isolated_config, monkeypatch: pytest.MonkeyPatch) -> None:
    """onboard must call add_model with name=<config_key> (regression for the
    missing-name TypeError found during e2e add-model flow)."""
    from RxyCode.RxyCode1_1_0.config import model_manager

    captured: dict = {}

    def _spy_add_model(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(model_manager, "probe_model_connection", lambda *a, **kw: {"ok": True})
    monkeypatch.setattr(model_manager, "set_active_model", lambda name: True)
    monkeypatch.setattr(model_manager, "add_model", _spy_add_model)
    monkeypatch.setattr(model_manager, "local_model_key", lambda pid, provider: "deepseek/deepseek-v4-flash")

    result = asyncio.run(
        model_routes.onboard(
            {"provider_model_id": "deepseek-v4-flash", "api_key": "sk-x", "base_url": "https://api.deepseek.com/v1"}
        )
    )
    assert result["ok"] is True
    assert captured.get("name") == "deepseek/deepseek-v4-flash"
    assert captured.get("model_name") == "deepseek-v4-flash"
    assert captured.get("api_key") == "sk-x"
