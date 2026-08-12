"""Luna#2: models/discover must NEVER persist the credential or any model.

Discovery is a read-only catalogue probe: after the call, the config and
the credential store must be byte-identical to before.
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


@pytest.fixture
def discover_failure(monkeypatch: pytest.MonkeyPatch):
    """Force discover_provider_models to fail like a real bad-credential probe."""

    def _fail(*args, **kwargs):
        return {"success": False, "error": "401 Unauthorized", "error_code": "auth"}

    monkeypatch.setattr(
        "RxyCode.RxyCode1_1_0.config.model_manager.discover_provider_models", _fail
    )
    return None


def _snapshot(tmp_path: Path) -> tuple[dict, bytes | None]:
    cfg_path = tmp_path / "config.yaml"
    secret_path = tmp_path / "credentials.yaml"
    cfg = {}
    if cfg_path.exists():
        import yaml

        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    secret_bytes = secret_path.read_bytes() if secret_path.exists() else None
    return cfg, secret_bytes


def test_discover_does_not_persist_on_failure(
    isolated_config, discover_failure, tmp_path: Path
) -> None:
    """A failed probe (e.g. bad key) must not create config or credential entries."""
    before = _snapshot(tmp_path)

    result = asyncio.run(
        model_routes.discover({"api_key": "sk-should-not-persist", "base_url": "https://api.invalid/v1"})
    )

    assert result["ok"] is False
    assert result["error_code"] == "auth"
    assert "sk-should-not-persist" not in str(result)
    assert _snapshot(tmp_path) == before


def test_discover_does_not_persist_on_success(
    isolated_config, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Even a successful catalogue probe must not write the credential anywhere."""
    from RxyCode.RxyCode1_1_0.config import settings
    from RxyCode.RxyCode1_1_0.config.credential_store import store_credential

    # Record any credential-store writes the discovery might attempt.
    writes: list[str] = []

    def _spy_store(value: str, config_path: Path) -> str:
        writes.append(value)
        return store_credential(value, config_path)

    monkeypatch.setattr(
        "RxyCode.RxyCode1_1_0.config.model_manager.store_credential", _spy_store
    )

    def _success(*args, **kwargs):
        return {
            "success": True,
            "models": [{"id": "probe-model", "object": "model"}],
            "elapsed": 0.1,
        }

    monkeypatch.setattr(
        "RxyCode.RxyCode1_1_0.config.model_manager.discover_provider_models", _success
    )

    before = _snapshot(tmp_path)
    result = asyncio.run(
        model_routes.discover({"api_key": "sk-probe-ok", "base_url": "https://api.invalid/v1"})
    )

    assert result["ok"] is True
    assert writes == [], "discover must not write any credential"
    assert _snapshot(tmp_path) == before
    assert "sk-probe-ok" not in str(result)
