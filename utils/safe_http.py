"""Pinned public HTTP(S) client shared by fetch and download tools."""

from __future__ import annotations

import asyncio
import atexit
import ipaddress
import socket
import threading
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx


REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 5
DEFAULT_USER_AGENT = "RxyCode-SafeHTTP/1.1"

#: Connection-pool limits for the process-wide client (C5).  The agent's
#: fetch/download tools are low-frequency, but a shared pool avoids
#: re-doing TCP+TLS handshakes and keeps keep-alive connections warm.
_POOL_LIMITS = httpx.Limits(
    max_connections=20,
    max_keepalive_connections=10,
    keepalive_expiry=30.0,
)

_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None
_client_lock = threading.Lock()


def get_shared_client() -> httpx.AsyncClient:
    """Return the process-wide AsyncClient singleton (lazy, thread-safe, C5).

    Every fetch/download call shares this client so connection pooling and
    keep-alive are effective.  httpx transports are event-loop bound, so the
    singleton is keyed by the running loop: production keeps one loop (one
    pool, as intended); tests/embedders that switch loops get a fresh client
    for the new loop and the previous one is dropped (its loop is gone).
    Never closed by ``async with`` on the caller side; shut down explicitly
    via :func:`close_shared_client` (registered with atexit).
    """
    global _client, _client_loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    with _client_lock:
        if _client is None or _client_loop is not loop:
            _client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=False,
                trust_env=False,
                limits=_POOL_LIMITS,
            )
            _client_loop = loop
        return _client


def close_shared_client() -> None:
    """Close the singleton and drop the reference (idempotent, C5).

    Registered with atexit so the process exits without leaking sockets.
    When called from an event-loop-free context the async close is driven
    with a private loop; when called from a running loop (tests/embedders)
    the close is scheduled on that loop as a task, so the client is still
    closed (the scheduling loop must run to completion for the task to
    execute; if the loop shuts down first, the process/embedder teardown
    owns the remaining cleanup).
    """
    global _client, _client_loop
    with _client_lock:
        client, _client = _client, None
        _client_loop = None
    if client is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        try:
            asyncio.run(client.aclose())
        except Exception:
            pass
    else:
        loop.create_task(client.aclose())


atexit.register(close_shared_client)


class UnsafeUrlError(ValueError):
    """Raised before a request can target a non-public destination."""


class ResponseTooLargeError(ValueError):
    """Raised once the configured response-size boundary is exceeded."""


def is_public_address(
    value: str | ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def validate_public_url(url: str) -> tuple[str, str, int, str]:
    """Normalize a target and reject non-web, credentialed, or local URLs."""
    candidate = str(url or "").strip()
    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise UnsafeUrlError("invalid URL") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UnsafeUrlError("only http and https URLs are allowed")
    if not parsed.hostname:
        raise UnsafeUrlError("URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("URL credentials are not allowed")

    try:
        hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        port = parsed.port or (443 if scheme == "https" else 80)
    except (UnicodeError, ValueError) as exc:
        raise UnsafeUrlError("invalid hostname or port") from exc

    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        raise UnsafeUrlError("local destinations are not allowed")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        if "." not in hostname:
            raise UnsafeUrlError("single-label hostnames are not allowed") from None
    else:
        if not literal.is_global:
            raise UnsafeUrlError(
                "private or non-routable destinations are not allowed"
            )

    host_for_url = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if scheme == "https" else 80
    netloc = host_for_url if port == default_port else f"{host_for_url}:{port}"
    normalized = urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))
    return normalized, hostname, port, scheme


async def resolve_public_addresses(hostname: str, port: int) -> list[str]:
    """Resolve once and reject the whole answer set if any address is private."""
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
        addresses = list(dict.fromkeys(record[4][0] for record in records))
    else:
        addresses = [str(literal)]

    if not addresses:
        raise UnsafeUrlError("hostname did not resolve")
    if any(not is_public_address(address) for address in addresses):
        raise UnsafeUrlError(
            "hostname resolves to a private or non-routable address"
        )
    return addresses


def _pinned_url(url: str, address: str, port: int) -> tuple[str, str]:
    parsed = urlsplit(url)
    ip_host = f"[{address}]" if ":" in address else address
    default_port = 443 if parsed.scheme == "https" else 80
    pinned_netloc = ip_host if port == default_port else f"{ip_host}:{port}"

    original_host = parsed.hostname or ""
    host_header = f"[{original_host}]" if ":" in original_host else original_host
    if port != default_port:
        host_header = f"{host_header}:{port}"
    return (
        urlunsplit((parsed.scheme, pinned_netloc, parsed.path, parsed.query, "")),
        host_header,
    )


def _connected_address(response: httpx.Response) -> str | None:
    stream = response.extensions.get("network_stream")
    if stream is None or not hasattr(stream, "get_extra_info"):
        return None
    server = stream.get_extra_info("server_addr")
    if isinstance(server, (tuple, list)) and server:
        return str(server[0])
    return None


async def _read_limited(response: httpx.Response, max_bytes: int) -> bytes:
    length = response.headers.get("content-length")
    if length:
        try:
            declared_length = int(length)
        except ValueError as exc:
            raise ResponseTooLargeError("invalid Content-Length header") from exc
        if declared_length < 0:
            raise ResponseTooLargeError("invalid Content-Length header")
        if declared_length > max_bytes:
            raise ResponseTooLargeError(
                f"response exceeds {max_bytes} byte limit"
            )

    content = bytearray()
    async for chunk in response.aiter_bytes():
        if len(content) + len(chunk) > max_bytes:
            raise ResponseTooLargeError(f"response exceeds {max_bytes} byte limit")
        content.extend(chunk)
    return bytes(content)


async def fetch_public_response(
    url: str,
    *,
    timeout: float = 30,
    max_bytes: int = 1_000_000,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Fetch bytes from a public target with validation on every redirect hop."""
    timeout = max(0.1, min(float(timeout), 120.0))
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    request_headers = {"User-Agent": DEFAULT_USER_AGENT, **(headers or {})}
    current_url = str(url or "")

    # C5: one process-wide pooled client, never a fresh client per request.
    # The caller owns the client; ``stream()``'s async-with only closes the
    # stream, never the shared client.
    client = get_shared_client()
    for redirect_count in range(MAX_REDIRECTS + 1):
        normalized, hostname, port, scheme = validate_public_url(current_url)
        # DNS is part of the caller's request deadline. Without this outer
        # cancellation boundary, a resolver stall can outlive httpx's connect
        # timeout and keep a GUI job alive until the appserver watchdog kills
        # it as an opaque "job stalled" failure.
        addresses = await asyncio.wait_for(
            resolve_public_addresses(hostname, port), timeout=timeout
        )
        pinned, host_header = _pinned_url(normalized, addresses[0], port)
        hop_headers = {**request_headers, "Host": host_header}
        extensions = {"sni_hostname": hostname} if scheme == "https" else None

        async with client.stream(
            "GET",
            pinned,
            headers=hop_headers,
            extensions=extensions,
            timeout=httpx.Timeout(timeout),
        ) as response:
            peer = _connected_address(response)
            if peer is not None and (
                not is_public_address(peer) or peer not in addresses
            ):
                raise UnsafeUrlError(
                    "connected peer did not match validated DNS"
                )

            if response.status_code in REDIRECT_STATUSES:
                location = response.headers.get("location")
                if not location:
                    raise UnsafeUrlError("redirect response omitted Location")
                if redirect_count >= MAX_REDIRECTS:
                    raise UnsafeUrlError("too many redirects")
                current_url = urljoin(normalized, location)
                continue

            raw = await _read_limited(response, max_bytes)
            request = httpx.Request("GET", normalized, headers=request_headers)
            # aiter_bytes() already yields decoded content, but httpx keeps
            # the Content-Encoding header on the stream. Re-constructing a
            # Response with decoded bytes while keeping that header makes
            # .text/.content try to decompress plaintext a second time and
            # fail (brotli: decoder failed). Drop the header so the
            # re-constructed response treats the bytes as final.
            final_headers = {
                key: value
                for key, value in response.headers.items()
                if key.lower() not in {"content-encoding", "content-length"}
            }
            return httpx.Response(
                response.status_code,
                headers=final_headers,
                content=raw,
                request=request,
            )
    raise UnsafeUrlError("too many redirects")


def fetch_public_response_sync(
    url: str,
    *,
    timeout: float = 30,
    max_bytes: int = 1_000_000,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Synchronous compatibility wrapper for non-event-loop callers."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            fetch_public_response(
                url,
                timeout=timeout,
                max_bytes=max_bytes,
                headers=headers,
            )
        )
    raise RuntimeError("synchronous safe HTTP cannot run inside an event loop")


def safe_url_label(url: str) -> str:
    """Describe a URL without reflecting credentials, query, or fragment."""
    try:
        parsed = urlsplit(str(url or ""))
        return urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "", ""))
    except ValueError:
        return "<invalid-url>"
