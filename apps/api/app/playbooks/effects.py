from __future__ import annotations

import re
from typing import Any, Protocol

from app.playbooks.webhook_destinations import PlaybookWebhookDestinationService


class SocClient(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        pass_through_statuses: set[int] | None = None,
    ) -> dict[str, Any]:
        pass


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


def execute_playbook_effects(
    *,
    playbook: dict[str, Any],
    run: dict[str, Any],
    incident: dict[str, Any],
    siem_client: SocClient,
    audit_store: AuditStore,
    webhook_destinations: PlaybookWebhookDestinationService,
    actor: dict[str, Any],
    client_ip: str | None,
    user_agent: str | None,
) -> list[dict[str, Any]]:
    nodes = [node for node in playbook.get("nodes", []) if isinstance(node, dict)]
    if not nodes:
        return []

    effects: list[dict[str, Any]] = []
    outputs: dict[str, dict[str, Any]] = {}
    for node in _walk_nodes(playbook, incident):
        node_type = str(node.get("type") or "")
        node_id = str(node.get("id") or node_type)
        config = node.get("config") if isinstance(node.get("config"), dict) else {}

        if node_type == "trigger.incident_created":
            continue

        if node_type == "condition.severity":
            matched = _severity_matches(config, incident)
            effect = {
                "nodeId": node_id,
                "nodeType": node_type,
                "status": "completed" if matched else "skipped",
                "output": {
                    "matched": matched,
                    "incidentSeverity": str(incident.get("severity") or ""),
                },
            }
            effects.append(effect)
            outputs[node_id] = effect["output"]
            if not matched and not _has_false_edge(playbook, node_id):
                break
            continue

        if node_type == "enrich.ip":
            field = str(config.get("field") or "")
            value = _value_at_path(incident, field)
            effect = {
                "nodeId": node_id,
                "nodeType": node_type,
                "status": "completed",
                "output": {"field": field, "value": value},
            }
            effects.append(effect)
            outputs[node_id] = effect["output"]
            continue

        if node_type == "case.note":
            note = _render(str(config.get("template") or ""), incident=incident, outputs=outputs)
            siem_client.request(
                "PATCH",
                f"/incidents/{run.get('incidentId')}/triage",
                json={"note": note},
            )
            effects.append(
                {
                    "nodeId": node_id,
                    "nodeType": node_type,
                    "status": "completed",
                    "output": {"note": note},
                }
            )
            continue

        if node_type == "audit.note":
            message = _render(str(config.get("message") or ""), incident=incident, outputs=outputs)
            audit_store.record(
                action="soc.playbook.audit_note",
                outcome="success",
                email=actor.get("email"),
                user_id=str(actor.get("id") or actor.get("user_id") or ""),
                client_ip=client_ip,
                user_agent=user_agent,
                details={
                    "runId": run.get("id"),
                    "playbookId": run.get("playbookId"),
                    "incidentId": run.get("incidentId"),
                    "nodeId": node_id,
                    "message": message,
                },
            )
            effects.append(
                {
                    "nodeId": node_id,
                    "nodeType": node_type,
                    "status": "completed",
                    "output": {"message": message},
                }
            )
            continue

        if node_type == "notify.webhook":
            destination_id = str(config.get("destinationId") or "")
            content = _render(
                str(config.get("content") or config.get("message") or ""),
                incident=incident,
                outputs=outputs,
            )
            payload = {"content": content}
            if config.get("username"):
                payload["username"] = str(config["username"])
            result = webhook_destinations.send(
                owner_user_id=str(actor.get("id") or actor.get("user_id") or ""),
                destination_id=destination_id,
                payload=payload,
            )
            public_destination = webhook_destinations.public_item(
                owner_user_id=str(actor.get("id") or actor.get("user_id") or ""),
                destination_id=destination_id,
            )
            audit_store.record(
                action="soc.playbook.webhook_sent",
                outcome="success" if result["ok"] else "failure",
                email=actor.get("email"),
                user_id=str(actor.get("id") or actor.get("user_id") or ""),
                client_ip=client_ip,
                user_agent=user_agent,
                details={
                    "runId": run.get("id"),
                    "playbookId": run.get("playbookId"),
                    "incidentId": run.get("incidentId"),
                    "nodeId": node_id,
                    "destinationId": destination_id,
                    "redactedUrl": public_destination.get("redactedUrl"),
                    "statusCode": result["statusCode"],
                },
            )
            effects.append(
                {
                    "nodeId": node_id,
                    "nodeType": node_type,
                    "status": "completed" if result["ok"] else "failed",
                    "output": {
                        "destinationId": destination_id,
                        "statusCode": result["statusCode"],
                        "ok": result["ok"],
                    },
                }
            )
            continue

        if node_type == "webhook.dry_run":
            effects.append(
                {
                    "nodeId": node_id,
                    "nodeType": node_type,
                    "status": "completed",
                    "output": {"dryRun": True, "method": config.get("method") or "POST"},
                }
            )
            continue

        if node_type == "approval.required":
            effects.append(
                {
                    "nodeId": node_id,
                    "nodeType": node_type,
                    "status": "waiting_approval",
                    "output": {"role": config.get("role") or "admin"},
                }
            )
            break

        if node_type in {
            "fortigate.recommend_block",
            "fortigate.temporary_block",
            "fortiweb.recommend_block",
        }:
            effects.append(
                {
                    "nodeId": node_id,
                    "nodeType": node_type,
                    "status": "waiting_approval",
                    "output": {
                        "reviewRequired": True,
                        "provider": node_type.split(".", 1)[0],
                    },
                }
            )
            break

    return effects


def _walk_nodes(playbook: dict[str, Any], incident: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [node for node in playbook.get("nodes", []) if isinstance(node, dict)]
    if not nodes:
        return []
    nodes_by_id = {str(node.get("id")): node for node in nodes}
    outgoing: dict[str, list[dict[str, Any]]] = {str(node.get("id")): [] for node in nodes}
    incoming: set[str] = set()
    for edge in playbook.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if source and target:
            outgoing.setdefault(source, []).append(edge)
            incoming.add(target)
    current = next(
        (node for node in nodes if node.get("type") == "trigger.incident_created"),
        next((node for node in nodes if str(node.get("id")) not in incoming), nodes[0]),
    )
    visited: set[str] = set()
    ordered: list[dict[str, Any]] = []
    while current:
        current_id = str(current.get("id"))
        if current_id in visited:
            break
        visited.add(current_id)
        ordered.append(current)
        current = _next_node(current, outgoing.get(current_id, []), nodes_by_id, incident)
    return ordered


def _next_node(
    node: dict[str, Any],
    edges: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
    incident: dict[str, Any],
) -> dict[str, Any] | None:
    if not edges:
        return None
    if node.get("type") == "condition.severity":
        desired = "true" if _severity_matches(_config(node), incident) else "false"
        edge = next((item for item in edges if item.get("condition") == desired), None)
        if edge is None and desired == "true":
            edge = next(
                (item for item in edges if item.get("condition") in (None, "", "success")),
                None,
            )
        if edge is None:
            return None
        return nodes_by_id.get(str(edge.get("to")))
    edge = next(
        (item for item in edges if item.get("condition") in (None, "", "success")),
        edges[0],
    )
    return nodes_by_id.get(str(edge.get("to")))


def _severity_matches(config: dict[str, Any], incident: dict[str, Any]) -> bool:
    allowed = config.get("severity")
    if not isinstance(allowed, list):
        return True
    incident_severity = str(incident.get("severity") or "").lower()
    return incident_severity in {str(item).lower() for item in allowed}


def _has_false_edge(playbook: dict[str, Any], node_id: str) -> bool:
    return any(
        isinstance(edge, dict)
        and edge.get("from") == node_id
        and edge.get("condition") == "false"
        for edge in playbook.get("edges", [])
    )


def _config(node: dict[str, Any]) -> dict[str, Any]:
    return node.get("config") if isinstance(node.get("config"), dict) else {}


def _render(template: str, *, incident: dict[str, Any], outputs: dict[str, dict[str, Any]]) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token.startswith("node."):
            _, node_id, *path = token.split(".")
            value = _value_at_path(outputs.get(node_id, {}), ".".join(path))
        else:
            value = _value_at_path({"incident": incident, **incident}, token)
        return "" if value is None else str(value)

    return re.sub(r"\{([a-zA-Z0-9_.]+)\}", replace, template)


def _value_at_path(payload: dict[str, Any], path: str) -> Any:
    if not path:
        return None
    current: Any = payload
    for segment in path.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        else:
            return None
    return current
