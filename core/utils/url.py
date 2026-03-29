"""URL validation utilities for SSRF protection.

Validates user-supplied URLs to prevent Server-Side Request Forgery (SSRF)
by blocking internal/private IP addresses and enforcing allowed schemes.
"""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Private/reserved networks that must be blocked
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("10.0.0.0/8"),         # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),      # RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),     # RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local
    ipaddress.ip_network("0.0.0.0/8"),          # "This" network
    ipaddress.ip_network("100.64.0.0/10"),      # Shared address space (CGNAT)
    ipaddress.ip_network("198.18.0.0/15"),      # Benchmarking
    ipaddress.ip_network("::1/128"),             # IPv6 loopback
    ipaddress.ip_network("fe80::/10"),           # IPv6 link-local
    ipaddress.ip_network("fc00::/7"),            # IPv6 unique local
    ipaddress.ip_network("::ffff:0:0/96"),       # IPv4-mapped IPv6
]

_ALLOWED_SCHEMES = {"http", "https"}


class SSRFError(ValueError):
    """Raised when a URL fails SSRF validation."""


def validate_url(url: str, *, resolve_dns: bool = True) -> str:
    """Validate a URL against SSRF attacks.

    Checks:
    - Only http:// and https:// schemes are allowed
    - Hostname must not resolve to a private/internal IP
    - DNS resolution is performed to catch DNS rebinding

    Args:
        url: The URL to validate.
        resolve_dns: Whether to resolve the hostname and check the IP.
            Set to False for URLs that will only be stored, not fetched.

    Returns:
        The validated URL (unchanged).

    Raises:
        SSRFError: If the URL fails validation.
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise SSRFError(f"Invalid URL: {e}") from e

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise SSRFError(
            f"URL scheme '{parsed.scheme}' not allowed. "
            f"Only {', '.join(sorted(_ALLOWED_SCHEMES))} are permitted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL has no hostname")

    # Block raw IP addresses in private ranges (even without DNS resolution)
    try:
        ip = ipaddress.ip_address(hostname)
        if _is_blocked_ip(ip):
            raise SSRFError(f"URL points to a blocked IP address: {hostname}")
    except ValueError:
        # hostname is not an IP literal — that's fine, we'll resolve it below
        pass

    if resolve_dns:
        _check_dns_resolution(hostname)

    return url


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address belongs to a blocked network."""
    for network in _BLOCKED_NETWORKS:
        if ip in network:
            return True
    return False


def _check_dns_resolution(hostname: str) -> None:
    """Resolve hostname and verify none of the addresses are internal.

    This prevents DNS rebinding attacks where a hostname initially resolves
    to a public IP but later resolves to an internal IP.
    """
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise SSRFError(f"DNS resolution failed for '{hostname}': {e}") from e

    if not results:
        raise SSRFError(f"DNS resolution returned no results for '{hostname}'")

    for family, _, _, _, sockaddr in results:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            raise SSRFError(
                f"URL hostname '{hostname}' resolves to blocked IP {ip_str}"
            )
