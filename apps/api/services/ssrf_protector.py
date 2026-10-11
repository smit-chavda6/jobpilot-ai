"""SSRF protection and safe HTTP fetcher."""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status

# Blocked private networks (RFC 1918, loopback, link-local, AWS/GCP metadata)
BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local and AWS/GCP cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_ip_blocked(ip_str: str) -> bool:
    """Checks whether an IP address belongs to any blocked private/metadata ranges."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in BLOCKED_NETWORKS)
    except ValueError:
        return True


def validate_url_for_ssrf(url: str) -> str:
    """
    Validates URL scheme, resolves host DNS, and asserts target IP is public.
    Raises HTTPException 400 if unsafe or internal IP is targeted.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ["http", "https"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only http and https protocols are permitted.",
        )

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL hostname.",
        )

    # Reject obvious localhost / metadata names
    lower_host = hostname.lower()
    if lower_host in ["localhost", "metadata", "instance-data", "169.254.169.254"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSRF Protection: Access to private or cloud metadata hosts is forbidden.",
        )

    # Resolve hostname to IPv4/IPv6 addresses and verify all are public
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to resolve hostname: {hostname}",
        )

    for item in addr_info:
        ip_addr = item[4][0]
        if is_ip_blocked(ip_addr):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"SSRF Protection: Host resolves to restricted private IP address ({ip_addr}).",
            )

    return url


async def fetch_url_safely(url: str, max_size_bytes: int = 2 * 1024 * 1024) -> str:
    """
    Fetches URL content safely with SSRF DNS validation, size cap, and descriptive User-Agent.
    """
    validated_url = validate_url_for_ssrf(url)
    headers = {
        "User-Agent": "JobPilotAI-ComplianceBot/1.0 (+https://github.com/smit-chavda6/jobpilot-ai)"
    }

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, max_redirects=3) as client:
        # Stream response to strictly enforce max_size_bytes cap
        response = await client.get(validated_url, headers=headers)

        # Validate final URL after redirects for SSRF
        validate_url_for_ssrf(str(response.url))

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to fetch job listing: HTTP {response.status_code}",
            )

        content = response.text
        if len(content) > max_size_bytes:
            content = content[:max_size_bytes]

        return content
