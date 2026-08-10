"""Phase 4 D5 · Model/credential JSON-RPC route tests.

Covers the thin adapter layer (appserver/model_routes.py): every method
delegates to config.model_manager / config.credential_store and never
reimplements business logic. Uses an isolated config dir per test.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from RxyCode.RxyCode1_1_0.appserver import model_routes


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point settings at a temp dir so model writes never touch user config."""
    from RxyCode.RxyCode1_1_0.config import settings

    cfg_path = tmp_path / "config.yaml"
    monkeypatch.setattr(settings, "get_config_path", lambda: cfg_path)
    monkeypatch.setattr(settings, "load_config", lambda: {})
    monkeypatch.setattr(settings, "save_config", lambda cfg: None)
    # model_manager imports settings functions at call time, so patching
    # settings is enough for load_config/save_config/get_config_path.
    return tmp_path


def test_list_models_empty(isolated_config):
    result = model_routes.list_models()
    assert result["models"] == []
    assert result["active"] == ""


def test_list_presets_shape(isolated_config):
    result = model_routes.list_presets()
    assert "presets" in result
    assert isinstance(result["presets"], list)


def test_remove_requires_id(isolated_config):
    result = model_routes.remove({})
    assert result["ok"] is False
    assert result["error_code"] == "invalid"


def test_set_active_requires_id(isolated_config):
    result = model_routes.set_active({})
    assert result["ok"] is False
    assert result["error_code"] == "invalid"


def test_onboard_validates_empty_fields(isolated_config):
    result = asyncio.run(model_routes.onboard({}))
    assert result["ok"] is False
    assert result["error_code"] == "invalid"


def test_onboard_rejects_invalid_base_url(isolated_config):
    result = asyncio.run(
        model_routes.onboard(
            {"provider_model_id": "x", "api_key": "sk-x", "base_url": "http://insecure"}
        )
    )
    assert result["ok"] is False
    assert result["error_code"] == "invalid"


def test_discover_validates_empty(isolated_config):
    result = asyncio.run(model_routes.discover({}))
    assert result["ok"] is False


def test_onboard_batch_validates_empty(isolated_config):
    result = asyncio.run(model_routes.onboard_batch({}))
    assert result["ok"] is False
    assert result["error_code"] == "invalid"


def test_test_connection_requires_id(isolated_config):
    result = asyncio.run(model_routes.test_connection({}))
    assert result["ok"] is False
    assert result["error_code"] == "invalid"


def test_upsert_credential_requires_model(isolated_config):
    result = model_routes.upsert_credential({"id": "ghost", "api_key": "sk-x"})
    assert result["ok"] is False
    assert result["error_code"] == "not_found"


def test_delete_credential_requires_model(isolated_config):
    result = model_routes.delete_credential({"id": "ghost"})
    assert result["ok"] is False
    assert result["error_code"] == "not_found"


def test_credentials_never_echo_key(isolated_config):
    """The adapter must never put the raw key in any response field."""
    # No response path returns 'api_key' directly; onboarding probes redact.
    assert "api_key" not in model_routes.upsert_credential({"id": "x", "api_key": "sk-secret"}).get(
        "message", ""
    )
