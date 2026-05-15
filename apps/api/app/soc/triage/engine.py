from datetime import UTC, datetime
from typing import Any

from .models import (
    EvidenceItem,
    ImpactedAsset,
    MissingDataItem,
    MitreMapping,
    PlaybookTemplateRecommendation,
    ResponseCandidate,
    TriageContext,
    TriageEntity,
)

SCAN_PORT_THRESHOLD = 20
BRUTE_FORCE_THRESHOLD = 3

ALERT_FAMILY_BY_RULE = {
    "network_scan": "network.scan",
    "denied_traffic_burst": "network.denied_burst",
    "repeated_failed_login": "auth.bruteforce",
    "suspicious_endpoint_connection": "endpoint.suspicious_connection",
    "privileged_logon_unusual_host": "identity.privileged_logon",
    "fortigate_resource_pressure": "fortigate.resource_pressure",
}


def build_triage_context(incident: dict[str, Any]) -> TriageContext:
    attributes = _dict_or_empty(incident.get("attributes"))
    entities_payload = _dict_or_empty(incident.get("entities"))
    rule_id = _string_or_none(incident.get("ruleId"))
    alert_family = ALERT_FAMILY_BY_RULE.get(rule_id or "", "manual.investigation")
    attack_type = _attack_type(alert_family, rule_id, attributes)
    evidence = _build_evidence(alert_family, incident, attributes, entities_payload)
    entities = _build_entities(attributes, entities_payload)
    response_candidates, missing_data = _build_response_candidates(
        alert_family=alert_family,
        attributes=attributes,
        entities=entities_payload,
    )
    mitre_mappings = _build_mitre_mappings(alert_family, evidence, attributes)
    playbook_templates = _build_playbook_templates(
        alert_family=alert_family,
        response_candidates=response_candidates,
        attributes=attributes,
        entities=entities_payload,
    )

    return TriageContext(
        incidentId=str(incident.get("id") or ""),
        ruleId=rule_id,
        alertFamily=alert_family,
        attackType=attack_type,
        severity=str(incident.get("severity") or "informational"),
        confidence=_confidence(alert_family, attributes),
        recommendedTriageLevel=_recommended_triage_level(incident),
        recommendedTicketStatus=_recommended_ticket_status(incident),
        summary=str(incident.get("summary") or incident.get("title") or ""),
        evidence=evidence,
        entities=entities,
        impactedAssets=_build_impacted_assets(attributes, entities_payload),
        mitreMappings=mitre_mappings,
        responseCandidates=response_candidates,
        playbookTemplates=playbook_templates,
        missingData=missing_data,
        generatedAt=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _attack_type(
    alert_family: str,
    rule_id: str | None,
    attributes: dict[str, Any],
) -> str:
    if isinstance(attributes.get("attackType"), str) and attributes["attackType"]:
        return attributes["attackType"]
    if alert_family == "network.denied_burst":
        return "denied_traffic_burst"
    if alert_family == "network.scan":
        return "port_scan"
    if alert_family == "auth.bruteforce":
        return "brute_force"
    return rule_id or alert_family


def _confidence(alert_family: str, attributes: dict[str, Any]) -> str:
    if alert_family == "network.scan":
        return "high" if _unique_port_count(attributes) >= SCAN_PORT_THRESHOLD else "medium"
    if alert_family == "auth.bruteforce":
        return "high" if _failed_login_count(attributes) >= BRUTE_FORCE_THRESHOLD else "medium"
    if alert_family == "network.denied_burst":
        return "high" if _unique_port_count(attributes) >= SCAN_PORT_THRESHOLD else "medium"
    if alert_family == "endpoint.suspicious_connection":
        return "medium" if attributes.get("processName") or attributes.get("protocol") else "low"
    return "medium"


def _recommended_triage_level(incident: dict[str, Any]) -> str:
    current = incident.get("triageLevel")
    if current in {"T1", "T2", "T3"}:
        return current
    severity = str(incident.get("severity") or "").lower()
    if severity in {"critical", "high"}:
        return "T1"
    if severity == "medium":
        return "T2"
    return "T3"


def _recommended_ticket_status(incident: dict[str, Any]) -> str:
    current = incident.get("ticketStatus")
    if current in {"contained", "closed"}:
        return current
    return "investigating"


def _build_evidence(
    alert_family: str,
    incident: dict[str, Any],
    attributes: dict[str, Any],
    entities: dict[str, Any],
) -> list[EvidenceItem]:
    evidence = [
        EvidenceItem(
            id="ev_detection_rule",
            type="event",
            label="Detection rule",
            value=str(incident.get("ruleId") or alert_family),
            severity=_evidence_severity(incident.get("severity")),
            source="siem_kowalski",
        )
    ]

    if alert_family in {"network.scan", "network.denied_burst"}:
        port_count = _unique_port_count(attributes)
        if port_count:
            evidence.append(
                EvidenceItem(
                    id="ev_unique_destination_ports",
                    type="threshold",
                    label="Unique destination ports",
                    value=port_count,
                    threshold={
                        "operator": "gte",
                        "value": SCAN_PORT_THRESHOLD,
                        "windowSeconds": _int_or_none(attributes.get("scanWindowSeconds")),
                    },
                    severity="high" if port_count >= SCAN_PORT_THRESHOLD else "medium",
                    source="siem_kowalski",
                )
            )
        elif attributes.get("count") is not None:
            evidence.append(
                EvidenceItem(
                    id="ev_denied_event_count",
                    type="threshold",
                    label="Denied event count",
                    value=_int_or_none(attributes.get("count")) or 0,
                    threshold={"operator": "gte", "value": 20},
                    severity="medium",
                    source="siem_kowalski",
                )
            )

    if alert_family == "auth.bruteforce":
        evidence.append(
            EvidenceItem(
                id="ev_failed_login_count",
                type="threshold",
                label="Failed login count",
                value=_failed_login_count(attributes),
                threshold={"operator": "gte", "value": BRUTE_FORCE_THRESHOLD},
                severity="high",
                source="siem_kowalski",
            )
        )

    for key, label in (
        ("sourceIp", "Source IP"),
        ("destinationIp", "Destination IP"),
        ("username", "Username"),
        ("hostname", "Hostname"),
        ("endpointId", "Endpoint ID"),
    ):
        value = _first_string(attributes.get(key), entities.get(key))
        if value:
            evidence.append(
                EvidenceItem(
                    id=f"ev_entity_{key}",
                    type="entity",
                    label=label,
                    value=value,
                    severity="informational",
                    source="siem_kowalski",
                )
            )

    return evidence


def _evidence_severity(value: Any) -> str:
    normalized = str(value or "").lower()
    if normalized in {"critical", "high", "medium", "low", "informational"}:
        return normalized
    return "informational"


def _build_entities(
    attributes: dict[str, Any],
    entities: dict[str, Any],
) -> list[TriageEntity]:
    result: list[TriageEntity] = []
    for key, kind, label in (
        ("sourceIp", "ip", "Source IP"),
        ("destinationIp", "ip", "Destination IP"),
        ("username", "user", "Username"),
        ("hostname", "host", "Hostname"),
        ("endpointId", "endpoint", "Endpoint ID"),
        ("integrationId", "provider", "Integration"),
    ):
        value = _first_string(attributes.get(key), entities.get(key))
        if value:
            result.append(
                TriageEntity(
                    id=f"{kind}:{value}",
                    kind=kind,
                    label=label,
                    value=value,
                    source="siem_kowalski",
                )
            )
    return result


def _build_impacted_assets(
    attributes: dict[str, Any],
    entities: dict[str, Any],
) -> list[ImpactedAsset]:
    destination_ip = _first_string(attributes.get("destinationIp"), entities.get("destinationIp"))
    hostname = _first_string(attributes.get("hostname"), entities.get("hostname"))
    endpoint_id = _first_string(attributes.get("endpointId"), entities.get("endpointId"))
    assets: list[ImpactedAsset] = []
    if destination_ip:
        assets.append(
            ImpactedAsset(
                id=f"ip:{destination_ip}",
                kind="ip",
                label="Destination IP",
                value=destination_ip,
            )
        )
    if hostname:
        assets.append(
            ImpactedAsset(id=f"host:{hostname}", kind="host", label="Hostname", value=hostname)
        )
    if endpoint_id:
        assets.append(
            ImpactedAsset(
                id=f"endpoint:{endpoint_id}",
                kind="endpoint",
                label="Endpoint ID",
                value=endpoint_id,
            )
        )
    return assets


def _build_mitre_mappings(
    alert_family: str,
    evidence: list[EvidenceItem],
    attributes: dict[str, Any],
) -> list[MitreMapping]:
    evidence_ids = {item.id for item in evidence}
    if alert_family == "network.scan":
        confidence = "high" if "ev_unique_destination_ports" in evidence_ids else "medium"
        reason = (
            "Unique destination port evidence crossed the scan threshold."
            if confidence == "high"
            else "Network scan rule matched without complete port-count evidence."
        )
        return [
            MitreMapping(
                tacticId="TA0007",
                tacticName="Discovery",
                techniqueId="T1046",
                techniqueName="Network Service Discovery",
                confidence=confidence,
                reason=reason,
                evidenceIds=(
                    ["ev_unique_destination_ports"]
                    if "ev_unique_destination_ports" in evidence_ids
                    else ["ev_detection_rule"]
                ),
            )
        ]
    if alert_family == "network.denied_burst":
        if _unique_port_count(attributes) >= SCAN_PORT_THRESHOLD:
            return [
                MitreMapping(
                    tacticId="TA0007",
                    tacticName="Discovery",
                    techniqueId="T1046",
                    techniqueName="Network Service Discovery",
                    confidence="high",
                    reason="Denied burst also includes unique destination port evidence.",
                    evidenceIds=["ev_unique_destination_ports"],
                )
            ]
        return [
            MitreMapping(
                tacticId="TA0043",
                tacticName="Reconnaissance",
                techniqueId="T1595",
                techniqueName="Active Scanning",
                confidence="medium",
                reason="Denied traffic burst may indicate scanning but can include benign noise.",
                evidenceIds=["ev_denied_event_count"]
                if "ev_denied_event_count" in evidence_ids
                else ["ev_detection_rule"],
            )
        ]
    if alert_family == "auth.bruteforce":
        return [
            MitreMapping(
                tacticId="TA0006",
                tacticName="Credential Access",
                techniqueId="T1110",
                techniqueName="Brute Force",
                confidence=(
                    "high"
                    if _failed_login_count(attributes) >= BRUTE_FORCE_THRESHOLD
                    else "medium"
                ),
                reason="Failed login count crossed the brute-force threshold.",
                evidenceIds=["ev_failed_login_count"],
            )
        ]
    if alert_family == "endpoint.suspicious_connection":
        return [
            MitreMapping(
                tacticId="TA0011",
                tacticName="Command and Control",
                techniqueId="T1071",
                techniqueName="Application Layer Protocol",
                confidence="medium" if attributes.get("protocol") else "low",
                reason=(
                    "Suspicious connection needs process or protocol evidence for "
                    "stronger confidence."
                ),
                evidenceIds=["ev_detection_rule"],
            )
        ]
    if alert_family == "identity.privileged_logon":
        return [
            MitreMapping(
                tacticId="TA0006",
                tacticName="Credential Access",
                techniqueId="T1078",
                techniqueName="Valid Accounts",
                confidence="medium",
                reason=(
                    "Privileged logon from unusual context is suspicious but not "
                    "proof of compromise."
                ),
                evidenceIds=["ev_detection_rule"],
            )
        ]
    return []


def _build_response_candidates(
    *,
    alert_family: str,
    attributes: dict[str, Any],
    entities: dict[str, Any],
) -> tuple[list[ResponseCandidate], list[MissingDataItem]]:
    source_ip = _first_string(attributes.get("sourceIp"), entities.get("sourceIp"))
    destination_ip = _first_string(attributes.get("destinationIp"), entities.get("destinationIp"))
    username = _first_string(attributes.get("username"), entities.get("username"))
    integration_id = _first_string(attributes.get("integrationId"), entities.get("integrationId"))
    candidates = [
        ResponseCandidate(
            id="case.add_note",
            type="case",
            label="Add case note",
            description="Record analyst context on the ticket timeline.",
            riskLevel="low",
            requiresApproval=False,
            availableNow=True,
            reason="Case notes are always available.",
            parameters={},
            mappedMitreTechniqueIds=[],
            playbookTemplateIds=[],
        ),
        ResponseCandidate(
            id="ticket.escalate_tier",
            type="ticket",
            label="Escalate ticket tier",
            description="Move the ticket to a stricter triage tier.",
            riskLevel="low",
            requiresApproval=False,
            availableNow=True,
            reason="Ticket triage updates are available in FortiDashboard.",
            parameters={},
            mappedMitreTechniqueIds=[],
            playbookTemplateIds=[],
        ),
    ]
    if source_ip or destination_ip or username:
        candidates.append(
            ResponseCandidate(
                id="entity.add_watchlist",
                type="case",
                label="Add entity watchlist note",
                description="Track the entity for analyst follow-up.",
                riskLevel="low",
                requiresApproval=False,
                availableNow=True,
                reason="At least one source, target or user entity is present.",
                parameters={
                    "sourceIp": source_ip,
                    "destinationIp": destination_ip,
                    "username": username,
                },
                mappedMitreTechniqueIds=[],
                playbookTemplateIds=[],
            )
        )

    missing_data: list[MissingDataItem] = []
    if alert_family in {"network.scan", "network.denied_burst", "auth.bruteforce"}:
        candidates.extend(
            _fortigate_candidates(
                alert_family=alert_family,
                source_ip=source_ip,
                destination_ip=destination_ip,
                integration_id=integration_id,
            )
        )

    if alert_family == "auth.bruteforce":
        candidates.append(
            ResponseCandidate(
                id="identity.review_account",
                type="identity",
                label="Review account",
                description="Review account activity and ownership before account action.",
                riskLevel="low",
                requiresApproval=False,
                availableNow=bool(username),
                reason="Username evidence exists." if username else "Username evidence is missing.",
                parameters={"username": username},
                mappedMitreTechniqueIds=["T1110"],
                playbookTemplateIds=["pb_auth_bruteforce_triage"],
            )
        )
        unavailable_reason = "No identity provider connector is available."
        candidates.append(
            ResponseCandidate(
                id="identity.lock_user",
                type="identity",
                label="Lock user",
                description="Temporarily lock the user account through an identity provider.",
                riskLevel="high",
                requiresApproval=True,
                availableNow=False,
                providerRequired="identity",
                reason=unavailable_reason,
                parameters={"username": username},
                mappedMitreTechniqueIds=["T1110"],
                playbookTemplateIds=["pb_auth_bruteforce_triage"],
            )
        )
        candidates.append(
            ResponseCandidate(
                id="identity.force_password_reset",
                type="identity",
                label="Force password reset",
                description="Force password reset through an identity provider.",
                riskLevel="high",
                requiresApproval=True,
                availableNow=False,
                providerRequired="identity",
                reason=unavailable_reason,
                parameters={"username": username},
                mappedMitreTechniqueIds=["T1110"],
                playbookTemplateIds=["pb_auth_bruteforce_triage"],
            )
        )
        missing_data.append(
            MissingDataItem(
                id="missing_identity_provider",
                label="Identity provider connector",
                reason="Required for account lockout or password reset actions.",
            )
        )

    return candidates, missing_data


def _fortigate_candidates(
    *,
    alert_family: str,
    source_ip: str,
    destination_ip: str,
    integration_id: str,
) -> list[ResponseCandidate]:
    templates = (
        ["pb_network_scan_triage", "pb_fortigate_temp_block"]
        if alert_family in {"network.scan", "network.denied_burst"}
        else ["pb_auth_bruteforce_triage", "pb_fortigate_temp_block"]
    )
    candidates = [
        ResponseCandidate(
            id="fortigate.temporary_source_block",
            type="fortigate",
            label="Temporarily block source",
            description="Create a FortiDashboard-owned temporary source block after approval.",
            riskLevel="high",
            requiresApproval=True,
            availableNow=bool(integration_id and source_ip),
            providerRequired="fortigate",
            reason=(
                "FortiGate integration and source IP are present."
                if integration_id and source_ip
                else "Requires FortiGate integration and source IP evidence."
            ),
            parameters={"integrationId": integration_id, "sourceIp": source_ip},
            mappedMitreTechniqueIds=["T1046"] if alert_family != "auth.bruteforce" else ["T1110"],
            playbookTemplateIds=templates,
        )
    ]
    if alert_family in {"network.scan", "network.denied_burst"}:
        candidates.append(
            ResponseCandidate(
                id="fortigate.temporary_source_destination_block",
                type="fortigate",
                label="Temporarily block source to target",
                description=(
                    "Create a FortiDashboard-owned temporary block scoped to the "
                    "observed source and destination after approval."
                ),
                riskLevel="high",
                requiresApproval=True,
                availableNow=bool(integration_id and source_ip and destination_ip),
                providerRequired="fortigate",
                reason=(
                    "FortiGate integration, source IP and destination IP are present."
                    if integration_id and source_ip and destination_ip
                    else "Requires FortiGate integration, source IP and destination IP."
                ),
                parameters={
                    "integrationId": integration_id,
                    "sourceIp": source_ip,
                    "destinationIp": destination_ip,
                },
                mappedMitreTechniqueIds=["T1046"],
                playbookTemplateIds=templates,
            )
        )
    candidates.append(
        ResponseCandidate(
            id="fortigate.policy_review_only",
            type="fortigate",
            label="Review firewall policy",
            description="Create review guidance when live policy changes are not safe.",
            riskLevel="medium",
            requiresApproval=False,
            availableNow=True,
            providerRequired="fortigate",
            reason="Policy review guidance is safe even when live apply is unavailable.",
            parameters={"integrationId": integration_id},
            mappedMitreTechniqueIds=[],
            playbookTemplateIds=[],
        )
    )
    return candidates


def _build_playbook_templates(
    *,
    alert_family: str,
    response_candidates: list[ResponseCandidate],
    attributes: dict[str, Any],
    entities: dict[str, Any],
) -> list[PlaybookTemplateRecommendation]:
    available_candidate_ids = {
        candidate.id for candidate in response_candidates if candidate.available_now
    }
    source_ip = _first_string(attributes.get("sourceIp"), entities.get("sourceIp"))
    destination_ip = _first_string(attributes.get("destinationIp"), entities.get("destinationIp"))
    integration_id = _first_string(attributes.get("integrationId"), entities.get("integrationId"))
    if alert_family in {"network.scan", "network.denied_burst"}:
        required = (
            ["fortigate.temporary_source_destination_block"]
            if "fortigate.temporary_source_destination_block" in available_candidate_ids
            else ["case.add_note"]
        )
        return [
            PlaybookTemplateRecommendation(
                templateId="pb_network_scan_triage",
                label="Network scan triage",
                reason="Network scan evidence is present and maps to service discovery.",
                confidence=_confidence(alert_family, attributes),
                requiredCandidateIds=required,
                parameters={
                    "sourceIp": source_ip,
                    "destinationIp": destination_ip,
                    "integrationId": integration_id,
                    "destinationPorts": attributes.get("destinationPorts") or [],
                },
                requiresApproval="fortigate.temporary_source_destination_block" in required,
            ),
            PlaybookTemplateRecommendation(
                templateId="pb_fortigate_temp_block",
                label="FortiGate temporary block",
                reason="A scoped FortiGate response can contain scan traffic after approval.",
                confidence="medium",
                requiredCandidateIds=required,
                parameters={
                    "sourceIp": source_ip,
                    "destinationIp": destination_ip,
                    "integrationId": integration_id,
                },
                requiresApproval=True,
            ),
        ]
    if alert_family == "auth.bruteforce":
        return [
            PlaybookTemplateRecommendation(
                templateId="pb_auth_bruteforce_triage",
                label="Authentication brute-force triage",
                reason="Failed-login threshold evidence is present.",
                confidence=_confidence(alert_family, attributes),
                requiredCandidateIds=["identity.review_account"],
                parameters={
                    "sourceIp": source_ip,
                    "username": _first_string(attributes.get("username"), entities.get("username")),
                    "failedLoginCount": _failed_login_count(attributes),
                    "integrationId": integration_id,
                },
                requiresApproval=False,
            )
        ]
    if alert_family == "endpoint.suspicious_connection":
        return [
            PlaybookTemplateRecommendation(
                templateId="pb_endpoint_connection_triage",
                label="Endpoint connection triage",
                reason="Endpoint network telemetry needs endpoint context review.",
                confidence=_confidence(alert_family, attributes),
                requiredCandidateIds=["case.add_note"],
                parameters={},
                requiresApproval=False,
            )
        ]
    if alert_family == "fortigate.resource_pressure":
        return [
            PlaybookTemplateRecommendation(
                templateId="pb_resource_pressure_review",
                label="Resource pressure review",
                reason="Operational resource pressure should be reviewed before security response.",
                confidence="medium",
                requiredCandidateIds=["case.add_note"],
                parameters={},
                requiresApproval=False,
            )
        ]
    return []


def _unique_port_count(attributes: dict[str, Any]) -> int:
    count = _int_or_none(attributes.get("uniqueDestinationPortCount"))
    if count is not None:
        return count
    ports = attributes.get("destinationPorts")
    if isinstance(ports, list):
        return len({port for port in ports if isinstance(port, int | str)})
    return 0


def _failed_login_count(attributes: dict[str, Any]) -> int:
    count = _int_or_none(attributes.get("count"))
    if count is not None:
        return count
    detection = attributes.get("detection")
    if isinstance(detection, dict):
        observed = _int_or_none(detection.get("observedCount"))
        if observed is not None:
            return observed
    return 0


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _first_string(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int | float) and not isinstance(value, bool):
            return str(value)
    return ""
