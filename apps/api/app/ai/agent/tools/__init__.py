"""Built-in read-only tools registered with the agent.

Importing this module triggers registration via the side-effecting
`register_tool(...)` calls in each tool file.
"""

from app.ai.agent.tools import (
    audit_tool,
    incidents,
    integrations,
    playbook_runs,
    widgets,
    workspace,
    xdr_endpoints,
)

__all__ = [
    "audit_tool",
    "incidents",
    "integrations",
    "playbook_runs",
    "widgets",
    "workspace",
    "xdr_endpoints",
]
