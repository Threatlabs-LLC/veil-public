"""URL validation for SSRF protection.

Blocks requests to internal/private network addresses, cloud metadata
endpoints, and link-local addresses.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Hostnames that should always be blocked
BLOCKED_HOSTNAMES = frozenset({
    "metadata.google.internal",
    "metadata.internal",
    "169.254.169.254",
})


def is_safe_url(url: str) -> tuple[bool, str]:
    """Validate that a URL is safe to make requests to.

    Returns (is_safe, reason). If not safe, reason explains why.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL"

    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported scheme: {parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname in URL"

    # Block known metadata hostnames
    if hostname.lower() in BLOCKED_HOSTNAMES:
        return False, f"Blocked hostname: {hostname}"

    # Resolve DNS and check the IP
    try:
        results = socket.getaddrinfo(hostname, parsed.port or 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return False, f"DNS resolution failed for {hostname}"

    for family, _, _, _, sockaddr in results:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if ip.is_private:
            return False, f"Private IP address: {ip_str}"
        if ip.is_loopback:
            return False, f"Loopback address: {ip_str}"
        if ip.is_link_local:
            return False, f"Link-local address: {ip_str}"
        if ip.is_reserved:
            return False, f"Reserved address: {ip_str}"
        # Block AWS/cloud metadata range
        if ip_str.startswith("169.254."):
            return False, f"Metadata address: {ip_str}"

    return True, "OK"
