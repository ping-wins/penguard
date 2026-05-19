from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)
DISCOVERY_REQUEST_TYPE = "penguard.agent_discovery.v1"
DISCOVERY_RESPONSE_TYPE = "penguard.agent_discovery.response.v1"


class AgentDiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        *,
        api_port: int,
        api_scheme: str = "http",
        api_base_path: str = "/api",
    ) -> None:
        self.api_port = api_port
        self.api_scheme = api_scheme
        self.api_base_path = api_base_path
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self.transport is None:
            return
        try:
            request = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(request, dict) or request.get("type") != DISCOVERY_REQUEST_TYPE:
            return

        nonce = request.get("nonce")
        response: dict[str, Any] = {
            "type": DISCOVERY_RESPONSE_TYPE,
            "product": "Penguard",
            "apiScheme": self.api_scheme,
            "apiPort": self.api_port,
            "apiBasePath": self.api_base_path,
        }
        if isinstance(nonce, str):
            response["nonce"] = nonce

        self.transport.sendto(json.dumps(response).encode("utf-8"), addr)


async def start_agent_discovery_udp_responder(
    *,
    host: str,
    port: int,
    api_port: int,
    api_scheme: str = "http",
    api_base_path: str = "/api",
) -> asyncio.DatagramTransport:
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: AgentDiscoveryProtocol(
            api_port=api_port,
            api_scheme=api_scheme,
            api_base_path=api_base_path,
        ),
        local_addr=(host, port),
        allow_broadcast=True,
    )
    logger.info(
        "agent_discovery_udp_started host=%s port=%s api_scheme=%s api_port=%s",
        host,
        port,
        api_scheme,
        api_port,
    )
    return transport
