from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from app.auth.csrf_dependency import require_csrf
from app.auth.dependencies import get_auth_audit_store, get_current_api_user
from app.core.config import get_settings
from app.routers.soc import SocClient, get_siem_client, get_xdr_client

router = APIRouter(tags=["lab-demo"])

DEMO_SOURCE_TAG = "demo.replay"
DEMO_ATTACK_TYPES = ("port_scan", "brute_force", "c2_beacon")


class AuditStore(Protocol):
    def record(
        self,
        *,
        action: str,
        outcome: str,
        email: str | None = None,
        user_id: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> None:
        pass


def _demo_attack_event(attack_type: str, *, now: datetime, demo_run_id: str) -> dict[str, Any]:
    base = now.astimezone(UTC)

    def stamp(offset_seconds: int) -> str:
        return (
            (base - timedelta(seconds=offset_seconds))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    if attack_type == "port_scan":
        return {
            "source": DEMO_SOURCE_TAG,
            "eventType": "network.deny",
            "severity": "high",
            "occurredAt": stamp(180),
            "entities": {
                "sourceIp": "203.0.113.77",
                "destinationIp": "192.168.0.50",
                "integrationId": "demo-fortigate",
            },
            "attributes": {
                "action": "deny",
                "subtype": "port_scan",
                "message": "Inbound port scan from 203.0.113.77",
                "count": 42,
                "uniqueDestinationCount": 1,
                "demoRunId": demo_run_id,
                "attackType": attack_type,
            },
        }
    if attack_type == "brute_force":
        return {
            "source": DEMO_SOURCE_TAG,
            "eventType": "auth.failed_login",
            "severity": "medium",
            "occurredAt": stamp(120),
            "entities": {
                "sourceIp": "203.0.113.77",
                "username": "svc-backup",
                "integrationId": "demo-fortigate",
            },
            "attributes": {
                "count": 9,
                "message": "Repeated SSH login failures for svc-backup",
                "demoRunId": demo_run_id,
                "attackType": attack_type,
            },
        }
    if attack_type == "c2_beacon":
        return {
            "source": DEMO_SOURCE_TAG,
            "eventType": "endpoint.suspicious_connection",
            "severity": "high",
            "occurredAt": stamp(60),
            "entities": {
                "endpointId": "demo-endpoint-01",
                "hostname": "demo-endpoint-01",
                "sourceIp": "192.168.0.50",
                "destinationIp": "203.0.113.77",
            },
            "attributes": {
                "message": "Endpoint demo-endpoint-01 dialed back to attacker IP",
                "demoRunId": demo_run_id,
                "attackType": attack_type,
            },
        }
    raise HTTPException(status_code=400, detail=f"Unknown demo attack type: {attack_type}")


def _demo_replay_events(
    *, now: datetime, demo_run_id: str, attack_types: list[str] | None = None
) -> list[dict[str, Any]]:
    requested = list(attack_types) if attack_types else list(DEMO_ATTACK_TYPES)
    unknown = [t for t in requested if t not in DEMO_ATTACK_TYPES]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown demo attack type(s): {', '.join(sorted(set(unknown)))}",
        )
    ordered = [t for t in DEMO_ATTACK_TYPES if t in set(requested)]
    return [_demo_attack_event(t, now=now, demo_run_id=demo_run_id) for t in ordered]


@router.post("/soc/demo/replay")
def replay_demo_incident(
    request: Request,
    client: Annotated[SocClient, Depends(get_siem_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
    payload: Annotated[dict[str, Any] | None, Body()] = None,
) -> dict:
    if not get_settings().enable_lab_demo_tools:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    roles = set(current_user.get("roles") or [])
    if "admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo replay requires the admin role.",
        )

    raw_types = (payload or {}).get("attackTypes") if isinstance(payload, dict) else None
    if raw_types is not None and not isinstance(raw_types, list):
        raise HTTPException(status_code=400, detail="attackTypes must be a list of strings")
    attack_types = [str(t) for t in raw_types] if raw_types else None

    now = datetime.now(UTC)
    demo_run_id = f"demo_{now.strftime('%Y%m%d_%H%M%S')}"
    events = _demo_replay_events(now=now, demo_run_id=demo_run_id, attack_types=attack_types)
    created: list[dict[str, Any]] = []
    for event in events:
        try:
            created.append(client.request("POST", "/events", json=event))
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            _audit(
                audit_store,
                request=request,
                current_user=current_user,
                action="soc.demo.replay",
                details={
                    "demoRunId": demo_run_id,
                    "error": str(exc),
                    "stage": event["eventType"],
                    "attackTypes": [e["attributes"]["attackType"] for e in events],
                },
                outcome="failure",
            )
            raise HTTPException(
                status_code=502,
                detail=f"Demo replay failed at {event['eventType']}: {exc}",
            ) from exc

    injected_types = [e["attributes"]["attackType"] for e in events]
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="soc.demo.replay",
        details={
            "demoRunId": demo_run_id,
            "eventCount": len(created),
            "service": "siem_kowalski",
            "attackTypes": injected_types,
        },
    )
    return {
        "demoRunId": demo_run_id,
        "eventCount": len(created),
        "attackTypes": injected_types,
        "eventIds": [
            event.get("id") for event in created if isinstance(event, dict) and event.get("id")
        ],
    }

@router.post("/weapons/simulator/events")
def create_simulator_events(
    request: Request,
    client: Annotated[SocClient, Depends(get_xdr_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
    payload: Annotated[dict[str, Any] | None, Body()] = None,
) -> dict:
    if not get_settings().enable_lab_demo_tools:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    response = client.request("POST", "/simulator/events", json=payload or {})
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="xdr.simulator_events.created",
        details={"service": "xdr_rico", "count": response.get("createdEvents")},
    )
    return response


def _audit(
    audit_store: AuditStore,
    *,
    request: Request,
    current_user: dict,
    action: str,
    details: dict,
    outcome: str = "success",
) -> None:
    audit_store.record(
        action=action,
        outcome=outcome,
        email=current_user.get("email"),
        user_id=str(current_user["id"]),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=details,
    )


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host
