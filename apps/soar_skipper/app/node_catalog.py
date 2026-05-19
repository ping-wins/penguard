from app.models import NodeTypeDefinition

SENSITIVE_NODE_TYPES = {
    "fortigate.recommend_block",
    "fortigate.temporary_block",
    "fortiweb.recommend_block",
}
APPROVAL_NODE_TYPES = {"approval.required"}


def _input(key: str, label: str, description: str) -> dict[str, str]:
    return {"key": key, "label": label, "description": description}


def node_type_definitions() -> list[NodeTypeDefinition]:
    return [
        NodeTypeDefinition(
            id="trigger.incident_created",
            label="Incident Created",
            description="Starts a run from a SOC incident.",
            effectSummary="Receives incident context and passes it to the next node.",
            category="trigger",
            boundary="trigger_only",
            config_schema={"type": "object", "properties": {}},
            exampleConfig={},
        ),
        NodeTypeDefinition(
            id="condition.severity",
            label="Severity Condition",
            description=(
                "Continues only when the incident severity matches one of the "
                "selected values."
            ),
            effectSummary="Routes or stops execution based on incident severity.",
            category="condition",
            boundary="decision_only",
            config_schema={
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "array",
                        "title": "Allowed severities",
                        "description": (
                            "Incident severities that should continue through "
                            "this condition."
                        ),
                        "items": {"enum": ["low", "medium", "high", "critical"]},
                    }
                },
                "required": ["severity"],
            },
            exampleConfig={"severity": ["high", "critical"]},
            requiredInputs=[
                _input(
                    "severity",
                    "Allowed severities",
                    "The severity values allowed to continue.",
                ),
            ],
        ),
        NodeTypeDefinition(
            id="enrich.ip",
            label="Enrich IP",
            description=(
                "Reads an IP-like value from the incident payload and exposes "
                "it to later nodes."
            ),
            effectSummary="Resolves a field such as entities.sourceIp from the incident.",
            category="enrichment",
            boundary="enrichment_read_only",
            config_schema={
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "title": "Incident field",
                        "description": "Dot path to the incident value to extract.",
                    }
                },
                "required": ["field"],
            },
            exampleConfig={"field": "entities.sourceIp"},
            requiredInputs=[
                _input("field", "Incident field", "Dot path such as entities.sourceIp."),
            ],
        ),
        NodeTypeDefinition(
            id="case.note",
            label="Create Case Note",
            description="Adds a rendered note to the SIEM incident timeline.",
            effectSummary="Writes a real case note through the SIEM gateway.",
            category="action",
            boundary="case_note",
            config_schema={
                "type": "object",
                "properties": {
                    "template": {
                        "type": "string",
                        "title": "Note template",
                        "description": (
                            "Text stored on the incident; placeholders like "
                            "{incident.id} are supported."
                        ),
                    }
                },
                "required": ["template"],
            },
            exampleConfig={"template": "Investigate {incident.id} from {entities.sourceIp}."},
            requiredInputs=[
                _input("template", "Note template", "Timeline note to write to the incident."),
            ],
        ),
        NodeTypeDefinition(
            id="audit.note",
            label="Write Audit Note",
            description="Records a Penguard audit event from the playbook run.",
            effectSummary="Writes a real audit log entry for traceability.",
            category="action",
            boundary="case_note",
            config_schema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "title": "Audit message",
                        "description": "Message saved in the audit event details.",
                    }
                },
                "required": ["message"],
            },
            exampleConfig={"message": "Playbook reviewed incident {incident.id}."},
            requiredInputs=[
                _input("message", "Audit message", "Message to record in the audit log."),
            ],
        ),
        NodeTypeDefinition(
            id="approval.required",
            label="Require Approval",
            description=(
                "Pauses the run until an authorized user approves the next "
                "sensitive action."
            ),
            effectSummary="Creates an approval gate and prevents silent live response.",
            category="control",
            boundary="approval_gate",
            config_schema={
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "title": "Approver role",
                        "description": "Role expected to approve the run.",
                        "default": "admin",
                    }
                },
            },
            exampleConfig={"role": "admin"},
        ),
        NodeTypeDefinition(
            id="notify.webhook",
            label="Notify Webhook",
            category="action",
            description=(
                "Sends a notification to a configured outbound webhook "
                "destination such as Discord."
            ),
            effectSummary=(
                "Sends a real outbound notification through a configured "
                "webhook destination."
            ),
            boundary="notification_dry_run",
            config_schema={
                "type": "object",
                "properties": {
                    "destinationId": {
                        "type": "string",
                        "title": "Webhook destination",
                        "description": (
                            "Configured destination ID; the secret URL stays "
                            "server-side."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "title": "Message content",
                        "description": (
                            "Message sent to the webhook. Discord receives "
                            "this as content."
                        ),
                    },
                    "username": {
                        "type": "string",
                        "title": "Display username",
                        "description": "Optional sender name supported by Discord webhooks.",
                    },
                },
                "required": ["destinationId", "content"],
            },
            exampleConfig={
                "destinationId": "pwd_discord_soc",
                "content": "Critical incident {incident.id} from {entities.sourceIp}",
            },
            requiredInputs=[
                _input(
                    "destinationId",
                    "Webhook destination",
                    "A configured Discord or generic webhook destination.",
                ),
                _input("content", "Message content", "Message body sent to the destination."),
            ],
        ),
        NodeTypeDefinition(
            id="fortigate.recommend_block",
            label="Recommend FortiGate Block",
            description=(
                "Creates an analyst-facing FortiGate block recommendation "
                "without applying it."
            ),
            effectSummary="Produces a governed FortiGate policy review requirement.",
            category="action",
            sensitive=True,
            boundary="recommendation_only",
            config_schema={
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "title": "Source field",
                        "description": "Incident field containing the source to block.",
                    },
                },
                "required": ["field"],
            },
            exampleConfig={"field": "entities.sourceIp"},
            requiredInputs=[
                _input("field", "Source field", "Incident field containing the source to review."),
            ],
        ),
        NodeTypeDefinition(
            id="fortiweb.recommend_block",
            label="Recommend FortiWeb Block",
            description=(
                "Creates an analyst-facing FortiWeb source-block "
                "recommendation without applying it."
            ),
            effectSummary="Produces a governed FortiWeb policy review requirement.",
            category="action",
            sensitive=True,
            boundary="recommendation_only",
            config_schema={
                "type": "object",
                "properties": {
                    "sourceIp": {
                        "type": "string",
                        "title": "Source IP",
                        "description": "Source IP address to review for FortiWeb blocking.",
                    },
                    "durationMinutes": {
                        "type": "integer",
                        "title": "Duration",
                        "description": "How long the proposed block should remain active.",
                        "minimum": 1,
                        "default": 60,
                    },
                },
                "required": ["sourceIp"],
            },
            exampleConfig={"sourceIp": "{entities.sourceIp}", "durationMinutes": 60},
            requiredInputs=[
                _input("sourceIp", "Source IP", "Source IP address or placeholder to review."),
            ],
        ),
        NodeTypeDefinition(
            id="fortigate.temporary_block",
            label="FortiGate Temporary Block",
            description=(
                "Requests a temporary FortiGate block through the governed "
                "policy workflow."
            ),
            effectSummary="Pauses for approval and then uses Penguard-owned policy orchestration.",
            category="action",
            sensitive=True,
            dryRunOnly=False,
            executionMode="approval_required",
            liveAvailable=True,
            boundary="fortigate_policy_orchestration",
            config_schema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "title": "Block scope",
                        "description": "How specific the temporary block should be.",
                        "enum": [
                            "source_only",
                            "source_destination",
                            "source_destination_service",
                        ],
                    },
                    "durationMinutes": {
                        "type": "integer",
                        "title": "Duration",
                        "description": "Temporary block duration in minutes.",
                        "minimum": 5,
                        "maximum": 1440,
                    },
                    "sourceField": {
                        "type": "string",
                        "title": "Source field",
                        "description": "Incident field containing the source IP.",
                    },
                    "destinationField": {
                        "type": "string",
                        "title": "Destination field",
                        "description": "Incident field containing the destination IP.",
                    },
                    "serviceField": {
                        "type": "string",
                        "title": "Service field",
                        "description": "Incident field containing the service or port.",
                    },
                },
                "required": ["scope", "durationMinutes", "sourceField"],
            },
            exampleConfig={
                "scope": "source_only",
                "durationMinutes": 30,
                "sourceField": "entities.sourceIp",
            },
            requiredInputs=[
                _input("scope", "Block scope", "Specificity of the temporary block."),
                _input("durationMinutes", "Duration", "Temporary block duration in minutes."),
                _input("sourceField", "Source field", "Incident field containing the source IP."),
            ],
        ),
        NodeTypeDefinition(
            id="webhook.dry_run",
            label="Webhook Dry Run",
            description="Validates the shape of an outbound webhook call without sending it.",
            effectSummary="Records a dry-run webhook effect and does not call the URL.",
            category="action",
            boundary="webhook_dry_run",
            config_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "title": "Webhook URL",
                        "description": "URL shown only for dry-run validation.",
                    },
                    "method": {
                        "title": "HTTP method",
                        "description": "Dry-run method. Only POST is currently supported.",
                        "enum": ["POST"],
                    },
                },
                "required": ["url", "method"],
            },
            exampleConfig={"url": "https://example.invalid/webhook", "method": "POST"},
            requiredInputs=[
                _input("url", "Webhook URL", "Dry-run URL to validate."),
                _input("method", "HTTP method", "Only POST is currently supported."),
            ],
        ),
    ]
