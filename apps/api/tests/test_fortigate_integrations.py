from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import dependencies as auth_dependencies
from app.auth.audit import InMemoryAuthAuditStore
from app.auth.token_cipher import TokenCipher
from app.db.base import Base
from app.db.models import (
    FortiGateHealthCheckModel,
    FortiGateIngestionStatusModel,
    FortiGateIntegrationModel,
)
from app.integrations.fortigate.client import FortiGateApiError
from app.integrations.fortigate.service import FortiGateIntegrationService
from app.integrations.fortigate.store import SqlAlchemyFortiGateIntegrationStore
from app.main import app
from app.routers import integrations as integrations_router


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


class HealthyFortiGateClient:
    def get_system_status(self):
        return {
            "hostname": "FGT-VM",
            "model_name": "FortiGate-VM64",
            "version": "v7.4.3",
            "serial": "FGVMTEST",
        }

    def get_performance_status(self):
        return {
            "cpu": {"idle": 97},
            "mem": {"total": 100, "used": 48},
        }

    def get_resource_usage(self, resource: str | None = None):
        assert resource == "session"
        return {"session": [{"current": 15}]}


class SyslogCapableFortiGateClient(HealthyFortiGateClient):
    def __init__(self):
        self.settings = {
            slot: {
                "status": "disable",
                "server": "",
                "port": 514,
                "mode": "udp",
                "facility": "local7",
                "format": "default",
            }
            for slot in (1, 2, 3, 4)
        }
        self.filters = {slot: {"severity": "information"} for slot in (1, 2, 3, 4)}
        self.setting_updates: list[dict] = []
        self.filter_updates: list[dict] = []

    @property
    def setting(self):
        return self.settings[1]

    @property
    def filter(self):
        return self.filters[1]

    def get_syslog_setting(self, *, slot: int = 1):
        return dict(self.settings[slot])

    def get_syslog_filter(self, *, slot: int = 1):
        return dict(self.filters[slot])

    def update_syslog_setting(self, payload, *, slot: int = 1):
        self.setting_updates.append({"slot": slot, **dict(payload)})
        self.settings[slot].update(payload)
        return dict(self.settings[slot])

    def update_syslog_filter(self, payload, *, slot: int = 1):
        self.filter_updates.append({"slot": slot, **dict(payload)})
        self.filters[slot].update(payload)
        return dict(self.filters[slot])


class PolicyCapableFortiGateClient(SyslogCapableFortiGateClient):
    def __init__(self):
        super().__init__()
        self.policies = [{"name": "FD_LAB_ALLOW_SCAN", "policyid": 10}]
        self.address_objects: list[dict] = []
        self.created_addresses: list[dict] = []
        self.created_policies: list[dict] = []

    def get_policies(self):
        return list(self.policies)

    def get_address_objects(self):
        return list(self.address_objects)

    def create_address_object(self, *, name: str, subnet: str, comment: str):
        payload = {"name": name, "subnet": subnet, "comment": comment}
        self.created_addresses.append(payload)
        self.address_objects.append(payload)
        return {"status": "success", "mkey": name}

    def create_firewall_policy(self, payload):
        self.created_policies.append(dict(payload))
        self.policies.append(dict(payload))
        return {"status": "success", "mkey": payload["name"]}


def healthy_client_factory(*, host: str, api_key: str, verify_tls: bool):
    return SyslogCapableFortiGateClient()


EXPECTED_SYSLOG_FILTER = {
    "severity": "information",
    "forward-traffic": "enable",
    "local-traffic": "enable",
    "multicast-traffic": "enable",
}


def test_fortigate_create_auto_configures_syslog_forwarding_when_missing():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    fake_client = SyslogCapableFortiGateClient()
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_auto_syslog",
        ),
        client_factory=lambda **_: fake_client,
    )

    created = service.create(
        owner_user_id="usr_owner",
        name="FortiGate Lab",
        host="https://fortigate.local/",
        api_key="fg_api_key_from_user",
        verify_tls=False,
        collector_host="10.10.10.50",
        collector_port=5514,
    )

    assert created["logForwarding"]["configured"] is True
    assert created["logForwarding"]["changed"] is True
    ingestion_status = service.store.get_ingestion_status(
        owner_user_id="usr_owner",
        integration_id=created["id"],
    )
    assert ingestion_status["enabled"] is False
    assert ingestion_status["status"] == "waiting_syslog"
    assert ingestion_status["lastRunTrigger"] == "syslog"
    assert fake_client.setting_updates == [
        {
            "slot": 1,
            "status": "enable",
            "server": "10.10.10.50",
            "port": 5514,
            "mode": "udp",
            "facility": "local7",
            "format": "default",
        }
    ]
    assert fake_client.filter_updates == [{"slot": 1, **EXPECTED_SYSLOG_FILTER}]


def test_fortigate_create_uses_empty_secondary_syslog_slot_when_primary_exists():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    fake_client = SyslogCapableFortiGateClient()
    fake_client.setting.update({"status": "enable", "server": "soc.example", "port": 5514})
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_existing_syslog",
        ),
        client_factory=lambda **_: fake_client,
    )

    created = service.create(
        owner_user_id="usr_owner",
        name="FortiGate Lab",
        host="https://fortigate.local/",
        api_key="fg_api_key_from_user",
        verify_tls=False,
        collector_host="10.10.10.50",
        collector_port=5514,
    )

    assert created["logForwarding"]["configured"] is True
    assert created["logForwarding"]["changed"] is True
    assert created["logForwarding"]["slot"] == 2
    assert created["logForwarding"]["current"]["slots"][1]["setting"]["server"] == "soc.example"
    assert created["logForwarding"]["current"]["slots"][2]["setting"]["server"] == "10.10.10.50"
    assert fake_client.setting_updates == [
        {
            "slot": 2,
            "status": "enable",
            "server": "10.10.10.50",
            "port": 5514,
            "mode": "udp",
            "facility": "local7",
            "format": "default",
        }
    ]
    assert fake_client.filter_updates == [{"slot": 2, **EXPECTED_SYSLOG_FILTER}]


def test_fortigate_create_updates_existing_collector_slot_when_traffic_filter_missing():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    fake_client = SyslogCapableFortiGateClient()
    fake_client.setting.update({
        "status": "enable",
        "server": "10.10.10.50",
        "port": 5514,
    })
    fake_client.filter.update({
        "severity": "information",
        "forward-traffic": "disable",
        "local-traffic": "disable",
        "multicast-traffic": "disable",
    })
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_existing_filter",
        ),
        client_factory=lambda **_: fake_client,
    )

    created = service.create(
        owner_user_id="usr_owner",
        name="FortiGate Lab",
        host="https://fortigate.local/",
        api_key="fg_api_key_from_user",
        verify_tls=False,
        collector_host="10.10.10.50",
        collector_port=5514,
    )

    assert created["logForwarding"]["configured"] is True
    assert created["logForwarding"]["changed"] is True
    assert created["logForwarding"]["slot"] == 1
    assert fake_client.setting_updates == [
        {
            "slot": 1,
            "status": "enable",
            "server": "10.10.10.50",
            "port": 5514,
            "mode": "udp",
            "facility": "local7",
            "format": "default",
        }
    ]
    assert fake_client.filter_updates == [{"slot": 1, **EXPECTED_SYSLOG_FILTER}]


def test_fortigate_service_can_status_and_apply_syslog_forwarding():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    fake_client = SyslogCapableFortiGateClient()
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_syslog",
        ),
        client_factory=lambda **_: fake_client,
    )
    service.create(
        owner_user_id="usr_owner",
        name="FortiGate Lab",
        host="https://fortigate.local/",
        api_key="fg_api_key_from_user",
        verify_tls=False,
    )

    status_payload = service.get_log_forwarding_status(
        integration_id="int_fgt_syslog",
        owner_user_id="usr_owner",
    )
    service.record_syslog_event(
        owner_user_id="usr_owner",
        integration_id="int_fgt_syslog",
        event_id="evt_syslog_01",
        received_at=datetime(2026, 5, 14, 22, 55, tzinfo=UTC),
    )
    streaming_status = service.get_log_forwarding_status(
        integration_id="int_fgt_syslog",
        owner_user_id="usr_owner",
    )
    applied = service.apply_log_forwarding(
        integration_id="int_fgt_syslog",
        owner_user_id="usr_owner",
        collector_host="10.10.10.50",
        port=5514,
        confirmed=True,
    )

    assert status_payload["configured"] is False
    assert streaming_status["receiveStatus"]["mode"] == "syslog"
    assert streaming_status["receiveStatus"]["pollingEnabled"] is False
    assert streaming_status["receiveStatus"]["lastReceivedAt"] == "2026-05-14T22:55:00.000Z"
    assert streaming_status["receiveStatus"]["lastEventIds"] == ["evt_syslog_01"]
    assert applied["configured"] is True
    assert applied["current"]["setting"]["server"] == "10.10.10.50"
    assert applied["current"]["setting"]["port"] == 5514


def test_fortigate_service_refuses_log_forwarding_apply_without_confirmation():
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=create_engine(
                "sqlite+pysqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            ),
            secret_cipher=TokenCipher.from_secret("test-secret"),
        ),
        client_factory=lambda **_: SyslogCapableFortiGateClient(),
    )

    try:
        service.apply_log_forwarding(
            integration_id="int_fgt_missing",
            owner_user_id="usr_owner",
            collector_host="10.10.10.50",
            port=5514,
            confirmed=False,
        )
    except PermissionError as exc:
        assert "confirmation" in str(exc)
    else:
        raise AssertionError("apply_log_forwarding should require explicit confirmation")


def test_fortigate_integration_store_encrypts_api_key_and_returns_public_payload():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    store = SqlAlchemyFortiGateIntegrationStore(
        engine=engine,
        secret_cipher=TokenCipher.from_secret("test-secret"),
        id_factory=lambda: "int_fgt_test",
    )

    created = store.create(
        owner_user_id="usr_owner",
        name="FortiGate Lab",
        host="https://fortigate.local/",
        api_key="fg_api_key_from_user",
        verify_tls=False,
    )

    with Session(engine) as db:
        row = db.execute(select(FortiGateIntegrationModel)).scalar_one()

    assert created["id"] == "int_fgt_test"
    assert created["type"] == "fortigate"
    assert created["name"] == "FortiGate Lab"
    assert created["status"] == "connected"
    assert created["capabilities"] == ["system", "interfaces", "policies", "threat_logs"]
    assert "apiKey" not in created
    assert row.owner_user_id == "usr_owner"
    assert row.api_key_blob != ""
    assert "fg_api_key_from_user" not in row.api_key_blob
    assert store.get_api_key("int_fgt_test", owner_user_id="usr_owner") == "fg_api_key_from_user"

    listed = store.list_public(owner_user_id="usr_owner")

    assert listed == {
        "items": [
            {
                "id": "int_fgt_test",
                "type": "fortigate",
                "name": "FortiGate Lab",
                "host": "https://fortigate.local/",
                "status": "connected",
                "lastCheckedAt": created["lastCheckedAt"],
            }
        ]
    }
    assert "apiKey" not in listed["items"][0]


def test_fortigate_integration_store_scopes_rows_by_owner_user_id():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    ids = iter(["int_fgt_owner_a", "int_fgt_owner_b"])
    store = SqlAlchemyFortiGateIntegrationStore(
        engine=engine,
        secret_cipher=TokenCipher.from_secret("test-secret"),
        id_factory=lambda: next(ids),
    )

    store.create(
        owner_user_id="usr_a",
        name="Owner A FortiGate",
        host="https://fortigate-a.local/",
        api_key="owner-a-token",
        verify_tls=False,
    )
    store.create(
        owner_user_id="usr_b",
        name="Owner B FortiGate",
        host="https://fortigate-b.local/",
        api_key="owner-b-token",
        verify_tls=False,
    )

    assert [item["id"] for item in store.list_public(owner_user_id="usr_a")["items"]] == [
        "int_fgt_owner_a"
    ]
    assert store.get_connection("int_fgt_owner_b", owner_user_id="usr_a") is None
    assert store.get_connection("int_fgt_owner_a", owner_user_id="usr_a") == {
        "id": "int_fgt_owner_a",
        "host": "https://fortigate-a.local/",
        "api_key": "owner-a-token",
        "verify_tls": False,
    }


def test_fortigate_integration_store_deletes_only_owned_integration_and_health_checks():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    ids = iter(["int_fgt_owner_a", "int_fgt_owner_b"])
    store = SqlAlchemyFortiGateIntegrationStore(
        engine=engine,
        secret_cipher=TokenCipher.from_secret("test-secret"),
        id_factory=lambda: next(ids),
        health_id_factory=lambda: "fgt_health_owner_a",
    )

    store.create(
        owner_user_id="usr_a",
        name="Owner A FortiGate",
        host="https://fortigate-a.local/",
        api_key="owner-a-token",
        verify_tls=False,
    )
    store.create(
        owner_user_id="usr_b",
        name="Owner B FortiGate",
        host="https://fortigate-b.local/",
        api_key="owner-b-token",
        verify_tls=False,
    )
    store.record_health_check(
        owner_user_id="usr_a",
        integration_id="int_fgt_owner_a",
        ok=True,
        status="connected",
        device={"hostname": "FGT-VM"},
        message=None,
        latency_ms=12,
        checked_at=datetime.now(UTC),
    )

    assert store.delete(owner_user_id="usr_b", integration_id="int_fgt_owner_a") is False
    assert store.delete(owner_user_id="usr_a", integration_id="int_fgt_owner_a") is True

    with Session(engine) as db:
        integration_ids = [
            row.id for row in db.execute(select(FortiGateIntegrationModel)).scalars()
        ]
        health_ids = [row.id for row in db.execute(select(FortiGateHealthCheckModel)).scalars()]

    assert integration_ids == ["int_fgt_owner_b"]
    assert health_ids == []


def test_fortigate_integration_store_resolves_syslog_source_ip_to_integration():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    store = SqlAlchemyFortiGateIntegrationStore(
        engine=engine,
        secret_cipher=TokenCipher.from_secret("unit-test-secret"),
        id_factory=lambda: "int_fgt_syslog_source",
    )
    store.create(
        owner_user_id="user_01",
        name="Lab FortiGate",
        host="https://192.0.2.118",
        api_key="super-secret-api-key",
        verify_tls=False,
    )

    resolved = store.find_public_by_host("192.0.2.118")

    assert resolved is not None
    assert resolved["id"] == "int_fgt_syslog_source"
    assert resolved["host"] == "https://192.0.2.118"
    assert "apiKey" not in resolved


def test_fortigate_integration_store_resolves_syslog_device_id_when_source_ip_differs():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    store = SqlAlchemyFortiGateIntegrationStore(
        engine=engine,
        secret_cipher=TokenCipher.from_secret("unit-test-secret"),
        id_factory=lambda: "int_fgt_syslog_device",
    )
    store.create(
        owner_user_id="user_01",
        name="Lab FortiGate",
        host="https://192.0.2.118",
        api_key="super-secret-api-key",
        verify_tls=False,
        device={"hostname": "FGT-VM", "serial": "FGVMTEST"},
    )

    resolved = store.find_syslog_source(
        "10.10.99.1",
        fields={"devid": "FGVMTEST", "devname": "FGT-VM"},
    )

    assert resolved == {"integrationId": "int_fgt_syslog_device", "ownerUserId": "user_01"}


def test_fortigate_integration_store_prefers_syslog_device_id_over_shared_host():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    ids = iter(["int_fgt_stale", "int_fgt_current"])
    store = SqlAlchemyFortiGateIntegrationStore(
        engine=engine,
        secret_cipher=TokenCipher.from_secret("unit-test-secret"),
        id_factory=lambda: next(ids),
    )
    store.create(
        owner_user_id="user_old",
        name="Old FortiGate",
        host="https://192.0.2.118",
        api_key="old-secret-api-key",
        verify_tls=False,
    )
    store.create(
        owner_user_id="user_current",
        name="Current FortiGate",
        host="https://192.0.2.118",
        api_key="current-secret-api-key",
        verify_tls=False,
        device={"hostname": "FGVMEVJAOUIR5F07", "serial": "FGVMTEST"},
    )

    resolved = store.find_syslog_source(
        "192.0.2.118",
        fields={"devid": "FGVMTEST", "devname": "FGVMEVJAOUIR5F07"},
    )

    assert resolved == {
        "integrationId": "int_fgt_current",
        "ownerUserId": "user_current",
    }


def test_fortigate_integration_store_records_syslog_receipt_and_disables_polling():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    store = SqlAlchemyFortiGateIntegrationStore(
        engine=engine,
        secret_cipher=TokenCipher.from_secret("unit-test-secret"),
        id_factory=lambda: "int_fgt_syslog_receipt",
        ingestion_id_factory=lambda: "fgt_ingest_syslog_receipt",
    )
    store.create(
        owner_user_id="user_01",
        name="Lab FortiGate",
        host="https://192.0.2.118",
        api_key="super-secret-api-key",
        verify_tls=False,
    )
    store.upsert_ingestion_status(
        owner_user_id="user_01",
        integration_id="int_fgt_syslog_receipt",
        enabled=True,
        interval_seconds=30,
        updated_at=datetime(2026, 5, 14, 22, 50, tzinfo=UTC),
    )

    status = store.record_syslog_event(
        owner_user_id="user_01",
        integration_id="int_fgt_syslog_receipt",
        event_id="evt_syslog_01",
        received_at=datetime(2026, 5, 14, 22, 51, tzinfo=UTC),
    )

    assert status["enabled"] is False
    assert status["status"] == "streaming"
    assert status["lastRunTrigger"] == "syslog"
    assert status["lastRawEventCount"] == 1
    assert status["lastCreatedCount"] == 1
    assert status["lastEventIds"] == ["evt_syslog_01"]
    assert status["lastSuccessAt"] == "2026-05-14T22:51:00.000Z"
    assert store.list_due_ingestion_statuses(
        now=datetime(2026, 5, 14, 22, 52, tzinfo=UTC)
    ) == []


def test_fortigate_integration_store_persists_ingestion_pipeline_status():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    store = SqlAlchemyFortiGateIntegrationStore(
        engine=engine,
        secret_cipher=TokenCipher.from_secret("test-secret"),
        id_factory=lambda: "int_fgt_ingest",
        ingestion_id_factory=lambda: "fgt_ingest_status_01",
    )
    store.create(
        owner_user_id="usr_owner",
        name="FortiGate Lab",
        host="https://fortigate.local/",
        api_key="fg_api_key_from_user",
        verify_tls=False,
    )

    configured = store.upsert_ingestion_status(
        owner_user_id="usr_owner",
        integration_id="int_fgt_ingest",
        enabled=True,
        interval_seconds=30,
        updated_at=datetime(2026, 5, 13, 18, 0, tzinfo=UTC),
    )
    started = store.record_ingestion_started(
        owner_user_id="usr_owner",
        integration_id="int_fgt_ingest",
        started_at=datetime(2026, 5, 13, 18, 1, tzinfo=UTC),
        trigger="manual",
    )
    completed = store.record_ingestion_result(
        owner_user_id="usr_owner",
        integration_id="int_fgt_ingest",
        ok=True,
        raw_event_count=4,
        created_count=1,
        event_ids=["evt_01"],
        error=None,
        finished_at=datetime(2026, 5, 13, 18, 1, 2, tzinfo=UTC),
    )

    with Session(engine) as db:
        row = db.execute(select(FortiGateIngestionStatusModel)).scalar_one()

    assert configured["enabled"] is True
    assert configured["intervalSeconds"] == 30
    assert started["status"] == "running"
    assert completed == {
        "id": "fgt_ingest_status_01",
        "integrationId": "int_fgt_ingest",
        "enabled": True,
        "intervalSeconds": 30,
        "status": "success",
        "lastStartedAt": "2026-05-13T18:01:00.000Z",
        "lastFinishedAt": "2026-05-13T18:01:02.000Z",
        "lastSuccessAt": "2026-05-13T18:01:02.000Z",
        "lastError": None,
        "lastRawEventCount": 4,
        "lastCreatedCount": 1,
        "lastEventIds": ["evt_01"],
        "lastRunTrigger": "manual",
        "updatedAt": "2026-05-13T18:01:02.000Z",
    }
    assert row.owner_user_id == "usr_owner"
    assert row.integration_id == "int_fgt_ingest"
    assert row.last_event_ids == ["evt_01"]


def test_fortigate_integration_service_can_use_persistent_store():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_service",
        ),
        client_factory=healthy_client_factory,
    )

    created = service.create(
        owner_user_id="usr_owner",
        name="FortiGate Lab",
        host="https://fortigate.local/",
        api_key="fg_api_key_from_user",
        verify_tls=False,
    )
    listed = service.list(owner_user_id="usr_owner")

    assert created["id"] == "int_fgt_service"
    assert listed["items"][0]["id"] == "int_fgt_service"


def test_fortigate_integration_service_deletes_owned_integration():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_service",
        ),
        client_factory=healthy_client_factory,
    )
    service.create(
        owner_user_id="usr_owner",
        name="FortiGate Lab",
        host="https://fortigate.local/",
        api_key="fg_api_key_from_user",
        verify_tls=False,
    )

    assert service.delete(integration_id="int_fgt_service", owner_user_id="usr_other") is False
    assert service.delete(integration_id="int_fgt_service", owner_user_id="usr_owner") is True
    assert service.list(owner_user_id="usr_owner") == {"items": []}


def test_fortigate_integration_service_does_not_persist_failed_connection():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    class FailingClient:
        def get_system_status(self):
            raise FortiGateApiError("FortiGate API request failed")

        def get_performance_status(self):
            return {}

        def get_resource_usage(self, resource: str | None = None):
            return {}

    store = SqlAlchemyFortiGateIntegrationStore(
        engine=engine,
        secret_cipher=TokenCipher.from_secret("test-secret"),
        id_factory=lambda: "int_fgt_failed",
    )
    service = FortiGateIntegrationService(
        store=store,
        client_factory=lambda *, host, api_key, verify_tls: FailingClient(),
    )

    try:
        service.create(
            owner_user_id="usr_owner",
            name="Broken FortiGate",
            host="https://fortigate.invalid/",
            api_key="secret-token-123",
            verify_tls=False,
        )
    except RuntimeError as exc:
        assert str(exc) == "FortiGate API request failed"
    else:
        raise AssertionError("expected failed FortiGate connection")

    assert store.list_public(owner_user_id="usr_owner") == {"items": []}


def test_fortigate_integration_service_tests_connection_with_live_client():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_service",
        ),
        client_factory=healthy_client_factory,
    )

    result = service.test_connection(
        host="https://fortigate.local/",
        api_key="secret-token",
        verify_tls=False,
    )

    assert result == {
        "ok": True,
        "status": "connected",
        "device": {
            "hostname": "FGT-VM",
            "model": "FortiGate-VM64",
            "serial": "FGVMTEST",
            "version": "v7.4.3",
        },
    }


def test_fortigate_integration_endpoint_can_use_persistent_service():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_endpoint",
        ),
        client_factory=lambda **_: SyslogCapableFortiGateClient(),
    )
    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = lambda: (
        service
    )
    client = TestClient(app)

    try:
        create_response = client.post(
            "/api/integrations/fortigate",
            headers=csrf_headers(client),
            json={
                "name": "FortiGate Lab",
                "host": "https://fortigate.local",
                "apiKey": "fg_api_key_from_user",
                "verifyTls": False,
                "collectorHost": "10.10.10.50",
            },
        )
        list_response = client.get("/api/integrations")
    finally:
        app.dependency_overrides.pop(
            integrations_router.get_fortigate_integration_service,
            None,
        )
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert create_response.status_code == 201
    assert "apiKey" not in create_response.json()
    assert create_response.json()["id"] == "int_fgt_endpoint"
    log_forwarding = create_response.json()["logForwarding"]
    assert log_forwarding["integrationId"] == "int_fgt_endpoint"
    assert log_forwarding["configured"] is True
    assert log_forwarding["changed"] is True
    assert log_forwarding["slot"] == 1
    assert log_forwarding["current"]["slots"]["1"]["setting"] == {
        "status": "enable",
        "server": "10.10.10.50",
        "port": 5514,
        "mode": "udp",
        "facility": "local7",
        "format": "default",
    }
    assert log_forwarding["current"]["slots"]["1"]["filter"] == EXPECTED_SYSLOG_FILTER
    assert list_response.status_code == 200
    assert list_response.json()["items"] == [
        {
            "id": "int_fgt_endpoint",
            "type": "fortigate",
            "name": "FortiGate Lab",
            "host": "https://fortigate.local/",
            "status": "connected",
            "lastCheckedAt": create_response.json()["lastCheckedAt"],
        }
    ]


def test_fortigate_integration_endpoint_scopes_list_to_authenticated_user():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    ids = iter(["int_fgt_owner_a", "int_fgt_owner_b"])
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: next(ids),
        ),
        client_factory=healthy_client_factory,
    )
    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = lambda: (
        service
    )
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_a",
        "email": "a@example.com",
        "displayName": "Analyst A",
        "roles": ["analyst"],
    }
    client = TestClient(app)

    try:
        first_response = client.post(
            "/api/integrations/fortigate",
            headers=csrf_headers(client),
            json={
                "name": "Owner A FortiGate",
                "host": "https://fortigate-a.local",
                "apiKey": "owner-a-token-123",
                "verifyTls": False,
            },
        )
        app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
            "id": "usr_b",
            "email": "b@example.com",
            "displayName": "Analyst B",
            "roles": ["analyst"],
        }
        second_response = client.post(
            "/api/integrations/fortigate",
            headers=csrf_headers(client),
            json={
                "name": "Owner B FortiGate",
                "host": "https://fortigate-b.local",
                "apiKey": "owner-b-token-123",
                "verifyTls": False,
            },
        )
        app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
            "id": "usr_a",
            "email": "a@example.com",
            "displayName": "Analyst A",
            "roles": ["analyst"],
        }
        list_response = client.get("/api/integrations")
    finally:
        app.dependency_overrides.pop(
            integrations_router.get_fortigate_integration_service,
            None,
        )
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert [item["id"] for item in list_response.json()["items"]] == ["int_fgt_owner_a"]


def test_fortigate_integration_endpoint_deletes_owned_integration():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_endpoint_delete",
        ),
        client_factory=healthy_client_factory,
    )
    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = lambda: (
        service
    )
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_owner",
        "email": "owner@example.com",
        "displayName": "Owner",
        "roles": ["analyst"],
    }
    client = TestClient(app)

    try:
        create_response = client.post(
            "/api/integrations/fortigate",
            headers=csrf_headers(client),
            json={
                "name": "FortiGate Lab",
                "host": "https://fortigate.local",
                "apiKey": "fg_api_key_from_user",
                "verifyTls": False,
            },
        )
        delete_response = client.delete(
            "/api/integrations/int_fgt_endpoint_delete",
            headers=csrf_headers(client),
        )
        list_response = client.get("/api/integrations")
    finally:
        app.dependency_overrides.pop(
            integrations_router.get_fortigate_integration_service,
            None,
        )
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert create_response.status_code == 201
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "id": "int_fgt_endpoint_delete"}
    assert list_response.json() == {"items": []}


def test_fortigate_integration_endpoint_returns_404_when_deleting_other_users_integration():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_endpoint_other",
        ),
        client_factory=healthy_client_factory,
    )
    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = lambda: (
        service
    )
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_owner",
        "email": "owner@example.com",
        "displayName": "Owner",
        "roles": ["analyst"],
    }
    client = TestClient(app)

    try:
        create_response = client.post(
            "/api/integrations/fortigate",
            headers=csrf_headers(client),
            json={
                "name": "FortiGate Lab",
                "host": "https://fortigate.local",
                "apiKey": "fg_api_key_from_user",
                "verifyTls": False,
            },
        )
        app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
            "id": "usr_other",
            "email": "other@example.com",
            "displayName": "Other",
            "roles": ["analyst"],
        }
        delete_response = client.delete(
            "/api/integrations/int_fgt_endpoint_other",
            headers=csrf_headers(client),
        )
    finally:
        app.dependency_overrides.pop(
            integrations_router.get_fortigate_integration_service,
            None,
        )
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert create_response.status_code == 201
    assert delete_response.status_code == 404
    assert delete_response.json() == {"detail": "Integration not found"}


def test_fortigate_log_forwarding_endpoints_status_after_connect_auto_apply():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    fake_client = SyslogCapableFortiGateClient()
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_syslog_endpoint",
        ),
        client_factory=lambda **_: fake_client,
    )
    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = lambda: (
        service
    )
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_owner",
        "email": "owner@example.com",
        "displayName": "Owner",
        "roles": ["admin"],
    }
    client = TestClient(app)

    try:
        create_response = client.post(
            "/api/integrations/fortigate",
            headers=csrf_headers(client),
            json={
                "name": "FortiGate Lab",
                "host": "https://fortigate.local",
                "apiKey": "fg_api_key_from_user",
                "verifyTls": False,
                "collectorHost": "10.10.10.50",
            },
        )
        status_response = client.get(
            "/api/integrations/fortigate/int_fgt_syslog_endpoint/log-forwarding/status"
        )
    finally:
        app.dependency_overrides.pop(
            integrations_router.get_fortigate_integration_service,
            None,
        )
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert create_response.status_code == 201
    assert create_response.json()["logForwarding"]["changed"] is True
    assert status_response.status_code == 200
    assert status_response.json()["configured"] is True
    assert status_response.json()["current"]["setting"]["server"] == "10.10.10.50"


def test_fortigate_log_forwarding_collector_test_endpoint_sends_synthetic_syslog(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    fake_client = SyslogCapableFortiGateClient()
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_collector_test",
        ),
        client_factory=lambda **_: fake_client,
    )
    sent = []

    async def fake_probe(*, host: str, port: int, integration_id: str):
        sent.append({"host": host, "port": port, "integrationId": integration_id})
        return {
            "sent": True,
            "collectorHost": host,
            "collectorPort": port,
            "integrationId": integration_id,
            "sentAt": "2026-05-14T23:10:00.000Z",
            "sample": "date=2026-05-14 probe=true",
        }

    monkeypatch.setattr(integrations_router, "send_fortigate_syslog_probe", fake_probe)
    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = lambda: (
        service
    )
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_owner",
        "email": "owner@example.com",
        "displayName": "Owner",
        "roles": ["admin"],
    }
    client = TestClient(app)

    try:
        client.post(
            "/api/integrations/fortigate",
            headers=csrf_headers(client),
            json={
                "name": "FortiGate Lab",
                "host": "https://fortigate.local",
                "apiKey": "fg_api_key_from_user",
                "verifyTls": False,
            },
        )
        response = client.post(
            "/api/integrations/fortigate/int_fgt_collector_test/log-forwarding/test-collector",
            headers=csrf_headers(client),
            json={"collectorHost": "127.0.0.1", "port": 5514},
        )
    finally:
        app.dependency_overrides.pop(
            integrations_router.get_fortigate_integration_service,
            None,
        )
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert response.status_code == 200
    assert sent == [
        {"host": "127.0.0.1", "port": 5514, "integrationId": "int_fgt_collector_test"}
    ]
    payload = response.json()
    assert payload["sent"] is True
    assert payload["integrationId"] == "int_fgt_collector_test"
    assert payload["receiveStatus"]["mode"] == "syslog"
    assert payload["receiveStatus"]["pollingEnabled"] is False



def test_fortigate_policy_review_and_apply_endpoints_create_real_policy_request():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    fake_client = PolicyCapableFortiGateClient()
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_policy_apply",
        ),
        client_factory=lambda **_: fake_client,
    )
    audit_store = InMemoryAuthAuditStore()

    def override_policy_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = lambda: (
        service
    )
    app.dependency_overrides[integrations_router.get_policy_db] = override_policy_db
    app.dependency_overrides[auth_dependencies.get_auth_audit_store] = lambda: audit_store
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_owner",
        "email": "owner@example.com",
        "displayName": "Owner",
        "roles": ["analyst"],
    }
    client = TestClient(app)

    try:
        client.post(
            "/api/integrations/fortigate",
            headers=csrf_headers(client),
            json={
                "name": "FortiGate Lab",
                "host": "https://fortigate.local",
                "apiKey": "fg_api_key_from_user",
                "verifyTls": False,
                "collectorHost": "127.0.0.1",
            },
        )
        preflight_response = client.post(
            "/api/integrations/fortigate/int_fgt_policy_apply/policy/preflight",
            headers=csrf_headers(client),
            json={
                "intent": "temporary_block",
                "scope": "source_destination",
                "source_interface": "port2",
                "destination_interface": "port3",
                "source_ip": "192.0.2.50",
                "destination_ip": "198.51.100.10",
                "duration_minutes": 30,
                "incident_id": "inc_123",
                "playbook_run_id": "run_123",
            },
        )
        assert preflight_response.status_code == 200
        assert fake_client.created_addresses == []
        assert fake_client.created_policies == []

        review_response = client.post(
            "/api/integrations/fortigate/int_fgt_policy_apply/policy/review",
            headers=csrf_headers(client),
            json={
                "intent": "temporary_block",
                "scope": "source_destination",
                "source_interface": "port2",
                "destination_interface": "port3",
                "source_ip": "192.0.2.50",
                "destination_ip": "198.51.100.10",
                "duration_minutes": 30,
                "incident_id": "inc_123",
                "playbook_run_id": "run_123",
            },
        )
        review_payload = review_response.json()
        mismatch_response = client.post(
            "/api/integrations/fortigate/int_fgt_policy_apply/policy/apply",
            headers=csrf_headers(client),
            json={"request_id": review_payload["request_id"], "review_hash": "bad-hash"},
        )
        apply_response = client.post(
            "/api/integrations/fortigate/int_fgt_policy_apply/policy/apply",
            headers=csrf_headers(client),
            json={
                "request_id": review_payload["request_id"],
                "review_hash": review_payload["review_hash"],
            },
        )
    finally:
        app.dependency_overrides.pop(
            integrations_router.get_fortigate_integration_service,
            None,
        )
        app.dependency_overrides.pop(integrations_router.get_policy_db, None)
        app.dependency_overrides.pop(auth_dependencies.get_auth_audit_store, None)
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert preflight_response.status_code == 200
    preflight_payload = preflight_response.json()
    assert preflight_payload["proposed_policy_name"] == (
        "FD_TMP_BLOCK_192_0_2_50_TO_198_51_100_10"
    )
    assert preflight_payload["placement"] == (
        "before first FortiDashboard-owned lab allow/log policy"
    )

    assert review_response.status_code == 200
    assert review_payload["status"] == "pending_review"
    assert review_payload["request_id"].startswith("fgpcr_")
    assert review_payload["review_hash"] == preflight_payload["review_hash"]

    assert mismatch_response.status_code == 409
    assert mismatch_response.json() == {"detail": "Policy review hash mismatch"}

    assert apply_response.status_code == 200
    apply_payload = apply_response.json()
    assert apply_payload["status"] == "applied"
    assert [item["name"] for item in apply_payload["applied_changes"]] == [
        "FD_ADDR_192_0_2_50",
        "FD_ADDR_198_51_100_10",
        "FD_TMP_BLOCK_192_0_2_50_TO_198_51_100_10",
    ]
    assert len(fake_client.created_addresses) == 2
    assert fake_client.created_policies[0]["action"] == "deny"
    assert [event.action for event in audit_store.events][-3:] == [
        "integration.fortigate.policy_preflight",
        "integration.fortigate.policy_review_created",
        "integration.fortigate.policy_applied",
    ]


def test_fortigate_traffic_policy_draft_endpoint_is_deprecated():
    client = TestClient(app)

    response = client.post(
        "/api/integrations/fortigate/int_fgt_policy_draft/traffic-policy-draft",
        headers=csrf_headers(client),
        json={
            "name": "TEMP_SOC_LAN_to_DMZ_allow_log",
            "sourceInterface": "port2",
            "destinationInterface": "port3",
            "sourceSubnet": "192.0.2.0/24",
            "destinationSubnet": "198.51.100.0/24",
            "service": "ALL",
            "action": "accept",
        },
    )

    assert response.status_code == 410
    assert response.json() == {
        "detail": (
            "Traffic policy drafts were replaced by governed FortiGate policy review endpoints."
        )
    }
