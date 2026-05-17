from app.models import NodeTypeDefinition

SENSITIVE_NODE_TYPES = {
    "fortigate.recommend_block",
    "fortigate.temporary_block",
    "fortiweb.recommend_block",
}
APPROVAL_NODE_TYPES = {"approval.required"}


def node_type_definitions() -> list[NodeTypeDefinition]:
    return [
        NodeTypeDefinition(
            id="trigger.incident_created",
            label="Incident Created",
            category="trigger",
            boundary="trigger_only",
            config_schema={"type": "object", "properties": {}},
        ),
        NodeTypeDefinition(
            id="condition.severity",
            label="Severity Condition",
            category="condition",
            boundary="decision_only",
            config_schema={
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "array",
                        "items": {"enum": ["low", "medium", "high", "critical"]},
                    }
                },
                "required": ["severity"],
            },
        ),
        NodeTypeDefinition(
            id="enrich.ip",
            label="Enrich IP",
            category="enrichment",
            boundary="enrichment_read_only",
            config_schema={
                "type": "object",
                "properties": {"field": {"type": "string"}},
                "required": ["field"],
            },
        ),
        NodeTypeDefinition(
            id="case.note",
            label="Create Case Note",
            category="action",
            boundary="case_note",
            config_schema={
                "type": "object",
                "properties": {"template": {"type": "string"}},
                "required": ["template"],
            },
        ),
        NodeTypeDefinition(
            id="audit.note",
            label="Write Audit Note",
            category="action",
            boundary="case_note",
            config_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        ),
        NodeTypeDefinition(
            id="approval.required",
            label="Require Approval",
            category="control",
            boundary="approval_gate",
            config_schema={
                "type": "object",
                "properties": {"role": {"type": "string", "default": "admin"}},
            },
        ),
        NodeTypeDefinition(
            id="notify.webhook",
            label="Notify Webhook",
            category="action",
            boundary="notification_dry_run",
            config_schema={
                "type": "object",
                "properties": {
                    "mode": {"enum": ["dry_run"]},
                    "channel": {"type": "string"},
                },
            },
        ),
        NodeTypeDefinition(
            id="fortigate.recommend_block",
            label="Recommend FortiGate Block",
            category="action",
            sensitive=True,
            boundary="recommendation_only",
            config_schema={
                "type": "object",
                "properties": {
                    "mode": {"enum": ["dry_run"]},
                    "field": {"type": "string"},
                },
                "required": ["field"],
            },
        ),
        NodeTypeDefinition(
            id="fortiweb.recommend_block",
            label="Recommend FortiWeb Block",
            category="action",
            sensitive=True,
            boundary="recommendation_only",
            config_schema={
                "type": "object",
                "properties": {
                    "sourceIp": {"type": "string"},
                    "durationMinutes": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 60,
                    },
                },
                "required": ["sourceIp"],
            },
        ),
        NodeTypeDefinition(
            id="fortigate.temporary_block",
            label="FortiGate Temporary Block",
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
                        "enum": [
                            "source_only",
                            "source_destination",
                            "source_destination_service",
                        ],
                    },
                    "durationMinutes": {
                        "type": "integer",
                        "minimum": 5,
                        "maximum": 1440,
                    },
                    "sourceField": {"type": "string"},
                    "destinationField": {"type": "string"},
                    "serviceField": {"type": "string"},
                },
                "required": ["scope", "durationMinutes", "sourceField"],
            },
        ),
        NodeTypeDefinition(
            id="webhook.dry_run",
            label="Webhook Dry Run",
            category="action",
            boundary="webhook_dry_run",
            config_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "method": {"enum": ["POST"]},
                },
            },
        ),
    ]
