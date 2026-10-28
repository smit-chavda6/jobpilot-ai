"""SSRF-hardened HTTP fetching (spec §7.2).

- http(s) only; no credentials in URLs; default ports only (80/443)
- every hop's hostname is resolved and ALL addresses must be public (blocks private, loopback,
  link-local, metadata, multicast, reserved, CGNAT, IPv4-mapped IPv6)
- redirects followed manually (max 3) and re-validated on every hop
- response size, time and content-type capped; descriptive User-Agent
- robots.txt honoured when fetching HTML pages

Residual risk (documented in threat-model.md): DNS rebinding between our resolution and the
HTTP client's own resolution. Mitigated by short timeouts and re-validation per hop.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.config import get_settings
from app.errors import UnprocessableError

MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal", "metadata", "instance-data"}


class FetchBlocked(UnprocessableError):
    code = "fetch_blocked"


@dataclass
class FetchResult:
    url: str
    status: int
    content_type: str
    text: str


def is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if addr in ipaddress.ip_network("100.64.0.0/10"):  # CGNAT
        return False
    return addr.is_global and not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


async def _resolve(host: str) -> list[str]:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchBlocked(f"Could not resolve host {host}") from exc
    return list({str(info[4][0]) for info in infos})


async def validate_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        raise FetchBlocked("Invalid URL") from exc
    if parts.scheme not in ("http", "https"):
        raise FetchBlocked("Only http(s) URLs are allowed")
    if parts.username or parts.password:
        raise FetchBlocked("URLs with credentials are not allowed")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or host in _BLOCKED_HOSTNAMES or host.endswith((".local", ".internal", ".localhost")):
        raise FetchBlocked("This host is not allowed")
    if parts.port not in (None, 80, 443):
        raise FetchBlocked("Only default ports are allowed")
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
        addresses = [str(literal)]
    except ValueError:
        addresses = await _resolve(host)
    if not addresses or not all(is_public_ip(a) for a in addresses):
        raise FetchBlocked("This address is not publicly routable and cannot be fetched")
    return url.strip()


async def _robots_allows(client: httpx.AsyncClient, url: str, ua: str) -> bool:
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        await validate_url(robots_url)
        resp = await client.get(robots_url, follow_redirects=False)
    except (httpx.HTTPError, FetchBlocked):
        return True  # unreachable robots.txt => no restrictions declared
    if resp.status_code >= 400:
        return True
    rp = RobotFileParser()
    rp.parse(resp.text[:100_000].splitlines())
    return rp.can_fetch(ua, url)


async def safe_get(
    url: str,
    *,
    accept: str = "text/html,application/json,application/xml;q=0.9,*/*;q=0.5",
    check_robots: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchResult:
    ua = get_settings().fetch_user_agent
    async with httpx.AsyncClient(
        timeout=TIMEOUT, headers={"User-Agent": ua, "Accept": accept}, transport=transport
    ) as client:
        current = await validate_url(url)
        if check_robots and not await _robots_allows(client, current, ua):
            raise FetchBlocked("This site's robots.txt disallows automated fetching of this page")
        for _ in range(MAX_REDIRECTS + 1):
            async with client.stream("GET", current, follow_redirects=False) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise FetchBlocked("Redirect without location")
                    current = await validate_url(urljoin(current, location))
                    continue
                declared = int(resp.headers.get("content-length") or 0)
                if declared > MAX_BYTES:
                    raise FetchBlocked("Response too large")
                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise FetchBlocked("Response too large")
                if resp.status_code >= 400:
                    raise UnprocessableError(
                        f"The page returned HTTP {resp.status_code}",
                        code="fetch_failed",
                        details={"status": resp.status_code},
                    )
                ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                return FetchResult(current, resp.status_code, ctype, body.decode(resp.encoding or "utf-8", "replace"))
        raise FetchBlocked("Too many redirects")


async def safe_get_with_retry(url: str, attempts: int = 3, **kwargs: object) -> FetchResult:
    """Retries transient network errors with exponential backoff + jitter (never 4xx/blocked)."""
    import random

    delay = 0.5
    for i in range(attempts):
        try:
            return await safe_get(url, **kwargs)  # type: ignore[arg-type]
        except (httpx.TransportError, httpx.TimeoutException):
            if i == attempts - 1:
                raise UnprocessableError("The site could not be reached", code="fetch_failed") from None
            await asyncio.sleep(delay + random.uniform(0, delay))
            delay *= 2
    raise AssertionError("unreachable")
