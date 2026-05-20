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
        self.updated_policies: list[dict] = []
        self.moved_policies: list[dict] = []

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
        policy_id = 42 + len(self.created_policies) - 1
        self.policies.append({"name": payload["name"], "policyid": policy_id})
        return {"status": "success", "mkey": policy_id}

    def move_firewall_policy(
        self,
        policy_id: str,
        *,
        before: str | None = None,
        after: str | None = None,
    ) -> dict:
        payload = {"policyId": policy_id, "before": before, "after": after}
        self.moved_policies.append(payload)
        return {"status": "success", **payload}

    def update_firewall_policy(self, policy_id: str, payload: dict) -> dict:
        item = {"policyId": policy_id, "payload": payload}
        self.updated_policies.append(item)
        return {"status": "success", **item}


def test_policy_orchestrator_normalizes_ipv4_address_objects():
    assert normalize_address_name("192.0.2.50") == "PG_ADDR_192_0_2_50"
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

    assert preflight.proposed_policy_name.startswith("PG_LAB_ALLOW_")
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
    assert policy["srcaddr"] == [{"name": "PG_ADDR_192_0_2_50"}]
    assert policy["dstaddr"] == [{"name": "PG_ADDR_198_51_100_10"}]
    assert policy["service"] == [{"name": "TCP_443"}]


def test_policy_orchestrator_plans_source_only_temporary_block():
    client = FakePolicyClient(
        policies=[{"name": "PG_LAB_ALLOW_SCAN", "policyid": 10}],
        address_objects=[{"name": "PG_ADDR_192_0_2_50"}],
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

    assert preflight.proposed_policy_name.startswith("PG_TMP_BLOCK_")
    assert len(preflight.proposed_policy_name) <= 35
    assert preflight.owned_policy_count == 1
    assert preflight.changes[0].operation == "reuse"
    policy = preflight.changes[-1].payload
    assert policy["action"] == "deny"
    assert policy["dstaddr"] == [{"name": "all"}]
    assert policy["service"] == [{"name": "ALL"}]
    assert policy["logtraffic"] == "all"
    assert preflight.placement == "before first Penguard-owned lab allow/log policy"


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

    assert https_preflight.proposed_policy_name.startswith("PG_LAB_ALLOW_")
    assert ssh_preflight.proposed_policy_name.startswith("PG_LAB_ALLOW_")
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
        "PG_ADDR_192_0_2_50",
        "PG_ADDR_198_51_100_10",
        preflight.proposed_policy_name,
    ]
    assert len(client.created_addresses) == 2
    assert client.created_policies[0]["action"] == "deny"


def test_policy_orchestrator_moves_temporary_block_before_owned_lab_allow_policy():
    client = FakePolicyClient(
        policies=[{"name": "PG_LAB_ALLOW_SCAN", "policyid": 10}],
    )
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

    orchestrator.apply_changes(preflight.changes)

    assert client.moved_policies == [
        {"policyId": "42", "before": "10", "after": None}
    ]


def test_policy_orchestrator_moves_temporary_block_before_legacy_fortidashboard_lab_allow_policy():
    client = FakePolicyClient(
        policies=[{"name": "FD_LAB_ALLOW_32FD0707AD9A", "policyid": 1}],
    )
    orchestrator = FortiGatePolicyOrchestrator(client, integration_id="int_fgt_lab")
    preflight = orchestrator.preflight(
        FortiGatePolicyPreflightRequest(
            intent=FortiGatePolicyIntent.TEMPORARY_BLOCK,
            scope=FortiGatePolicyScope.SOURCE_DESTINATION,
            source_interface="port2",
            destination_interface="port3",
            source_ip="10.10.10.10",
            destination_ip="10.10.20.10",
            duration_minutes=30,
        )
    )

    orchestrator.apply_changes(preflight.changes)

    assert preflight.owned_policy_count == 1
    assert preflight.placement == "before first Penguard-owned lab allow/log policy"
    assert preflight.warnings == []
    assert client.moved_policies == [
        {"policyId": "42", "before": "1", "after": None}
    ]


def test_policy_orchestrator_uses_all_services_for_source_destination_block():
    client = FakePolicyClient()
    orchestrator = FortiGatePolicyOrchestrator(client, integration_id="int_fgt_lab")

    preflight = orchestrator.preflight(
        FortiGatePolicyPreflightRequest(
            intent=FortiGatePolicyIntent.TEMPORARY_BLOCK,
            scope=FortiGatePolicyScope.SOURCE_DESTINATION,
            source_interface="port2",
            destination_interface="port3",
            source_ip="10.10.10.10",
            destination_ip="10.10.20.10",
            service="tcp/24014",
            duration_minutes=30,
        )
    )

    assert preflight.changes[-1].payload["service"] == [{"name": "ALL"}]


def test_policy_orchestrator_keeps_service_for_source_destination_service_block():
    client = FakePolicyClient()
    orchestrator = FortiGatePolicyOrchestrator(client, integration_id="int_fgt_lab")

    preflight = orchestrator.preflight(
        FortiGatePolicyPreflightRequest(
            intent=FortiGatePolicyIntent.TEMPORARY_BLOCK,
            scope=FortiGatePolicyScope.SOURCE_DESTINATION_SERVICE,
            source_interface="port2",
            destination_interface="port3",
            source_ip="10.10.10.10",
            destination_ip="10.10.20.10",
            service="tcp/24014",
            duration_minutes=30,
        )
    )

    assert preflight.changes[-1].payload["service"] == [{"name": "tcp/24014"}]


def test_policy_orchestrator_updates_matching_legacy_lab_allow_for_temporary_block():
    client = FakePolicyClient(
        policies=[
            {
                "name": "FD_LAB_ALLOW_32FD0707AD9A",
                "policyid": 1,
                "srcintf": [{"name": "port2"}],
                "dstintf": [{"name": "port3"}],
                "srcaddr": [{"name": "FD_ADDR_10_10_10_10"}],
                "dstaddr": [{"name": "FD_ADDR_10_10_20_10"}],
                "action": "accept",
                "service": [{"name": "ALL"}],
            }
        ],
        address_objects=[
            {"name": "FD_ADDR_10_10_10_10", "subnet": "10.10.10.10 255.255.255.255"},
            {"name": "FD_ADDR_10_10_20_10", "subnet": "10.10.20.10 255.255.255.255"},
        ],
    )
    orchestrator = FortiGatePolicyOrchestrator(client, integration_id="int_fgt_lab")

    preflight = orchestrator.preflight(
        FortiGatePolicyPreflightRequest(
            intent=FortiGatePolicyIntent.TEMPORARY_BLOCK,
            scope=FortiGatePolicyScope.SOURCE_DESTINATION,
            source_interface="port2",
            destination_interface="port3",
            source_ip="10.10.10.10",
            destination_ip="10.10.20.10",
            service="tcp/24014",
            duration_minutes=30,
        )
    )
    applied = orchestrator.apply_changes(preflight.changes)

    assert [change.operation for change in preflight.changes] == ["update"]
    assert preflight.changes[0].object_type == "firewall.policy"
    assert preflight.changes[0].name == "FD_LAB_ALLOW_32FD0707AD9A"
    assert preflight.changes[0].payload["policyid"] == "1"
    assert preflight.changes[0].payload["action"] == "deny"
    assert preflight.changes[0].payload["service"] == [{"name": "ALL"}]
    assert client.created_addresses == []
    assert client.created_policies == []
    assert client.updated_policies == [
        {
            "policyId": "1",
            "payload": {
                "action": "deny",
                "service": [{"name": "ALL"}],
                "logtraffic": "all",
                "status": "enable",
                "comments": "Penguard owned temporary block policy",
            },
        }
    ]
    assert applied == [
        {
            "operation": "update",
            "objectType": "firewall.policy",
            "name": "FD_LAB_ALLOW_32FD0707AD9A",
            "result": {
                "status": "success",
                "policyId": "1",
                "payload": {
                    "action": "deny",
                    "service": [{"name": "ALL"}],
                    "logtraffic": "all",
                    "status": "enable",
                    "comments": "Penguard owned temporary block policy",
                },
            },
        }
    ]


def test_policy_orchestrator_updates_matching_legacy_lab_allow_for_source_only_block():
    client = FakePolicyClient(
        policies=[
            {
                "name": "FD_LAB_ALLOW_32FD0707AD9A",
                "policyid": 1,
                "srcintf": [{"name": "port2"}],
                "dstintf": [{"name": "port3"}],
                "srcaddr": [{"name": "FD_ADDR_10_10_10_10"}],
                "dstaddr": [{"name": "FD_ADDR_10_10_20_10"}],
                "action": "deny",
                "service": [{"name": "ALL"}],
            }
        ],
        address_objects=[
            {"name": "FD_ADDR_10_10_10_10", "subnet": "10.10.10.10 255.255.255.255"},
            {"name": "FD_ADDR_10_10_20_10", "subnet": "10.10.20.10 255.255.255.255"},
        ],
    )
    orchestrator = FortiGatePolicyOrchestrator(client, integration_id="int_fgt_lab")

    preflight = orchestrator.preflight(
        FortiGatePolicyPreflightRequest(
            intent=FortiGatePolicyIntent.TEMPORARY_BLOCK,
            scope=FortiGatePolicyScope.SOURCE_ONLY,
            source_interface="port2",
            destination_interface="port3",
            source_ip="10.10.10.10",
            duration_minutes=30,
        )
    )
    orchestrator.apply_changes(preflight.changes)

    assert [change.operation for change in preflight.changes] == ["update"]
    assert preflight.changes[0].payload["policyid"] == "1"
    assert preflight.changes[0].payload["dstaddr"] == [{"name": "all"}]
    assert preflight.changes[0].payload["service"] == [{"name": "ALL"}]
    assert client.created_policies == []
    assert client.updated_policies == [
        {
            "policyId": "1",
            "payload": {
                "dstaddr": [{"name": "all"}],
                "action": "deny",
                "service": [{"name": "ALL"}],
                "logtraffic": "all",
                "status": "enable",
                "comments": "Penguard owned temporary block policy",
            },
        }
    ]


def test_policy_orchestrator_updates_existing_broader_source_block_for_destination_block():
    client = FakePolicyClient(
        policies=[
            {
                "name": "FD_LAB_ALLOW_32FD0707AD9A",
                "policyid": 1,
                "srcintf": [{"name": "port2"}],
                "dstintf": [{"name": "port3"}],
                "srcaddr": [{"name": "FD_ADDR_10_10_10_10"}],
                "dstaddr": [{"name": "all"}],
                "action": "deny",
                "service": [{"name": "ALL"}],
            }
        ],
        address_objects=[
            {"name": "FD_ADDR_10_10_10_10", "subnet": "10.10.10.10 255.255.255.255"},
        ],
    )
    orchestrator = FortiGatePolicyOrchestrator(client, integration_id="int_fgt_lab")

    preflight = orchestrator.preflight(
        FortiGatePolicyPreflightRequest(
            intent=FortiGatePolicyIntent.TEMPORARY_BLOCK,
            scope=FortiGatePolicyScope.SOURCE_DESTINATION,
            source_interface="port2",
            destination_interface="port3",
            source_ip="10.10.10.10",
            destination_ip="10.10.20.10",
            duration_minutes=30,
        )
    )
    orchestrator.apply_changes(preflight.changes)

    assert [change.operation for change in preflight.changes] == ["update"]
    assert preflight.changes[0].payload["policyid"] == "1"
    assert client.created_policies == []
    assert client.updated_policies == [
        {
            "policyId": "1",
            "payload": {
                "action": "deny",
                "service": [{"name": "ALL"}],
                "logtraffic": "all",
                "status": "enable",
                "comments": "Penguard owned temporary block policy",
            },
        }
    ]


def test_policy_orchestrator_reuses_existing_temporary_block_and_moves_it():
    request = FortiGatePolicyPreflightRequest(
        intent=FortiGatePolicyIntent.TEMPORARY_BLOCK,
        scope=FortiGatePolicyScope.SOURCE_DESTINATION,
        source_interface="port2",
        destination_interface="port3",
        source_ip="192.0.2.50",
        destination_ip="198.51.100.10",
        duration_minutes=30,
    )
    policy_name = "PG_TMP_BLOCK_FC8832C8423C"
    client = FakePolicyClient(
        policies=[
            {"name": "PG_LAB_ALLOW_SCAN", "policyid": 10},
            {"name": policy_name, "policyid": 42},
        ],
        address_objects=[
            {"name": "PG_ADDR_192_0_2_50"},
            {"name": "PG_ADDR_198_51_100_10"},
        ],
    )
    orchestrator = FortiGatePolicyOrchestrator(client, integration_id="int_fgt_lab")

    preflight = orchestrator.preflight(request)
    applied = orchestrator.apply_changes(preflight.changes)

    assert preflight.proposed_policy_name == policy_name
    assert preflight.changes[-1].operation == "reuse"
    assert client.created_policies == []
    assert client.moved_policies == [
        {"policyId": "42", "before": "10", "after": None}
    ]
    assert applied[-1]["operation"] == "move"
