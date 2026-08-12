"""Luna#3: _redact must cover every path that echoes an error containing the key.

Each error response that could embed a provider error string (which may
repeat the api_key back) must have the key redacted before it reaches the
client. We assert on the wire-shaped dict returned by the route handlers.
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


def _assert_no_key_leak(result: dict, key: str) -> None:
    """Recursively assert the secret never appears in the response payload."""
    import json

    dumped = json.dumps(result, ensure_ascii=False)
    assert key not in dumped, f"API key leaked in response: {dumped[:200]}"


def test_discover_failure_redacts_key(isolated_config, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider error strings sometimes echo the key back; _redact must strip it."""
    secret = "sk-super-secret-discover"

    def _fail(*args, **kwargs):
        return {"success": False, "error": f"401 with key {secret}", "error_code": "auth"}

    monkeypatch.setattr(
        "RxyCode.RxyCode1_1_0.config.model_manager.discover_provider_models", _fail
    )
    result = asyncio.run(
        model_routes.discover({"api_key": secret, "base_url": "https://api.invalid/v1"})
    )
    _assert_no_key_leak(result, secret)
    assert result["error_code"] == "auth"


def test_onboard_probe_failure_redacts_key(isolated_config, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "sk-super-secret-onboard"

    def _probe(*args, **kwargs):
        return {"ok": False, "error": f"bad credential {secret}", "error_code": "probe"}

    monkeypatch.setattr(
        "RxyCode.RxyCode1_1_0.config.model_manager.probe_model_connection", _probe
    )
    result = asyncio.run(
        model_routes.onboard(
            {"provider_model_id": "m", "api_key": secret, "base_url": "https://api.invalid/v1"}
        )
    )
    _assert_no_key_leak(result, secret)


def test_onboard_batch_exception_redacts_key(isolated_config, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "sk-super-secret-batch"

    def _boom(*args, **kwargs):
        raise RuntimeError(f"unexpected {secret} in exception")

    monkeypatch.setattr(
        "RxyCode.RxyCode1_1_0.config.model_manager.onboard_models_batch", _boom
    )
    result = asyncio.run(
        model_routes.onboard_batch(
            {"api_key": secret, "base_url": "https://api.invalid/v1", "model_ids": ["a"]}
        )
    )
    _assert_no_key_leak(result, secret)


def test_upsert_credential_never_returns_key(isolated_config) -> None:
    """credentials/upsert response must not contain the submitted key."""
    secret = "sk-upsert-secret"
    result = model_routes.upsert_credential({"id": "ghost-model", "api_key": secret})
    _assert_no_key_leak(result, secret)
