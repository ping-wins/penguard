import argparse
import json
import os
from typing import Any

import httpx

DEFAULT_SIEM_URL = "http://siem-kowalski:8000"
DEFAULT_SOAR_URL = "http://soar-skipper:8000"
DEFAULT_XDR_URL = "http://xdr-rico:8000"

DEMO_EVENTS: list[dict[str, Any]] = [
    {
        "source": "fortigate",
        "eventType": "network.scan",
        "severity": "high",
        "occurredAt": "2026-05-08T12:00:00.000Z",
        "entities": {"sourceIp": "192.0.2.10", "destinationIp": "198.51.100.20"},
        "attributes": {"count": 42},
    },
    {
        "source": "fortigate",
        "eventType": "network.deny",
        "severity": "medium",
        "occurredAt": "2026-05-08T12:01:00.000Z",
        "entities": {"sourceIp": "192.0.2.30", "destinationIp": "198.51.100.20"},
        "attributes": {"action": "deny", "count": 25},
    },
    {
        "source": "agent_private",
        "eventType": "endpoint.suspicious_connection",
        "severity": "high",
        "occurredAt": "2026-05-08T12:02:00.000Z",
        "entities": {"endpointId": "demo-endpoint-01", "hostname": "demo-endpoint-01"},
        "attributes": {"destinationIp": "198.51.100.20"},
    },
]

DEMO_ENDPOINT_EVENT = {
    "endpointId": "demo-endpoint-01",
    "eventType": "heartbeat",
    "occurredAt": "2026-05-08T12:00:00.000Z",
    "hostname": "demo-endpoint-01",
    "ipAddresses": ["192.0.2.50"],
    "currentUser": "SOC-DEMO\\analyst",
    "health": "healthy",
    "attributes": {"os": "Linux", "source": "seed"},
}


def seed_demo_data(
    *,
    siem_url: str,
    soar_url: str,
    xdr_url: str,
    dry_run: bool = False,
    allow_demo_data: bool = False,
    client: Any | None = None,
) -> dict[str, Any]:
    if dry_run:
        return {
            "dryRun": True,
            "siemEvents": DEMO_EVENTS,
            "xdrEndpointEvent": DEMO_ENDPOINT_EVENT,
            "soarDefaults": ["pb_port_scan_triage", "pb_suspicious_endpoint_triage"],
        }
    if not allow_demo_data:
        raise RuntimeError(
            "Refusing to write demo data without explicit acknowledgement. "
            "Pass --i-understand-this-is-demo-data for isolated lab runs."
        )

    owns_client = client is None
    http_client = client or httpx.Client(timeout=5.0)
    try:
        created_events = [
            _post_json(http_client, f"{siem_url.rstrip('/')}/events", event)
            for event in DEMO_EVENTS
        ]
        enrollment = _post_json(
            http_client,
            f"{xdr_url.rstrip('/')}/enrollments",
            {"displayName": "Demo endpoint"},
        )
        endpoint_event = _post_json(
            http_client,
            f"{xdr_url.rstrip('/')}/endpoint-events",
            DEMO_ENDPOINT_EVENT,
            headers={"Authorization": f"Bearer {enrollment['token']}"},
        )
        playbooks = _get_json(http_client, f"{soar_url.rstrip('/')}/playbooks")
    finally:
        if owns_client:
            http_client.close()

    return {
        "dryRun": False,
        "createdEventIds": [event["id"] for event in created_events],
        "endpointId": endpoint_event["endpoint"]["id"],
        "playbookIds": [playbook["id"] for playbook in playbooks],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed local SOC-lite demo data.")
    parser.add_argument(
        "--siem-url",
        default=os.getenv("FORTIDASHBOARD_SIEM_KOWALSKI_URL", DEFAULT_SIEM_URL),
    )
    parser.add_argument(
        "--soar-url",
        default=os.getenv("FORTIDASHBOARD_SOAR_SKIPPER_URL", DEFAULT_SOAR_URL),
    )
    parser.add_argument(
        "--xdr-url",
        default=os.getenv("FORTIDASHBOARD_XDR_RICO_URL", DEFAULT_XDR_URL),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the demo payloads without sending HTTP requests.",
    )
    parser.add_argument(
        "--i-understand-this-is-demo-data",
        action="store_true",
        dest="allow_demo_data",
        help="Required for HTTP writes; labels this as an isolated lab/demo data operation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = seed_demo_data(
        siem_url=args.siem_url,
        soar_url=args.soar_url,
        xdr_url=args.xdr_url,
        dry_run=args.dry_run,
        allow_demo_data=args.allow_demo_data,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _post_json(
    client: httpx.Client,
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    response = client.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def _get_json(client: httpx.Client, url: str) -> Any:
    response = client.get(url)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    raise SystemExit(main())
