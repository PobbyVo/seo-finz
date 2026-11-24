from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

DEFAULT_PROVIDER_ENDPOINTS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "claude": "https://api.anthropic.com/v1",
    "mock": "mock://local",
}

ALLOWED_PROVIDER_HOSTS: dict[str, set[str]] = {
    "openai": {"api.openai.com"},
    "gemini": {"generativelanguage.googleapis.com"},
    "claude": {"api.anthropic.com"},
    "mock": {"local"},
}


def validate_provider_endpoint(provider: str, endpoint_url: str | None) -> str:
    """Validate provider endpoint against SSRF and enforce HTTPS for external hosts."""
    default_url = DEFAULT_PROVIDER_ENDPOINTS.get(provider)
    if not default_url:
        raise ValueError(f"Nhà cung cấp AI không được hỗ trợ: {provider}")

    if not endpoint_url or not endpoint_url.strip():
        return default_url

    cleaned = endpoint_url.strip().rstrip("/")
    if provider == "mock":
        return "mock://local"

    parsed = urlparse(cleaned)
    if parsed.scheme != "https":
        raise ValueError("Endpoint AI phải sử dụng HTTPS để bảo vệ API key.")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("Endpoint AI thiếu hostname hợp lệ.")

    # Block IP literals and private/loopback ranges to prevent SSRF
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("Endpoint trỏ tới địa chỉ IP nội bộ bị chặn để chống SSRF.")
        raise ValueError("Không cho phép gọi trực tiếp IP trần; hãy dùng tên miền chính thức của nhà cung cấp.")
    except ValueError as exc:
        if "SSRF" in str(exc) or "IP trần" in str(exc):
            raise

    allowed = ALLOWED_PROVIDER_HOSTS.get(provider, set())
    if hostname not in allowed:
        raise ValueError(
            f"Hostname '{hostname}' không nằm trong danh sách endpoint chính thức của {provider} ({', '.join(sorted(allowed))})."
        )

    return cleaned


def resolve_public_web_url(url: str) -> tuple[str, str, str]:
    """Resolve once; caller pins this IP for TLS connection (including redirects)."""
    import socket
    parsed=urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Chỉ cho phép URL HTTPS công khai ở cổng 443.')
    addresses={item[4][0] for item in socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError('SSRF: chặn địa chỉ mạng nội bộ hoặc không công khai.')
    return parsed.hostname, sorted(addresses)[0], (parsed.path or '/') + ('?'+parsed.query if parsed.query else '')
