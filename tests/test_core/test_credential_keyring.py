"""DC4: cross-platform keyring backend tests (macOS Keychain / Linux Secret Service).

The credential store must prefer the OS keychain on POSIX when a desktop
keyring backend is available (keyring lib), and degrade to the 0600
owner-only file when no keyring is available (CI / headless). The public
API (store_credential / load_credential / delete_credential) must behave
identically either way.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


class _FakeKeyring:
    """In-memory keyring stand-in with an opt-in availability switch."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], str] = {}
        self.available = True

    def get_password(self, service: str, username: str) -> str | None:
        if not self.available:
            raise Exception("no keyring backend available")
        return self._values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        if not self.available:
            raise Exception("no keyring backend available")
        self._values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if not self.available:
            raise Exception("no keyring backend available")
        self._values.pop((service, username), None)


@pytest.fixture
def keyring_backend(monkeypatch: pytest.MonkeyPatch):
    """Install a fake keyring module into sys.modules and force POSIX mode."""
    import RxyCode.RxyCode1_1_0.config.credential_store as store

    fake = _FakeKeyring()
    monkeypatch.setitem(sys.modules, "keyring", fake)
    monkeypatch.setattr(store, "_os_name", "posix")  # force the POSIX branch
    monkeypatch.setattr(store, "_keyring_available", lambda: fake.available)
    return fake


@pytest.fixture
def secret_file(tmp_path: Path) -> Path:
    return tmp_path / "credentials.yaml"


def test_store_uses_keyring_when_available(keyring_backend, tmp_path: Path) -> None:
    """On POSIX with a keyring backend, the raw secret must NOT be in the file."""
    from RxyCode.RxyCode1_1_0.config.credential_store import (
        load_credential,
        store_credential,
    )

    secret = "sk-test-secret-live-123"
    ref = store_credential(secret, tmp_path / "config.yaml")

    stored_file = (tmp_path / "credentials.yaml").read_text(encoding="utf-8")
    assert "keyring-v1:" in stored_file
    assert secret not in stored_file

    assert load_credential(ref, tmp_path / "config.yaml") == secret


def test_store_falls_back_to_file_when_keyring_unavailable(
    keyring_backend, tmp_path: Path
) -> None:
    """POSIX without a keyring (CI/headless) degrades to the 0600 file."""
    from RxyCode.RxyCode1_1_0.config.credential_store import (
        load_credential,
        store_credential,
    )

    keyring_backend.available = False
    secret = "sk-test-secret-fallback-456"
    ref = store_credential(secret, tmp_path / "config.yaml")

    stored_file = (tmp_path / "credentials.yaml").read_text(encoding="utf-8")
    assert "file-v1:" in stored_file
    assert load_credential(ref, tmp_path / "config.yaml") == secret


def test_delete_credential_cleans_keyring(
    keyring_backend, tmp_path: Path
) -> None:
    """Deleting a keyring-backed credential removes both the file entry and keyring value."""
    from RxyCode.RxyCode1_1_0.config.credential_store import (
        delete_credential,
        load_credential,
        store_credential,
    )

    secret = "sk-test-secret-delete-me"
    ref = store_credential(secret, tmp_path / "config.yaml")
    assert load_credential(ref, tmp_path / "config.yaml") == secret

    delete_credential(ref, tmp_path / "config.yaml")

    assert keyring_backend.get_password("rxycode.credentials", ref) is None
    with pytest.raises(ValueError, match="unavailable"):
        load_credential(ref, tmp_path / "config.yaml")


def test_posix_file_fallback_keeps_0600_permissions(tmp_path: Path) -> None:
    """The degraded file must stay owner-only readable."""
    import os

    from RxyCode.RxyCode1_1_0.config.credential_store import store_credential

    secret = "sk-test-secret-perm-check"
    store_credential(secret, tmp_path / "config.yaml")

    if os.name != "nt":
        mode = (tmp_path / "credentials.yaml").stat().st_mode & 0o777
        assert mode == 0o600
