from app.integrations.fortigate.policy_models import (
    FortiGatePolicyIntent,
    FortiGatePolicyPreflightRequest,
    FortiGatePolicyScope,
)
from app.integrations.fortigate.policy_orchestrator import (
    FortiGatePolicyOrchestrator,
    host_subnet,
    normalize_address_name,
)


class FakePolicyClient:
    def __init__(
        self,
        *,
        policies: list[dict] | None = None,
        address_objects: list[dict] | None = None,
    ) -> None:
        self.policies = policies or []
        self.address_objects = address_objects or []
        self.created_addresses: list[dict] = []
        self.created_policies: list[dict] = []

    def get_policies(self) -> list[dict]:
        return self.policies

    def get_address_objects(self) -> list[dict]:
        return self.address_objects

    def create_address_object(self, *, name: str, subnet: str, comment: str) -> dict:
        payload = {"name": name, "subnet": subnet, "comment": comment}
        self.created_addresses.append(payload)
        return {"status": "success", "mkey": name}

    def create_firewall_policy(self, payload: dict) -> dict:
        self.created_policies.append(payload)
        return {"status": "success", "mkey": payload["name"]}


def test_policy_orchestrator_normalizes_ipv4_address_objects():
    assert normalize_address_name("192.0.2.50") == "FD_ADDR_192_0_2_50"
    assert host_subnet("192.0.2.50") == "192.0.2.50 255.255.255.255"


def test_policy_orchestrator_plans_lab_allow_log_policy():
    client = FakePolicyClient()
    orchestrator = FortiGatePolicyOrchestrator(client, integration_id="int_fgt_lab")

    preflight = orchestrator.preflight(
        FortiGatePolicyPreflightRequest(
            intent=FortiGatePolicyIntent.LAB_ALLOW_LOG,
            scope=FortiGatePolicyScope.SOURCE_DESTINATION_SERVICE,
            source_interface="port2",
            destination_interface="port3",
            source_ip="192.0.2.50",
            destination_ip="198.51.100.10",
            service="TCP_443",
        )
    )

    assert preflight.proposed_policy_name.startswith("FD_LAB_ALLOW_")
    assert preflight.integration_id == "int_fgt_lab"
    assert len(preflight.proposed_policy_name) <= 35
    assert preflight.existing_policy_count == 0
    assert preflight.owned_policy_count == 0
    assert [change.object_type for change in preflight.changes] == [
        "firewall.address",
        "firewall.address",
        "firewall.policy",
    ]
    policy = preflight.changes[-1].payload
    assert policy["name"] == preflight.proposed_policy_name
    assert len(policy["name"]) <= 35
    assert policy["action"] == "accept"
    assert policy["logtraffic"] == "all"
    assert policy["srcintf"] == [{"name": "port2"}]
    assert policy["dstintf"] == [{"name": "port3"}]
    assert policy["srcaddr"] == [{"name": "FD_ADDR_192_0_2_50"}]
    assert policy["dstaddr"] == [{"name": "FD_ADDR_198_51_100_10"}]
    assert policy["service"] == [{"name": "TCP_443"}]


def test_policy_orchestrator_plans_source_only_temporary_block():
    client = FakePolicyClient(
        policies=[{"name": "FD_LAB_ALLOW_SCAN", "policyid": 10}],
        address_objects=[{"name": "FD_ADDR_192_0_2_50"}],
    )
    orchestrator = FortiGatePolicyOrchestrator(client, integration_id="int_fgt_lab")

    preflight = orchestrator.preflight(
        FortiGatePolicyPreflightRequest(
            intent=FortiGatePolicyIntent.TEMPORARY_BLOCK,
            scope=FortiGatePolicyScope.SOURCE_ONLY,
            source_interface="port2",
            destination_interface="port3",
            source_ip="192.0.2.50",
            duration_minutes=30,
            incident_id="inc_123",
            playbook_run_id="run_123",
        )
    )

    assert preflight.proposed_policy_name.startswith("FD_TMP_BLOCK_")
    assert len(preflight.proposed_policy_name) <= 35
    assert preflight.owned_policy_count == 1
    assert preflight.changes[0].operation == "reuse"
    policy = preflight.changes[-1].payload
    assert policy["action"] == "deny"
    assert policy["dstaddr"] == [{"name": "all"}]
    assert policy["service"] == [{"name": "ALL"}]
    assert policy["logtraffic"] == "all"
    assert preflight.placement == "before first FortiDashboard-owned lab allow/log policy"


def test_policy_orchestrator_generates_short_distinct_policy_names():
    client = FakePolicyClient()
    orchestrator = FortiGatePolicyOrchestrator(client, integration_id="int_fgt_lab")

    https_preflight = orchestrator.preflight(
        FortiGatePolicyPreflightRequest(
            intent=FortiGatePolicyIntent.LAB_ALLOW_LOG,
            scope=FortiGatePolicyScope.SOURCE_DESTINATION_SERVICE,
            source_interface="port2",
            destination_interface="port3",
            source_ip="192.0.2.10",
            destination_ip="198.51.100.20",
            service="HTTPS",
        )
    )
    ssh_preflight = orchestrator.preflight(
        FortiGatePolicyPreflightRequest(
            intent=FortiGatePolicyIntent.LAB_ALLOW_LOG,
            scope=FortiGatePolicyScope.SOURCE_DESTINATION_SERVICE,
            source_interface="port2",
            destination_interface="port3",
            source_ip="192.0.2.10",
            destination_ip="198.51.100.20",
            service="SSH",
        )
    )

    assert https_preflight.proposed_policy_name.startswith("FD_LAB_ALLOW_")
    assert ssh_preflight.proposed_policy_name.startswith("FD_LAB_ALLOW_")
    assert len(https_preflight.proposed_policy_name) <= 35
    assert len(ssh_preflight.proposed_policy_name) <= 35
    assert https_preflight.proposed_policy_name != ssh_preflight.proposed_policy_name


def test_policy_orchestrator_review_hash_is_stable():
    client = FakePolicyClient()
    orchestrator = FortiGatePolicyOrchestrator(client, integration_id="int_fgt_lab")
    request = FortiGatePolicyPreflightRequest(
        intent=FortiGatePolicyIntent.TEMPORARY_BLOCK,
        scope=FortiGatePolicyScope.SOURCE_DESTINATION,
        source_interface="port2",
        destination_interface="port3",
        source_ip="192.0.2.50",
        destination_ip="198.51.100.10",
        duration_minutes=30,
    )

    first = orchestrator.preflight(request)
    second = orchestrator.preflight(request)

    assert first.review_hash == second.review_hash
    assert len(first.review_hash) == 64


def test_policy_orchestrator_applies_planned_changes_in_order():
    client = FakePolicyClient()
    orchestrator = FortiGatePolicyOrchestrator(client, integration_id="int_fgt_lab")
    preflight = orchestrator.preflight(
        FortiGatePolicyPreflightRequest(
            intent=FortiGatePolicyIntent.TEMPORARY_BLOCK,
            scope=FortiGatePolicyScope.SOURCE_DESTINATION,
            source_interface="port2",
            destination_interface="port3",
            source_ip="192.0.2.50",
            destination_ip="198.51.100.10",
            duration_minutes=30,
        )
    )

    applied = orchestrator.apply_changes(preflight.changes)

    assert [item["objectType"] for item in applied] == [
        "firewall.address",
        "firewall.address",
        "firewall.policy",
    ]
    assert [item["name"] for item in applied] == [
        "FD_ADDR_192_0_2_50",
        "FD_ADDR_198_51_100_10",
        preflight.proposed_policy_name,
    ]
    assert len(client.created_addresses) == 2
    assert client.created_policies[0]["action"] == "deny"
