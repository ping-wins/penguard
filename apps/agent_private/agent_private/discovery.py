from __future__ import annotations

import ipaddress
import json
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import psutil

DISCOVERY_REQUEST_TYPE = "penguard.agent_discovery.v1"
DISCOVERY_RESPONSE_TYPE = "penguard.agent_discovery.response.v1"
DEFAULT_DISCOVERY_PORT = 8764
DEFAULT_DISCOVERY_TIMEOUT_SECONDS = 5.0


class DashboardDiscoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class DashboardDiscovery:
    api_url: str
    source_host: str
    api_port: int
    api_scheme: str


def build_discovery_request(nonce: str) -> bytes:
    return json.dumps(
        {
            "type": DISCOVERY_REQUEST_TYPE,
            "nonce": nonce,
            "service": "agent_private",
        }
    ).encode("utf-8")


def parse_discovery_response(
    data: bytes,
    addr: tuple[str, int],
    *,
    nonce: str,
) -> DashboardDiscovery | None:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("type") != DISCOVERY_RESPONSE_TYPE:
        return None
    if payload.get("nonce") != nonce:
        return None

    scheme = str(payload.get("apiScheme") or "http").lower()
    if scheme not in {"http", "https"}:
        return None
    try:
        port = int(payload.get("apiPort") or 8000)
    except (TypeError, ValueError):
        return None
    if port <= 0 or port > 65535:
        return None

    source_host = addr[0]
    return DashboardDiscovery(
        api_url=f"{scheme}://{source_host}:{port}",
        source_host=source_host,
        api_port=port,
        api_scheme=scheme,
    )


def broadcast_targets(port: int = DEFAULT_DISCOVERY_PORT) -> list[tuple[str, int]]:
    targets: set[tuple[str, int]] = {("255.255.255.255", port)}
    for rows in psutil.net_if_addrs().values():
        for row in rows:
            if row.family != socket.AF_INET or not row.address or not row.netmask:
                continue
            try:
                address = ipaddress.IPv4Address(row.address)
                if address.is_loopback:
                    continue
                network = ipaddress.IPv4Network(f"{row.address}/{row.netmask}", strict=False)
            except ValueError:
                continue
            targets.add((str(network.broadcast_address), port))
    return sorted(targets)


def candidate_api_urls(api_port: int = 8000) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for rows in psutil.net_if_addrs().values():
        for row in rows:
            if row.family != socket.AF_INET or not row.address or not row.netmask:
                continue
            try:
                address = ipaddress.IPv4Address(row.address)
                if address.is_loopback:
                    continue
                network = ipaddress.IPv4Network(f"{row.address}/{row.netmask}", strict=False)
                candidates = (
                    ipaddress.IPv4Address(int(network.network_address) + 1),
                    ipaddress.IPv4Address(int(network.network_address) + 2),
                )
            except ValueError:
                continue
            for candidate in candidates:
                if candidate == address or candidate not in network:
                    continue
                url = f"http://{candidate}:{api_port}"
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
    return urls


def probe_dashboard_api(api_url: str, *, timeout: float = 0.35) -> bool:
    try:
        response = httpx.get(f"{api_url.rstrip('/')}/health", timeout=timeout)
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    return payload.get("status") == "ok"


def _discovery_from_api_url(api_url: str) -> DashboardDiscovery:
    parsed = urlparse(api_url)
    return DashboardDiscovery(
        api_url=api_url.rstrip("/"),
        source_host=parsed.hostname or api_url,
        api_port=parsed.port or (443 if parsed.scheme == "https" else 80),
        api_scheme=parsed.scheme or "http",
    )


def discover_dashboard(
    *,
    timeout_seconds: float = DEFAULT_DISCOVERY_TIMEOUT_SECONDS,
    port: int = DEFAULT_DISCOVERY_PORT,
) -> DashboardDiscovery:
    nonce = uuid4().hex
    packet = build_discovery_request(nonce)
    deadline = time.monotonic() + max(timeout_seconds, 0.1)
    targets = broadcast_targets(port)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.25)
        for target in targets:
            try:
                sock.sendto(packet, target)
            except OSError:
                continue
        while time.monotonic() < deadline:
            sock.settimeout(max(0.05, min(0.25, deadline - time.monotonic())))
            try:
                data, addr = sock.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                continue
            result = parse_discovery_response(data, addr, nonce=nonce)
            if result is not None:
                return result

    for api_url in candidate_api_urls():
        if probe_dashboard_api(api_url):
            return _discovery_from_api_url(api_url)

    raise DashboardDiscoveryError(
        "Penguard API was not discovered on the local VMware network."
    )
