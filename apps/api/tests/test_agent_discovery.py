import json

from app.agent_discovery import (
    DISCOVERY_REQUEST_TYPE,
    DISCOVERY_RESPONSE_TYPE,
    AgentDiscoveryProtocol,
)


class FakeDatagramTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))


def test_agent_discovery_protocol_replies_with_api_port_and_nonce():
    transport = FakeDatagramTransport()
    protocol = AgentDiscoveryProtocol(api_port=8000)
    protocol.connection_made(transport)  # type: ignore[arg-type]

    protocol.datagram_received(
        json.dumps({"type": DISCOVERY_REQUEST_TYPE, "nonce": "nonce-01"}).encode("utf-8"),
        ("192.168.56.101", 50123),
    )

    assert len(transport.sent) == 1
    data, addr = transport.sent[0]
    assert addr == ("192.168.56.101", 50123)
    assert json.loads(data.decode("utf-8")) == {
        "type": DISCOVERY_RESPONSE_TYPE,
        "product": "Penguard",
        "apiScheme": "http",
        "apiPort": 8000,
        "apiBasePath": "/api",
        "nonce": "nonce-01",
    }
