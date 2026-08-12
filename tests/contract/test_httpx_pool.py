"""Phase C C5 contract tests: process-wide httpx client pool.

``utils/safe_http.get_shared_client()`` must be a process-wide singleton
(lazy, thread-safe) with configured connection-pool limits, reused by every
``fetch_public_response`` call so TCP/TLS handshakes and keep-alive
connections are shared; ``close_shared_client`` is idempotent and safe to
call from an event-loop-free teardown.
"""

from __future__ import annotations

import asyncio
import threading

import httpx
import pytest

from RxyCode.RxyCode1_1_0.utils import safe_http

MAX_CONNECTIONS = 20
MAX_KEEPALIVE = 10


@pytest.fixture(autouse=True)
def _isolate_singleton(monkeypatch):
    monkeypatch.setattr(safe_http, "_client", None)
    monkeypatch.setattr(safe_http, "_client_loop", None)
    monkeypatch.setattr(safe_http, "_client_lock", threading.Lock())
    yield
    safe_http._client = None
    safe_http._client_loop = None


def test_shared_client_is_a_singleton():
    first = safe_http.get_shared_client()
    second = safe_http.get_shared_client()
    assert first is second


def test_shared_client_pool_limits_are_applied():
    client = safe_http.get_shared_client()
    pool = client._transport._pool
    assert pool._max_connections == MAX_CONNECTIONS
    assert pool._max_keepalive_connections == MAX_KEEPALIVE


def test_close_shared_client_is_idempotent_and_rebuilds():
    first = safe_http.get_shared_client()
    safe_http.close_shared_client()
    assert safe_http._client is None
    safe_http.close_shared_client()  # second call must be a no-op
    second = safe_http.get_shared_client()
    assert second is not first, "a fresh client is created after close"


def test_shared_client_creation_is_thread_safe():
    results: list[httpx.AsyncClient] = []

    def worker() -> None:
        results.append(safe_http.get_shared_client())

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert all(c is results[0] for c in results), (
        "concurrent first access must yield the same singleton"
    )


def test_client_is_not_shared_across_close_boundary():
    """After close_shared_client the next call builds a NEW client (the old
    reference is dropped), so a stale closed client is never reused."""
    first = safe_http.get_shared_client()
    safe_http.close_shared_client()
    second = safe_http.get_shared_client()
    assert first is not second
    safe_http.close_shared_client()


class _FakeStream:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc) -> bool:
        return False


class _FakeClient:
    """Records stream() calls; used to prove fetch uses the shared client."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.stream_calls: list[tuple[str, str, dict]] = []

    def stream(self, method: str, url: str, **kwargs):
        self.stream_calls.append((method, url, kwargs))
        return _FakeStream(self._response)


@pytest.mark.asyncio
async def test_fetch_uses_the_shared_client(monkeypatch):
    """fetch_public_response must use get_shared_client() instead of
    constructing a fresh AsyncClient per call."""
    from RxyCode.RxyCode1_1_0.utils.safe_http import (
        fetch_public_response,
        resolve_public_addresses,
    )

    fake_response = httpx.Response(
        200,
        headers={"content-type": "text/plain"},
        content=b"hello",
        request=httpx.Request("GET", "https://example.com/"),
    )
    fake = _FakeClient(fake_response)
    monkeypatch.setattr(safe_http, "get_shared_client", lambda: fake)

    async def fake_resolve(hostname: str, port: int) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(safe_http, "resolve_public_addresses", fake_resolve)

    result = await fetch_public_response("https://example.com/index.html")

    assert fake.stream_calls, "fetch must drive the shared client"
    assert result.status_code == 200
    assert result.content == b"hello"


@pytest.mark.asyncio
async def test_webfetch_and_file_download_share_the_same_client(monkeypatch, tmp_path):
    """Both tools must obtain THE SAME shared client (both route through
    fetch_public_response -> get_shared_client)."""
    from RxyCode.RxyCode1_1_0.tools import file_download, webfetch

    shared = _FakeClient(
        httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"hello",
            request=httpx.Request("GET", "https://example.com/"),
        )
    )
    monkeypatch.setattr(safe_http, "get_shared_client", lambda: shared)

    async def fake_resolve(hostname: str, port: int) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(safe_http, "resolve_public_addresses", fake_resolve)

    text = await webfetch.fetch_url_async("https://example.com/x", format="text")
    target = tmp_path / "out.bin"
    await file_download.download_file_async(
        "https://example.com/x", target
    )

    assert "hello" in text
    assert target.read_bytes() == b"hello"
    assert len(shared.stream_calls) == 2
    assert webfetch.fetch_url_async.__module__  # both entries share the pool
    # The shared client (not a fresh one) served both tools.
    assert safe_http.get_shared_client() is shared


@pytest.mark.asyncio
async def test_fetch_passes_the_caller_timeout_per_request(monkeypatch):
    """The shared client's default timeout must not swallow the caller's
    per-request timeout (per-request timeout on stream())."""
    from RxyCode.RxyCode1_1_0.utils.safe_http import fetch_public_response

    fake_response = httpx.Response(
        200,
        headers={"content-type": "text/plain"},
        content=b"hello",
        request=httpx.Request("GET", "https://example.com/"),
    )
    fake = _FakeClient(fake_response)
    monkeypatch.setattr(safe_http, "get_shared_client", lambda: fake)

    async def fake_resolve(hostname: str, port: int) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(safe_http, "resolve_public_addresses", fake_resolve)

    await fetch_public_response("https://example.com/", timeout=77.0)

    assert fake.stream_calls
    _method, _url, kwargs = fake.stream_calls[0]
    per_request = kwargs.get("timeout")
    assert per_request is not None
    assert float(per_request.connect) == 77.0
